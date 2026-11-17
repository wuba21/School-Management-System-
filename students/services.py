"""
Student Management Service Layer for SSMS.

Handles:
  - Atomic Admission Number generation and validation
  - Secure file upload validation for student portraits
  - Role-based student querysets and multi-parameter filtering
  - Comprehensive audit logging for student changes
"""

import os
import re
from datetime import date
from decimal import Decimal
import io
from PIL import Image

from django.db import transaction
from django.db.models import Q, Max
from django.core.exceptions import ValidationError, PermissionDenied
from django.conf import settings
from django.utils import timezone
from django.http import HttpResponse
from django.urls import reverse

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderSVG, renderPDF

from students.models import Student, StudentEnrollment, StudentIDCard, StudentCertificate
from academics.models import AcademicYear, Grade, Section, Stream, ClassOffering
from teachers.models import Teacher, TeacherAssignment
from core.models import AuditLog
from core.utils.ethiopian_calendar import gregorian_to_ethiopian, EthiopianDate


class AdmissionNumberService:
    """
    Manages unique, sequential, and configurable student admission numbers.
    Format: SSMS/{YEAR}/{SEQUENCE} (e.g. SSMS/2026/0001).
    Avoids race conditions using database transactions and atomic sequence checks.
    """
    DEFAULT_PREFIX = 'SSMS'
    PATTERN = re.compile(r'^[A-Za-z0-9]+/[0-9]{4}/[0-9]{3,}$')

    @classmethod
    def get_year_string(cls, academic_year=None):
        """Extracts a 4-digit calendar year from the current academic year or date."""
        if academic_year:
            match = re.search(r'\b(20[2-9][0-9])\b', academic_year.code or academic_year.name)
            if match:
                return match.group(1)
            if academic_year.start_date:
                return str(academic_year.start_date.year)
        
        current_ay = AcademicYear.objects.filter(is_current=True).first()
        if current_ay:
            match = re.search(r'\b(20[2-9][0-9])\b', current_ay.code or current_ay.name)
            if match:
                return match.group(1)
            if current_ay.start_date:
                return str(current_ay.start_date.year)

        return str(timezone.localdate().year)

    @classmethod
    def generate_next_admission_number(cls, academic_year=None, prefix=None):
        """
        Generates the next sequential unique admission number.
        Runs inside an atomic block to prevent concurrent sequence collisions.
        """
        prefix = prefix or cls.DEFAULT_PREFIX
        year = cls.get_year_string(academic_year)
        year_prefix = f"{prefix}/{year}/"

        with transaction.atomic():
            # Query existing numbers for this prefix and year
            existing_numbers = (
                Student.objects.filter(admission_number__startswith=year_prefix)
                .values_list('admission_number', flat=True)
            )

            max_seq = 0
            for num in existing_numbers:
                try:
                    parts = num.split('/')
                    if len(parts) == 3:
                        seq = int(parts[2])
                        if seq > max_seq:
                            max_seq = seq
                except (ValueError, IndexError):
                    continue

            next_seq = max_seq + 1
            return f"{year_prefix}{next_seq:04d}"

    @classmethod
    def validate_admission_number(cls, admission_number, exclude_student_id=None):
        """
        Validates the format and uniqueness of an admission number.
        Allows custom school formats if well-formed alphanumeric strings.
        """
        if not admission_number or not admission_number.strip():
            raise ValidationError("Admission number is required.")

        clean_number = admission_number.strip()
        
        # Check allowed characters: letters, digits, slash, hyphen
        if not re.match(r'^[A-Za-z0-9/\-_]+$', clean_number):
            raise ValidationError(
                "Admission number may only contain letters, numbers, slashes (/), hyphens (-), and underscores (_)."
            )

        # Uniqueness check
        query = Student.objects.filter(admission_number__iexact=clean_number)
        if exclude_student_id:
            query = query.exclude(pk=exclude_student_id)

        if query.exists():
            raise ValidationError(f"Admission number '{clean_number}' is already registered to another student.")

        return clean_number


class FileUploadSecurityService:
    """
    Validates uploaded student profile photographs.
    Prevents executable uploads, verifies magic image headers, and checks file sizes.
    """
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB (accommodates high-res smartphone portraits)
    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.jfif', '.bmp'}
    ALLOWED_IMAGE_FORMATS = {'JPEG', 'PNG', 'WEBP', 'MPO', 'JFIF', 'BMP'}

    @classmethod
    def validate_student_photo(cls, uploaded_file):
        """
        Validates an uploaded image file thoroughly:
          1. File size under 5MB
          2. Safe file extension
          3. Valid image binary header via PIL (detecting renamed binaries)
        """
        if not uploaded_file:
            return None

        # 1. File size check
        if uploaded_file.size > cls.MAX_FILE_SIZE:
            raise ValidationError("Photograph size must not exceed 5MB.")

        # 2. Extension check
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext not in cls.ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"Unsupported image format ({ext}). Allowed formats: JPG, PNG, WebP."
            )

        # 3. Content inspection via PIL
        try:
            uploaded_file.seek(0)
            img = Image.open(uploaded_file)
            img.verify()
            fmt = (img.format or '').upper()
            if fmt not in cls.ALLOWED_IMAGE_FORMATS:
                raise ValidationError(
                    f"Invalid image structure. Detected format: {fmt}."
                )
            uploaded_file.seek(0)
        except Exception as exc:
            if isinstance(exc, ValidationError):
                raise
            raise ValidationError(f"The uploaded file is not a valid or safe image file.")

        return uploaded_file


class StudentService:
    """
    Encapsulates querying, role-based scoping, filtering, and audit logging for students.
    """

    @staticmethod
    def get_scoped_queryset(user):
        """
        Returns student queryset scoped according to user role:
          - Principal / Registrar / Admin: All students
          - Teacher: Students enrolled in classes assigned to this teacher
          - Other: None
        """
        role_code = user.role.code if user.role else ('ADMIN' if user.is_superuser else None)

        if role_code in ('ADMIN', 'PRINCIPAL', 'REGISTRAR') or user.is_superuser:
            return Student.objects.all().select_related()

        if role_code == 'TEACHER':
            teacher = getattr(user, 'teacher_profile', None)
            if not teacher:
                teacher = Teacher.objects.filter(user=user).first()
            if teacher:
                assigned_classes = ClassOffering.objects.filter(
                    teacher_assignments__teacher=teacher
                )
                return Student.objects.filter(
                    enrollments__class_offering__in=assigned_classes,
                    enrollments__status='ACTIVE'
                ).distinct()
            return Student.objects.none()

        return Student.objects.none()

    @staticmethod
    def filter_students(queryset, params):
        """
        Applies search, grade, section, stream, academic year, gender, and status filters.
        """
        search_query = params.get('q', '').strip()
        if search_query:
            queryset = queryset.filter(
                Q(admission_number__icontains=search_query) |
                Q(first_name__icontains=search_query) |
                Q(father_name__icontains=search_query) |
                Q(grandfather_name__icontains=search_query)
            )

        grade_id = params.get('grade')
        if grade_id:
            queryset = queryset.filter(enrollments__class_offering__grade_id=grade_id)

        section_id = params.get('section')
        if section_id:
            queryset = queryset.filter(enrollments__class_offering__section_id=section_id)

        stream_id = params.get('stream')
        if stream_id:
            queryset = queryset.filter(enrollments__class_offering__stream_id=stream_id)

        academic_year_id = params.get('academic_year')
        if academic_year_id:
            queryset = queryset.filter(enrollments__academic_year_id=academic_year_id)

        status = params.get('status')
        if status:
            queryset = queryset.filter(status=status)

        gender = params.get('gender')
        if gender:
            queryset = queryset.filter(gender=gender)

        # Sorting
        sort_by = params.get('sort', 'name')
        if sort_by == 'name_desc':
            queryset = queryset.order_by('-first_name', '-father_name')
        elif sort_by == 'admission_number':
            queryset = queryset.order_by('admission_number')
        elif sort_by == 'admission_number_desc':
            queryset = queryset.order_by('-admission_number')
        elif sort_by == 'date_desc':
            queryset = queryset.order_by('-admission_date')
        elif sort_by == 'date_asc':
            queryset = queryset.order_by('admission_date')
        else:
            queryset = queryset.order_by('first_name', 'father_name', 'grandfather_name')

        return queryset.distinct()

    @staticmethod
    def log_audit(request, action, student, changes=None):
        """Creates an immutable audit record for student changes."""
        try:
            actor = request.user if request and request.user.is_authenticated else None
            ip = None
            if request:
                ip = (
                    request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
                    or request.META.get('REMOTE_ADDR')
                )
            AuditLog.objects.create(
                actor=actor,
                action=action,
                entity_name='Student',
                record_id=str(student.admission_number or student.pk),
                ip_address=ip or None,
                changes_json=changes or {},
            )
        except Exception:
            pass


class StudentIDCardService:
    """
    Step 22: Service managing Student ID Card issuance, lifecycle,
    secure QR code generation (zero PII in payload), vector PDF rendering,
    and multi-card batch print sheets.
    """

    @classmethod
    def generate_card_number(cls, student, academic_year):
        """
        Generates a unique, institutional human-readable card number.
        Format: MSS-ID-{YEAR_CODE}-{SEQ:04d} (e.g. MSS-ID-2026-0001).
        """
        year_str = re.sub(r'[^A-Za-z0-9]', '', academic_year.code or academic_year.name)[:6]
        base_prefix = f"MSS-ID-{year_str}"
        seq = StudentIDCard.objects.filter(academic_year=academic_year).count() + 1
        card_num = f"{base_prefix}-{seq:04d}"

        # Guarantee absolute uniqueness
        while StudentIDCard.objects.filter(card_number=card_num).exists():
            seq += 1
            card_num = f"{base_prefix}-{seq:04d}"

        return card_num

    @classmethod
    def get_or_create_id_card(cls, student, academic_year=None, issued_by=None, force_new=False, request=None):
        """
        Retrieves active ID card or issues a new one for the student.
        If force_new=True, replaces existing active card and issues a new card.
        """
        if not academic_year:
            academic_year = AcademicYear.objects.filter(is_current=True).first()
            if not academic_year:
                enrollment = student.enrollments.order_by('-academic_year__start_date').first()
                academic_year = enrollment.academic_year if enrollment else None

        if not academic_year:
            raise ValidationError("Cannot issue ID card: No active or valid academic year found.")

        # Find active enrollment for context
        enrollment = student.enrollments.filter(academic_year=academic_year, status='ACTIVE').first()

        with transaction.atomic():
            existing = StudentIDCard.objects.filter(
                student=student,
                academic_year=academic_year,
                status='ACTIVE'
            ).first()

            if existing and not force_new:
                return existing, False

            if existing and force_new:
                existing.status = 'REPLACED'
                existing.save(update_fields=['status', 'updated_at'])

            card_number = cls.generate_card_number(student, academic_year)
            expiry_date = academic_year.end_date if academic_year and academic_year.end_date else date(date.today().year + 1, 6, 30)

            id_card = StudentIDCard.objects.create(
                student=student,
                enrollment=enrollment,
                academic_year=academic_year,
                card_number=card_number,
                issue_date=date.today(),
                expiry_date=expiry_date,
                status='ACTIVE',
                issued_by=issued_by
            )

            StudentService.log_audit(
                request,
                'ISSUE_ID_CARD',
                student,
                {
                    'card_number': id_card.card_number,
                    'academic_year': academic_year.name,
                    'force_new': force_new
                }
            )

            return id_card, True

    @classmethod
    def batch_generate_id_cards(cls, class_offering=None, grade=None, academic_year=None, issued_by=None, force_new=False, request=None):
        """
        Batch generates student ID cards for an entire classroom or grade.
        Prevents duplicate active cards.
        """
        if not academic_year:
            academic_year = AcademicYear.objects.filter(is_current=True).first()

        enrollments_qs = StudentEnrollment.objects.filter(
            academic_year=academic_year,
            status='ACTIVE',
            student__status='ACTIVE'
        ).select_related('student', 'class_offering__grade', 'class_offering__section', 'class_offering__stream')

        if class_offering:
            enrollments_qs = enrollments_qs.filter(class_offering=class_offering)
        if grade:
            enrollments_qs = enrollments_qs.filter(class_offering__grade=grade)

        created_count = 0
        reused_count = 0
        errors = []

        for enr in enrollments_qs:
            try:
                card, created = cls.get_or_create_id_card(
                    student=enr.student,
                    academic_year=academic_year,
                    issued_by=issued_by,
                    force_new=force_new,
                    request=request
                )
                if created:
                    created_count += 1
                else:
                    reused_count += 1
            except Exception as e:
                errors.append(f"Failed to generate card for {enr.student.full_name} ({enr.student.admission_number}): {str(e)}")

        return {
            'total': enrollments_qs.count(),
            'created': created_count,
            'reused': reused_count,
            'errors': errors
        }

    @classmethod
    def revoke_card(cls, id_card, reason, user=None, request=None):
        """Officially revokes an ID card with timestamp and audit logging."""
        id_card.revoke(reason=reason, user=user)
        StudentService.log_audit(
            request,
            'REVOKE_ID_CARD',
            id_card.student,
            {'card_number': id_card.card_number, 'reason': reason}
        )
        return id_card

    @classmethod
    def reprint_card(cls, id_card, user=None, request=None):
        """Increments reprint count and logs audit event."""
        id_card.reprint_count += 1
        id_card.save(update_fields=['reprint_count', 'updated_at'])
        StudentService.log_audit(
            request,
            'REPRINT_ID_CARD',
            id_card.student,
            {'card_number': id_card.card_number, 'reprint_count': id_card.reprint_count}
        )

    @classmethod
    def get_verification_url(cls, id_card, request=None):
        """Builds verification URL for the card without exposing any student PII."""
        rel_url = reverse('id_card_verify', kwargs={'card_uuid': id_card.card_uuid})
        if request:
            return request.build_absolute_uri(rel_url)
        return rel_url

    @classmethod
    def get_qr_svg(cls, id_card, size=75, request=None):
        """
        Generates vector SVG markup for the secure QR code.
        Zero external APIs, 100% offline Local LAN execution.
        """
        verify_url = cls.get_verification_url(id_card, request=request)
        widget = qr.QrCodeWidget(verify_url)
        bounds = widget.getBounds()
        orig_w = bounds[2] - bounds[0]
        orig_h = bounds[3] - bounds[1]

        d = Drawing(size, size)
        d.transform = (size / orig_w, 0, 0, size / orig_h, 0, 0)
        d.add(widget)

        svg_xml = renderSVG.drawToString(d)
        if '<?xml' in svg_xml:
            svg_xml = svg_xml.split('?>', 1)[-1].strip()
        if '<!DOCTYPE' in svg_xml:
            svg_xml = svg_xml.split(']>', 1)[-1].strip() if ']>' in svg_xml else svg_xml.split('>', 1)[-1].strip()
        return svg_xml

    @classmethod
    def get_card_context(cls, id_card, request=None):
        """Prepares comprehensive view data dictionary for web preview and templates."""
        student = id_card.student
        enrollment = id_card.enrollment or student.enrollments.filter(academic_year=id_card.academic_year).first()
        class_offering = enrollment.class_offering if enrollment else None

        grade_name = class_offering.grade.name if class_offering and class_offering.grade else "—"
        section_name = class_offering.section.name if class_offering and class_offering.section else "—"
        stream_name = class_offering.stream.name if class_offering and class_offering.stream else "General Secondary"

        # Calendar formats
        ay = id_card.academic_year
        eth_year = ay.ethiopian_year_display if hasattr(ay, 'ethiopian_year_display') else ""
        ay_display = f"{ay.name} G.C. ({eth_year})" if eth_year else ay.name

        issued_gc = id_card.issue_date.strftime("%b %d, %Y")
        issued_ec = str(gregorian_to_ethiopian(id_card.issue_date)) if id_card.issue_date else ""

        expiry_gc = id_card.expiry_date.strftime("%b %d, %Y") if id_card.expiry_date else "—"
        expiry_ec = str(gregorian_to_ethiopian(id_card.expiry_date)) if id_card.expiry_date else ""

        qr_svg = cls.get_qr_svg(id_card, size=85, request=request)
        verify_url = cls.get_verification_url(id_card, request=request)

        logo_rel = os.path.join('static', 'images', 'school_logo.png')
        logo_abs = os.path.abspath(logo_rel)

        return {
            'card': id_card,
            'student': student,
            'enrollment': enrollment,
            'class_offering': class_offering,
            'grade_name': grade_name,
            'section_name': section_name,
            'stream_name': stream_name,
            'academic_year': ay,
            'academic_year_display': ay_display,
            'issue_date_gc': issued_gc,
            'issue_date_ec': issued_ec,
            'expiry_date_gc': expiry_gc,
            'expiry_date_ec': expiry_ec,
            'qr_svg': qr_svg,
            'verify_url': verify_url,
            'is_valid': id_card.is_valid,
            'status': id_card.status,
            'status_display': id_card.get_status_display(),
            'logo_exists': os.path.exists(logo_abs),
        }

    @classmethod
    def _draw_id_card_front(cls, c, x, y, id_card, request=None):
        """
        Draws the front side of a CR80 student ID card (153 pt x 243 pt) at canvas coordinates (x, y).
        """
        student = id_card.student
        enrollment = id_card.enrollment or student.enrollments.filter(academic_year=id_card.academic_year).first()
        co = enrollment.class_offering if enrollment else None

        grade_text = f"{co.grade.name} - Sec {co.section.name}" if co else "Secondary"
        stream_text = co.stream.name if co and co.stream else "General Secondary"

        # 1. Outer Card Boundary & Background
        c.saveState()
        c.setStrokeColor(colors.HexColor('#CBD5E1'))
        c.setFillColor(colors.HexColor('#FFFFFF'))
        c.roundRect(x, y, 153, 243, 6, stroke=1, fill=1)

        # 2. Header Navy Band
        c.setFillColor(colors.HexColor('#0F172A'))
        c.rect(x + 1, y + 198, 151, 44, stroke=0, fill=1)

        # Gold Header Accent Bar
        c.setFillColor(colors.HexColor('#D97706'))
        c.rect(x + 1, y + 196, 151, 2, stroke=0, fill=1)

        # 3. School Logo (Left)
        logo_path = os.path.abspath(os.path.join('static', 'images', 'school_logo.png'))
        if os.path.exists(logo_path):
            try:
                c.drawImage(logo_path, x + 6, y + 203, width=32, height=32, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass

        # 4. School Header Typography
        c.setFillColor(colors.HexColor('#FFFFFF'))
        c.setFont('Helvetica-Bold', 7.2)
        c.drawString(x + 42, y + 226, "METTI SECONDARY SCHOOL")

        c.setFillColor(colors.HexColor('#F59E0B'))
        c.setFont('Helvetica-Bold', 5.5)
        c.drawString(x + 42, y + 215, "STUDENT IDENTITY CARD")

        c.setFillColor(colors.HexColor('#94A3B8'))
        c.setFont('Helvetica', 4.5)
        c.drawString(x + 42, y + 205, "Majang Zone, Gambella, Ethiopia")

        # 5. Student Portrait (x + 8, y + 128, w=44, h=54)
        photo_x = x + 8
        photo_y = y + 128
        photo_w = 44
        photo_h = 56

        c.setStrokeColor(colors.HexColor('#CBD5E1'))
        c.setFillColor(colors.HexColor('#F8FAFC'))
        c.rect(photo_x, photo_y, photo_w, photo_h, stroke=1, fill=1)

        photo_rendered = False
        if student.photo and hasattr(student.photo, 'path') and os.path.exists(student.photo.path):
            try:
                c.drawImage(student.photo.path, photo_x, photo_y, width=photo_w, height=photo_h, preserveAspectRatio=True)
                photo_rendered = True
            except Exception:
                photo_rendered = False

        if not photo_rendered:
            # Professional placeholder icon & text
            c.setFillColor(colors.HexColor('#E2E8F0'))
            c.circle(photo_x + (photo_w / 2), photo_y + 36, 11, stroke=0, fill=1)
            c.circle(photo_x + (photo_w / 2), photo_y + 12, 16, stroke=0, fill=1)
            c.setFillColor(colors.HexColor('#64748B'))
            c.setFont('Helvetica-Bold', 5)
            c.drawCentredString(photo_x + (photo_w / 2), photo_y + 6, "NO PHOTO")

        # 6. Student Data Column (x + 58)
        info_x = x + 57
        c.setFillColor(colors.HexColor('#0F172A'))
        c.setFont('Helvetica-Bold', 7.5)
        # Handle long Ethiopian three-part names
        full_name = student.full_name
        if len(full_name) > 20:
            parts = full_name.split()
            line1 = " ".join(parts[:2])
            line2 = " ".join(parts[2:]) if len(parts) > 2 else ""
            c.drawString(info_x, y + 174, line1)
            if line2:
                c.drawString(info_x, y + 165, line2)
        else:
            c.drawString(info_x, y + 172, full_name)

        # Admission Number Badge
        c.setFillColor(colors.HexColor('#EFF6FF'))
        c.setStrokeColor(colors.HexColor('#BFDBFE'))
        c.roundRect(info_x, y + 150, 88, 12, 2, stroke=1, fill=1)
        c.setFillColor(colors.HexColor('#1E3A8A'))
        c.setFont('Helvetica-Bold', 6.5)
        c.drawString(info_x + 4, y + 153.5, f"ID: {student.admission_number}")

        # Grade & Section
        c.setFillColor(colors.HexColor('#334155'))
        c.setFont('Helvetica-Bold', 6.2)
        c.drawString(info_x, y + 138, grade_text)

        # Stream
        c.setFont('Helvetica', 5.6)
        c.setFillColor(colors.HexColor('#64748B'))
        c.drawString(info_x, y + 128, f"Stream: {stream_text}")

        # Academic Year
        c.drawString(info_x, y + 118, f"Year: {id_card.academic_year.name} G.C.")

        # 7. Divider Line
        c.setStrokeColor(colors.HexColor('#E2E8F0'))
        c.line(x + 8, y + 110, x + 145, y + 110)

        # 8. Bottom Information & QR Code Area
        c.setFillColor(colors.HexColor('#475569'))
        c.setFont('Helvetica-Bold', 5.2)
        c.drawString(x + 8, y + 96, "CARD CREDENTIAL")

        c.setFont('Helvetica', 5.0)
        c.drawString(x + 8, y + 84, f"Card No: {id_card.card_number}")
        c.drawString(x + 8, y + 74, f"Issued: {id_card.issue_date.strftime('%d/%m/%Y')}")
        if id_card.expiry_date:
            c.drawString(x + 8, y + 64, f"Expires: {id_card.expiry_date.strftime('%d/%m/%Y')}")

        # Status Pill
        if id_card.is_valid:
            c.setFillColor(colors.HexColor('#DCFCE7'))
            c.setStrokeColor(colors.HexColor('#86EFAC'))
            c.roundRect(x + 8, y + 46, 75, 12, 2, stroke=1, fill=1)
            c.setFillColor(colors.HexColor('#15803D'))
            c.setFont('Helvetica-Bold', 5.8)
            c.drawString(x + 12, y + 50, "VALID CREDENTIAL")
        else:
            c.setFillColor(colors.HexColor('#FEE2E2'))
            c.setStrokeColor(colors.HexColor('#FCA5A5'))
            c.roundRect(x + 8, y + 46, 75, 12, 2, stroke=1, fill=1)
            c.setFillColor(colors.HexColor('#B91C1C'))
            c.setFont('Helvetica-Bold', 5.8)
            c.drawString(x + 12, y + 50, f"{id_card.get_status_display().upper()}")

        # 9. Vector QR Code (x + 92, y + 14, w=50, h=50)
        verify_url = cls.get_verification_url(id_card, request=request)
        widget = qr.QrCodeWidget(verify_url)
        bounds = widget.getBounds()
        orig_w = bounds[2] - bounds[0]
        orig_h = bounds[3] - bounds[1]

        qr_size = 50
        d = Drawing(qr_size, qr_size)
        d.transform = (qr_size / orig_w, 0, 0, qr_size / orig_h, 0, 0)
        d.add(widget)

        renderPDF.draw(d, c, x + 94, y + 16)
        c.setFillColor(colors.HexColor('#64748B'))
        c.setFont('Helvetica', 4.5)
        c.drawCentredString(x + 119, y + 8, "Scan to Verify")

        # LAN Identifier
        c.drawString(x + 8, y + 8, "Offline LAN ID Card")

        c.restoreState()

    @classmethod
    def _draw_id_card_back(cls, c, x, y, id_card):
        """
        Draws the back side of a CR80 student ID card (153 pt x 243 pt) at canvas coordinates (x, y).
        """
        c.saveState()
        c.setStrokeColor(colors.HexColor('#CBD5E1'))
        c.setFillColor(colors.HexColor('#FFFFFF'))
        c.roundRect(x, y, 153, 243, 6, stroke=1, fill=1)

        # Header Navy Band
        c.setFillColor(colors.HexColor('#0F172A'))
        c.rect(x + 1, y + 218, 151, 24, stroke=0, fill=1)
        c.setFillColor(colors.HexColor('#D97706'))
        c.rect(x + 1, y + 216, 151, 2, stroke=0, fill=1)

        c.setFillColor(colors.HexColor('#FFFFFF'))
        c.setFont('Helvetica-Bold', 6.5)
        c.drawCentredString(x + 76.5, y + 226, "TERMS OF IDENTIFICATION")

        # Notice Terms Box
        c.setFillColor(colors.HexColor('#334155'))
        c.setFont('Helvetica', 5.2)

        terms = [
            "1. This credential is the official property of",
            "   Metti Secondary School.",
            "2. The student must carry this card at all times",
            "   when on campus or at official activities.",
            "3. Card is non-transferable and must be presented",
            "   upon request to authorized school personnel.",
            "4. Report loss or theft immediately to the",
            "   Registrar Office.",
            "5. If found, please return to:",
            "   Metti Secondary School Administration,",
            "   Godere Woreda, Majang Zone, Gambella, Ethiopia."
        ]

        text_y = y + 198
        for line in terms:
            c.drawString(x + 10, text_y, line)
            text_y -= 8

        # Divider
        c.setStrokeColor(colors.HexColor('#E2E8F0'))
        c.line(x + 10, y + 95, x + 143, y + 95)

        # Signature & Seal Area
        c.setFillColor(colors.HexColor('#0F172A'))
        c.setFont('Helvetica-Bold', 5.5)
        c.drawString(x + 10, y + 80, "AUTHORIZED BY:")

        c.setFont('Helvetica', 5.0)
        c.drawString(x + 10, y + 42, "___________________________")
        c.drawString(x + 10, y + 33, "School Principal / Registrar")
        c.drawString(x + 10, y + 24, "Metti Secondary School")

        # Official Seal Box
        c.setStrokeColor(colors.HexColor('#CBD5E1'))
        c.setFillColor(colors.HexColor('#F8FAFC'))
        c.rect(x + 95, y + 26, 48, 48, stroke=1, fill=1)
        c.setFillColor(colors.HexColor('#94A3B8'))
        c.setFont('Helvetica-Bold', 5.0)
        c.drawCentredString(x + 119, y + 54, "OFFICIAL")
        c.drawCentredString(x + 119, y + 44, "SCHOOL")
        c.drawCentredString(x + 119, y + 34, "SEAL")

        # Footer
        c.setFillColor(colors.HexColor('#64748B'))
        c.setFont('Helvetica', 4.5)
        c.drawCentredString(x + 76.5, y + 10, "Smart School Management System (SSMS) • Local LAN")

        c.restoreState()

    @classmethod
    def export_single_card_pdf(cls, id_card, filename=None, request=None):
        """
        Generates a 2-page CR80 vector PDF (Front & Back) for an individual student ID card.
        """
        buf = io.BytesIO()
        card_w, card_h = 153, 243
        c = canvas.Canvas(buf, pagesize=(card_w, card_h))

        # Page 1: Front
        cls._draw_id_card_front(c, 0, 0, id_card, request=request)
        c.showPage()

        # Page 2: Back
        cls._draw_id_card_back(c, 0, 0, id_card)
        c.showPage()

        c.save()
        buf.seek(0)

        safe_adm = id_card.student.admission_number.replace('/', '_').replace('\\', '_')
        if not filename:
            filename = f"StudentID_{safe_adm}_{id_card.card_number}.pdf"

        response = HttpResponse(buf.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @classmethod
    def export_batch_cards_pdf(cls, id_cards, filename=None, request=None):
        """
        Generates a multi-card printable PDF sheet on standard Letter (612 x 792 pt).
        Layout: 4 cards per page (2 columns x 2 rows) with alignment guides and crop marks.
        """
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=letter)
        page_w, page_h = letter # 612 x 792

        # 4 cards per page (2 cols x 2 rows)
        card_w = 153
        card_h = 243
        gap_x = 40
        gap_y = 35

        total_grid_w = (2 * card_w) + gap_x # 346 pt
        total_grid_h = (2 * card_h) + gap_y # 521 pt

        start_x = (page_w - total_grid_w) / 2 # ~133 pt
        start_y = page_h - ((page_h - total_grid_h) / 2) - card_h # Top row y

        col_count = 2
        row_count = 2
        cards_per_page = col_count * row_count

        cards_list = list(id_cards)
        for idx, card in enumerate(cards_list):
            page_idx = idx % cards_per_page
            col = page_idx % col_count
            row = page_idx // col_count

            card_x = start_x + col * (card_w + gap_x)
            card_y = start_y - row * (card_h + gap_y)

            # Draw alignment cut crop marks around card
            c.saveState()
            c.setStrokeColor(colors.HexColor('#94A3B8'))
            c.setLineWidth(0.5)
            # Top-left corner
            c.line(card_x - 6, card_y + card_h, card_x - 1, card_y + card_h)
            c.line(card_x, card_y + card_h + 1, card_x, card_y + card_h + 6)
            # Top-right corner
            c.line(card_x + card_w + 1, card_y + card_h, card_x + card_w + 6, card_y + card_h)
            c.line(card_x + card_w, card_y + card_h + 1, card_x + card_w, card_y + card_h + 6)
            # Bottom-left corner
            c.line(card_x - 6, card_y, card_x - 1, card_y)
            c.line(card_x, card_y - 1, card_x, card_y - 6)
            # Bottom-right corner
            c.line(card_x + card_w + 1, card_y, card_x + card_w + 6, card_y)
            c.line(card_x + card_w, card_y - 1, card_x + card_w, card_y - 6)
            c.restoreState()

            # Draw card
            cls._draw_id_card_front(c, card_x, card_y, card, request=request)

            # If last card of the page or last card overall, emit page
            if (page_idx == cards_per_page - 1) or (idx == len(cards_list) - 1):
                # Page footer
                c.saveState()
                c.setFont('Helvetica', 8)
                c.setFillColor(colors.HexColor('#64748B'))
                c.drawCentredString(page_w / 2, 25, f"Metti Secondary School • Student ID Card Print Sheet • Page {(idx // cards_per_page) + 1}")
                c.restoreState()
                c.showPage()

        c.save()
        buf.seek(0)

        if not filename:
            filename = f"StudentID_Batch_{timezone.now():%Y%m%d_%H%M%S}.pdf"

        response = HttpResponse(buf.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class CertificateService:
    """
    Step 23: Service managing Student Transfer & Leaving Certificate workflows,
    multi-level approval state machine (DRAFT -> SUBMITTED -> APPROVED -> ISSUED),
    institutional reference numbering, audit logging, and high-fidelity A4 PDF compilation.
    """

    @classmethod
    def generate_certificate_number(cls, certificate_type, academic_year=None):
        """
        Generates unique, sequential institutional reference number.
        Format:
          - Transfer: MSS-TC-{YEAR}-{SEQ:04d} (e.g. MSS-TC-2016-0001)
          - Leaving:  MSS-LC-{YEAR}-{SEQ:04d} (e.g. MSS-LC-2016-0001)
        """
        if not academic_year:
            academic_year = AcademicYear.objects.filter(is_current=True).first() or AcademicYear.objects.order_by('-start_date').first()
        
        raw_year = (academic_year.code if academic_year else '') or (academic_year.name if academic_year else '') or ''
        match = re.search(r'\d{4}', raw_year)
        year_str = match.group(0) if match else str(date.today().year)

        prefix = "MSS-TC" if certificate_type == 'TRANSFER' else "MSS-LC"
        base_prefix = f"{prefix}-{year_str}"
        seq = StudentCertificate.objects.filter(certificate_type=certificate_type, academic_year=academic_year).count() + 1
        cert_num = f"{base_prefix}-{seq:04d}"

        while StudentCertificate.objects.filter(certificate_number=cert_num).exists():
            seq += 1
            cert_num = f"{base_prefix}-{seq:04d}"

        return cert_num

    @classmethod
    def create_certificate_request(cls, student, certificate_type, academic_year=None,
                                   last_grade=None, section_name='', stream_name='',
                                   effective_date=None, destination_school='',
                                   reason='', academic_standing='', conduct='Good',
                                   remarks='', requested_by=None, request=None):
        """
        Creates a new StudentCertificate request.
        Auto-populates academic context from active or latest student enrollment if omitted.
        Enforces unique active certificate constraint per student/type/year.
        """
        if certificate_type == 'TRANSFER' and not (destination_school and destination_school.strip()):
            raise ValidationError("Destination school is required for Student Transfer Certificates.")

        if not academic_year:
            academic_year = AcademicYear.objects.filter(is_current=True).first()
            if not academic_year:
                enrollment = student.enrollments.order_by('-academic_year__start_date').first()
                academic_year = enrollment.academic_year if enrollment else None

        if not academic_year:
            raise ValidationError("Cannot create certificate request: No active academic year found.")

        # Check existing active certificate
        existing_active = StudentCertificate.objects.filter(
            student=student,
            certificate_type=certificate_type,
            academic_year=academic_year,
            status__in=['DRAFT', 'SUBMITTED', 'APPROVED', 'ISSUED']
        ).first()

        if existing_active:
            raise ValidationError(
                f"Student already has an active {existing_active.get_certificate_type_display()} "
                f"({existing_active.status}) for {academic_year.name}."
            )

        # Find latest/active enrollment
        enrollment = student.enrollments.filter(academic_year=academic_year).first()
        if not enrollment:
            enrollment = student.enrollments.order_by('-academic_year__start_date').first()

        if not last_grade:
            if enrollment and enrollment.class_offering and enrollment.class_offering.grade:
                last_grade = enrollment.class_offering.grade
            else:
                last_grade = Grade.objects.order_by('-level').first()

        if not section_name and enrollment and enrollment.class_offering and enrollment.class_offering.section:
            section_name = f"Section {enrollment.class_offering.section.name}"

        if not stream_name and enrollment and enrollment.class_offering and enrollment.class_offering.stream:
            stream_name = enrollment.class_offering.stream.name

        if not effective_date:
            effective_date = date.today()

        with transaction.atomic():
            certificate = StudentCertificate.objects.create(
                student=student,
                certificate_type=certificate_type,
                academic_year=academic_year,
                enrollment=enrollment,
                last_grade=last_grade,
                section_name=section_name,
                stream_name=stream_name,
                admission_date=student.admission_date,
                effective_date=effective_date,
                destination_school=(destination_school or '').strip(),
                reason=(reason or '').strip(),
                academic_standing=(academic_standing or '').strip(),
                conduct=(conduct or '').strip() or 'Good',
                remarks=(remarks or '').strip(),
                status='DRAFT',
                requested_by=requested_by
            )

            StudentService.log_audit(
                request,
                'CREATE_CERTIFICATE_REQUEST',
                student,
                {
                    'certificate_id': certificate.pk,
                    'type': certificate_type,
                    'academic_year': academic_year.name,
                }
            )

            return certificate

    @classmethod
    def submit_certificate(cls, certificate, user=None, submitted_by=None, request=None):
        """Submits a draft certificate for administrative and principal review."""
        effective_user = user or submitted_by
        if certificate.status != 'DRAFT':
            raise ValidationError(f"Cannot submit certificate in status '{certificate.status}'.")

        certificate.status = 'SUBMITTED'
        certificate.reviewed_by = effective_user
        certificate.reviewed_at = timezone.now()
        certificate.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])

        StudentService.log_audit(
            request,
            'SUBMIT_CERTIFICATE_REQUEST',
            certificate.student,
            {'certificate_id': certificate.pk, 'status': 'SUBMITTED'}
        )
        return certificate

    @classmethod
    def approve_certificate(cls, certificate, user=None, approved_by=None, remarks='', request=None):
        """
        Principal or authorized administrator approval.
        """
        effective_user = user or approved_by
        if not effective_user:
            raise PermissionDenied("Approving user is required.")

        is_approver = effective_user.is_superuser or (effective_user.role and effective_user.role.code in ['PRINCIPAL', 'ADMIN'])
        if not is_approver:
            raise PermissionDenied("Only the School Principal or Administrator may approve certificates.")

        if certificate.status not in ['DRAFT', 'SUBMITTED']:
            raise ValidationError(f"Certificate in status '{certificate.status}' cannot be approved.")

        with transaction.atomic():
            certificate.status = 'APPROVED'
            certificate.approved_by = effective_user
            certificate.approved_at = timezone.now()
            certificate.approval_remarks = (remarks or '').strip()
            certificate.save(update_fields=['status', 'approved_by', 'approved_at', 'approval_remarks', 'updated_at'])

            StudentService.log_audit(
                request,
                'APPROVE_CERTIFICATE',
                certificate.student,
                {'certificate_id': certificate.pk, 'approved_by': effective_user.username, 'remarks': remarks}
            )
        return certificate

    @classmethod
    def reject_certificate(cls, certificate, user=None, rejected_by=None, reason='', request=None):
        """Rejects a certificate request with mandatory justification."""
        effective_user = user or rejected_by
        if not effective_user:
            raise PermissionDenied("Rejecting user is required.")

        is_approver = effective_user.is_superuser or (effective_user.role and effective_user.role.code in ['PRINCIPAL', 'ADMIN'])
        if not is_approver:
            raise PermissionDenied("Only the School Principal or Administrator may reject certificate requests.")

        if not reason or not reason.strip():
            raise ValidationError("A clear justification is required to reject a certificate request.")

        if certificate.status not in ['DRAFT', 'SUBMITTED']:
            raise ValidationError(f"Cannot reject certificate in status '{certificate.status}'.")

        with transaction.atomic():
            certificate.status = 'REJECTED'
            certificate.rejection_reason = reason.strip()
            certificate.save(update_fields=['status', 'rejection_reason', 'updated_at'])

            StudentService.log_audit(
                request,
                'REJECT_CERTIFICATE',
                certificate.student,
                {'certificate_id': certificate.pk, 'rejected_by': effective_user.username, 'reason': reason}
            )
        return certificate

    @classmethod
    def issue_certificate(cls, certificate, user=None, issued_by=None, update_student_status=True, request=None):
        """
        Officially issues the approved certificate.
        Assigns reference number and issue date.
        Optionally updates student master status (e.g. TRANSFERRED or WITHDRAWN/GRADUATED)
        while strictly preserving all historical enrollments and academic records.
        """
        effective_user = user or issued_by
        if certificate.status != 'APPROVED':
            raise ValidationError("Only approved certificates can be officially issued.")

        with transaction.atomic():
            if not certificate.certificate_number:
                certificate.certificate_number = cls.generate_certificate_number(
                    certificate.certificate_type,
                    certificate.academic_year
                )

            certificate.status = 'ISSUED'
            certificate.issue_date = date.today()
            certificate.issued_by = effective_user
            certificate.save(update_fields=['status', 'certificate_number', 'issue_date', 'issued_by', 'updated_at'])

            # Update student status if requested, preserving all records
            if update_student_status:
                student = certificate.student
                if certificate.certificate_type == 'TRANSFER':
                    student.status = 'TRANSFERRED'
                elif certificate.certificate_type == 'LEAVING':
                    grade_val = getattr(certificate.last_grade, 'level', None)
                    reason_lower = certificate.reason.lower()
                    standing_lower = certificate.academic_standing.lower()
                    if grade_val == 12 or 'graduat' in reason_lower or 'completed grade 12' in standing_lower:
                        student.status = 'GRADUATED'
                    else:
                        student.status = 'WITHDRAWN'
                student.save(update_fields=['status'])

            StudentService.log_audit(
                request,
                'ISSUE_CERTIFICATE',
                certificate.student,
                {
                    'certificate_id': certificate.pk,
                    'certificate_number': certificate.certificate_number,
                    'type': certificate.certificate_type,
                    'issued_by': effective_user.username if effective_user else 'System'
                }
            )

        return certificate

    @classmethod
    def revoke_certificate(cls, certificate, user=None, revoked_by=None, reason='', request=None):
        """Officially revokes an issued or approved certificate with mandatory reason."""
        effective_user = user or revoked_by
        if not reason or not reason.strip():
            raise ValidationError("A mandatory reason is required to revoke a certificate.")

        with transaction.atomic():
            certificate.status = 'REVOKED'
            certificate.revoked_by = effective_user
            certificate.revoked_at = timezone.now()
            certificate.revocation_reason = reason.strip()
            certificate.save(update_fields=['status', 'revoked_by', 'revoked_at', 'revocation_reason', 'updated_at'])

            StudentService.log_audit(
                request,
                'REVOKE_CERTIFICATE',
                certificate.student,
                {
                    'certificate_id': certificate.pk,
                    'certificate_number': certificate.certificate_number,
                    'revoked_by': effective_user.username if effective_user else 'System',
                    'reason': reason
                }
            )

        return certificate

    @classmethod
    def format_dual_date(cls, date_val):
        """Formats Gregorian and Ethiopian dates cleanly (e.g. 'Oct 15, 2023 (Tikimt 05, 2016 E.C.)')."""
        if not date_val:
            return "N/A"
        try:
            eth_date = EthiopianDate.from_gregorian(date_val)
            return f"{date_val.strftime('%b %d, %Y')} ({eth_date.format('full_en')})"
        except Exception:
            return date_val.strftime('%b %d, %Y')

    @classmethod
    def export_certificate_pdf(cls, certificate, request=None, filename=None):
        """
        Compiles a high-fidelity, professional English-only A4 PDF certificate.
        Includes ornate borders, school branding, official Ethiopian & Gregorian dates,
        verified academic particulars, and registrar/principal signature and stamp blocks.
        """
        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        c.setTitle(f"Certificate_{certificate.certificate_number or certificate.pk}")

        page_w, page_h = A4  # 595.27 x 841.89

        # Colors
        navy = colors.HexColor('#1E3A8A')
        deep_gold = colors.HexColor('#D97706')
        charcoal = colors.HexColor('#0F172A')
        slate = colors.HexColor('#334155')
        light_slate = colors.HexColor('#64748B')
        border_bg = colors.HexColor('#F8FAFC')
        table_border = colors.HexColor('#CBD5E1')
        zebra_bg = colors.HexColor('#F1F5F9')

        # 1. Background Fill & Double Frame Border
        # Outer border
        c.saveState()
        c.setStrokeColor(navy)
        c.setLineWidth(2.5)
        c.rect(22, 22, page_w - 44, page_h - 44)

        # Inner border
        c.setStrokeColor(deep_gold)
        c.setLineWidth(1.0)
        c.rect(27, 27, page_w - 54, page_h - 54)

        # Corner Corner Accents
        c.setFillColor(deep_gold)
        corner_size = 8
        c.rect(27, 27, corner_size, corner_size, fill=1, stroke=0)
        c.rect(page_w - 27 - corner_size, 27, corner_size, corner_size, fill=1, stroke=0)
        c.rect(27, page_h - 27 - corner_size, corner_size, corner_size, fill=1, stroke=0)
        c.rect(page_w - 27 - corner_size, page_h - 27 - corner_size, corner_size, corner_size, fill=1, stroke=0)
        c.restoreState()

        # 2. Header & Branding
        logo_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'school_logo.png')
        if os.path.exists(logo_path):
            try:
                c.drawImage(logo_path, 42, page_h - 108, width=64, height=64, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass

        c.saveState()
        c.setFont('Helvetica-Bold', 19)
        c.setFillColor(navy)
        c.drawCentredString(page_w / 2, page_h - 58, "METTI SECONDARY SCHOOL")

        c.setFont('Helvetica-Bold', 10)
        c.setFillColor(slate)
        c.drawCentredString(page_w / 2, page_h - 73, "Godere Woreda, Majang Zone, Gambella Region, Ethiopia")

        c.setFont('Helvetica', 8.5)
        c.setFillColor(light_slate)
        c.drawCentredString(page_w / 2, page_h - 87, "Federal Democratic Republic of Ethiopia • Ministry of Education")
        c.restoreState()

        # Decorative Horizontal Divider
        c.saveState()
        c.setStrokeColor(deep_gold)
        c.setLineWidth(1.5)
        c.line(42, page_h - 100, page_w - 42, page_h - 100)
        c.restoreState()

        # 3. Certificate Title Banner
        is_transfer = certificate.certificate_type == 'TRANSFER'
        title_text = "OFFICIAL STUDENT TRANSFER CERTIFICATE" if is_transfer else "OFFICIAL STUDENT LEAVING CERTIFICATE"

        c.saveState()
        # Title background pill
        title_w = 420
        title_h = 28
        title_x = (page_w - title_w) / 2
        title_y = page_h - 138
        c.setFillColor(navy)
        c.roundRect(title_x, title_y, title_w, title_h, 4, fill=1, stroke=0)

        c.setFont('Helvetica-Bold', 13)
        c.setFillColor(colors.white)
        c.drawCentredString(page_w / 2, title_y + 8, title_text)
        c.restoreState()

        # 4. Reference Number & Issue Date Subheader
        ref_num = certificate.certificate_number or f"DRAFT-REF-{certificate.pk}"
        issue_d = certificate.issue_date or date.today()
        issue_str = cls.format_dual_date(issue_d)

        c.saveState()
        c.setFont('Helvetica-Bold', 9.5)
        c.setFillColor(navy)
        c.drawString(45, page_h - 156, f"Reference No: {ref_num}")

        c.setFont('Helvetica-Bold', 9.5)
        c.setFillColor(charcoal)
        c.drawRightString(page_w - 45, page_h - 156, f"Issue Date: {issue_str}")
        c.restoreState()

        # Status Watermark if not officially issued
        if certificate.status != 'ISSUED':
            c.saveState()
            c.setFont('Helvetica-Bold', 46)
            c.setFillColor(colors.HexColor('#DC2626'), alpha=0.15)
            c.translate(page_w / 2, page_h / 2)
            c.rotate(35)
            c.drawCentredString(0, 0, f"*** {certificate.get_status_display().upper()} ***")
            c.restoreState()

        # 5. Formal Certification Paragraph
        c.saveState()
        c.setFont('Helvetica', 10)
        c.setFillColor(charcoal)
        intro_text = (
            "This is to officially certify that the student whose particulars and academic standing are set forth below "
            "was a duly registered student of Metti Secondary School, Godere Woreda, Majang Zone:"
        )
        c.drawString(45, page_h - 176, intro_text)
        c.restoreState()

        # 6. Structured Particulars Table
        table_top = page_h - 192
        row_height = 24
        label_w = 175
        val_w = page_w - 90 - label_w
        table_x = 45

        # Prepare field rows
        student = certificate.student
        dob_str = cls.format_dual_date(student.date_of_birth) if student.date_of_birth else "Not Recorded"
        adm_date_str = cls.format_dual_date(certificate.admission_date) if certificate.admission_date else "Not Recorded"
        eff_date_str = cls.format_dual_date(certificate.effective_date) if certificate.effective_date else "Not Recorded"

        particulars = [
            ("1. Full Student Name:", student.full_name),
            ("2. Student Admission Number:", student.admission_number),
            ("3. Gender:", "Male" if student.gender == 'M' else "Female"),
            ("4. Date of Birth:", dob_str),
            ("5. Date of Admission:", adm_date_str),
            ("6. Academic Year of Attendance:", certificate.academic_year.name),
            ("7. Last Attended Grade & Section:", f"{certificate.last_grade.name} {(' - ' + certificate.section_name) if certificate.section_name else ''}"),
            ("8. Academic Curriculum Stream:", certificate.stream_name or "General Secondary"),
            ("9. Effective Date of " + ("Transfer:" if is_transfer else "Leaving:"), eff_date_str),
        ]

        if is_transfer:
            particulars.append(("10. Destination School:", certificate.destination_school or "Not Specified / As Requested"))
            particulars.append(("11. Reason for Transfer:", certificate.reason or "Family relocation / Official school transfer"))
        else:
            particulars.append(("10. Approved Reason for Leaving:", certificate.reason or "Official school completion / departure"))

        particulars.append(("11. Verified Academic Standing:", certificate.academic_standing or "In Good Standing"))
        particulars.append(("12. General Conduct & Character:", certificate.conduct or "Good"))

        if certificate.remarks:
            particulars.append(("13. Official Remarks:", certificate.remarks))

        # Render Rows
        c.saveState()
        for idx, (label, val) in enumerate(particulars):
            y = table_top - (idx * row_height)

            # Alternate row background
            if idx % 2 == 0:
                c.setFillColor(zebra_bg)
                c.rect(table_x, y - 6, page_w - 90, row_height, fill=1, stroke=0)

            # Border line under row
            c.setStrokeColor(table_border)
            c.setLineWidth(0.5)
            c.line(table_x, y - 6, table_x + (page_w - 90), y - 6)

            # Label
            c.setFont('Helvetica-Bold', 8.5)
            c.setFillColor(navy)
            c.drawString(table_x + 8, y + 2, label)

            # Value
            c.setFont('Helvetica', 8.5)
            c.setFillColor(charcoal)
            val_display = str(val)[:75] + ("..." if len(str(val)) > 75 else "")
            c.drawString(table_x + label_w + 10, y + 2, val_display)

        # Outer box for table
        total_table_height = len(particulars) * row_height
        c.setStrokeColor(navy)
        c.setLineWidth(1)
        c.rect(table_x, table_top - total_table_height + (row_height - 6), page_w - 90, total_table_height, fill=0, stroke=1)
        c.restoreState()

        # 7. Institutional Certification & Dues Cleared Statement
        cert_statement_y = table_top - total_table_height - 10
        c.saveState()
        c.setFont('Helvetica-Oblique', 8)
        c.setFillColor(slate)
        statement_1 = (
            "Institutional Clearance Certification: The above-named student has cleared all school property, library books, "
            "and laboratory equipment, and bears no outstanding obligations to Metti Secondary School as of the departure date."
        )
        statement_2 = (
            "Official Notice: This certificate is issued under the authority of Metti Secondary School administration. "
            "Any alteration, erasure, or unauthorized amendment renders this document completely void."
        )
        c.drawString(45, cert_statement_y, statement_1)
        c.drawString(45, cert_statement_y - 12, statement_2)
        c.restoreState()

        # 8. Signatures & Official Stamp Tri-Block
        sig_y = cert_statement_y - 55

        # Block 1: Prepared by Registrar
        c.saveState()
        c.setStrokeColor(slate)
        c.setLineWidth(0.8)
        c.line(45, sig_y + 16, 195, sig_y + 16)
        c.setFont('Helvetica-Bold', 8.5)
        c.setFillColor(navy)
        c.drawCentredString(120, sig_y + 4, "Prepared & Verified by")
        c.setFont('Helvetica', 7.5)
        c.setFillColor(slate)
        c.drawCentredString(120, sig_y - 8, "Registrar Office • Signature & Date")
        if certificate.issued_by:
            c.setFont('Helvetica-Oblique', 7)
            c.setFillColor(light_slate)
            c.drawCentredString(120, sig_y - 20, f"Officer: {certificate.issued_by.get_full_name() or certificate.issued_by.username}")

        # Block 2: Official Stamp Box
        stamp_box_w = 110
        stamp_box_h = 60
        stamp_box_x = (page_w - stamp_box_w) / 2
        stamp_box_y = sig_y - 28
        c.setStrokeColor(deep_gold)
        c.setLineWidth(1)
        c.rect(stamp_box_x, stamp_box_y, stamp_box_w, stamp_box_h, fill=0, stroke=1)
        c.setFont('Helvetica-Bold', 7)
        c.setFillColor(deep_gold)
        c.drawCentredString(page_w / 2, stamp_box_y + stamp_box_h - 12, "OFFICIAL SCHOOL SEAL")
        c.setFont('Helvetica', 6.5)
        c.setFillColor(light_slate)
        c.drawCentredString(page_w / 2, stamp_box_y + 10, "Metti Secondary School")

        # Block 3: Approved by Principal
        c.setStrokeColor(slate)
        c.setLineWidth(0.8)
        c.line(page_w - 195, sig_y + 16, page_w - 45, sig_y + 16)
        c.setFont('Helvetica-Bold', 8.5)
        c.setFillColor(navy)
        c.drawCentredString(page_w - 120, sig_y + 4, "Approved & Authorized by")
        c.setFont('Helvetica', 7.5)
        c.setFillColor(slate)
        c.drawCentredString(page_w - 120, sig_y - 8, "School Principal • Signature & Date")
        if certificate.approved_by:
            c.setFont('Helvetica-Oblique', 7)
            c.setFillColor(light_slate)
            c.drawCentredString(page_w - 120, sig_y - 20, f"Principal: {certificate.approved_by.get_full_name() or certificate.approved_by.username}")

        c.restoreState()

        # 9. Bottom Archive & Verification Footer
        c.saveState()
        c.setFont('Helvetica', 7)
        c.setFillColor(light_slate)
        c.drawCentredString(
            page_w / 2,
            34,
            f"Metti Secondary School • Smart School Management System (SSMS) • Offline Local Archive • Verification ID: {certificate.certificate_uuid}"
        )
        c.restoreState()

        c.showPage()
        c.save()
        buf.seek(0)

        if not filename:
            cert_code = "TC" if is_transfer else "LC"
            adm_clean = re.sub(r'[^A-Za-z0-9]', '_', certificate.student.admission_number)
            filename = f"Certificate_{cert_code}_{adm_clean}_{timezone.now():%Y%m%d}.pdf"

        response = HttpResponse(buf.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

