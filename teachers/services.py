"""
Teacher Management Service Layer for SSMS.

Handles:
  - Atomic Teacher / Employee ID generation and validation
  - Secure file upload validation for teacher portraits
  - Role-based teacher directory queries and filtering
  - Subject and Class assignment workflows
  - Comprehensive audit logging for staff management actions
"""

import os
import re
from datetime import date
from PIL import Image

from django.db import transaction
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.conf import settings

from teachers.models import Teacher, TeacherAssignment
from academics.models import AcademicYear, Grade, Section, Stream, Subject, ClassOffering
from core.models import AuditLog


class TeacherIDService:
    """
    Manages unique, sequential, and configurable teacher identification numbers.
    Format: EMP/{YEAR}/{SEQUENCE} (e.g. EMP/2026/0001) or EMP-XXXX.
    Avoids race conditions using database transactions and atomic sequence checks.
    """
    DEFAULT_PREFIX = getattr(settings, 'TEACHER_ID_PREFIX', 'EMP')
    PATTERN = re.compile(r'^[A-Za-z0-9]+[/-][0-9A-Za-z/-]+$')

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
    def generate_next_teacher_id(cls, academic_year=None, prefix=None):
        """
        Generates the next sequential unique teacher employee ID.
        Runs inside an atomic transaction to ensure safety under concurrent submissions.
        """
        prefix = prefix or cls.DEFAULT_PREFIX
        year = cls.get_year_string(academic_year)
        year_prefix = f"{prefix}/{year}/"

        with transaction.atomic():
            existing_ids = (
                Teacher.objects.filter(employee_id__startswith=year_prefix)
                .values_list('employee_id', flat=True)
            )

            max_seq = 0
            for eid in existing_ids:
                try:
                    parts = eid.split('/')
                    if len(parts) >= 3 and parts[-1].isdigit():
                        seq = int(parts[-1])
                        if seq > max_seq:
                            max_seq = seq
                except (ValueError, IndexError):
                    continue

            # Fallback check for alternate formats (e.g. EMP-1001) if no matching year prefix
            if max_seq == 0:
                alt_existing = Teacher.objects.filter(employee_id__startswith=f"{prefix}-").values_list('employee_id', flat=True)
                for eid in alt_existing:
                    m = re.search(r'(\d+)$', eid)
                    if m:
                        try:
                            val = int(m.group(1))
                            if val > max_seq:
                                max_seq = val
                        except ValueError:
                            pass

            next_seq = max_seq + 1
            proposed_id = f"{year_prefix}{next_seq:04d}"

            # Safety loop to guarantee uniqueness
            while Teacher.objects.filter(employee_id=proposed_id).exists():
                next_seq += 1
                proposed_id = f"{year_prefix}{next_seq:04d}"

            return proposed_id

    @classmethod
    def validate_teacher_id(cls, teacher_id, current_instance=None):
        """Validates format and checks uniqueness of teacher employee ID."""
        if not teacher_id:
            raise ValidationError("Teacher ID is required.")

        teacher_id = teacher_id.strip()

        if len(teacher_id) < 3 or len(teacher_id) > 50:
            raise ValidationError("Teacher ID must be between 3 and 50 characters long.")

        if not cls.PATTERN.match(teacher_id):
            raise ValidationError(
                "Teacher ID format invalid. Use alphanumeric characters separated by '/' or '-' (e.g. EMP/2026/0001 or EMP-1001)."
            )

        query = Teacher.objects.filter(employee_id=teacher_id)
        if current_instance and current_instance.pk:
            query = query.exclude(pk=current_instance.pk)

        if query.exists():
            raise ValidationError(f"Teacher ID '{teacher_id}' is already registered in the system.")

        return teacher_id


class FileUploadSecurityService:
    """
    Validates uploaded teacher portrait files to prevent remote execution,
    malformed binary exploits, and excessive file size attacks.
    """
    MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB
    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.jfif', '.bmp'}
    ALLOWED_CONTENT_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/bmp'}

    @classmethod
    def validate_image_file(cls, uploaded_file):
        """
        Runs rigorous checks on uploaded image file:
        1. Checks maximum file size (5MB).
        2. Validates filename extension.
        3. Inspects real binary header via Pillow Image.open.
        """
        if not uploaded_file:
            return None

        # 1. Size check
        if uploaded_file.size > cls.MAX_FILE_SIZE_BYTES:
            max_mb = cls.MAX_FILE_SIZE_BYTES // (1024 * 1024)
            raise ValidationError(f"File size exceeds the {max_mb}MB limit. Please upload a smaller photo.")

        # 2. Extension check
        ext = os.path.splitext(uploaded_file.name)[1].lower()
        if ext not in cls.ALLOWED_EXTENSIONS:
            allowed = ", ".join(cls.ALLOWED_EXTENSIONS)
            raise ValidationError(f"Unsupported file type '{ext}'. Allowed formats: {allowed}")

        # 3. Binary image verification via Pillow
        try:
            uploaded_file.seek(0)
            img = Image.open(uploaded_file)
            img.verify()

            fmt = (img.format or '').lower()
            if fmt not in {'jpeg', 'png', 'webp', 'mpo', 'jfif', 'bmp'}:
                raise ValidationError("Invalid or corrupted image format detected.")

            uploaded_file.seek(0)
        except Exception as e:
            if isinstance(e, ValidationError):
                raise
            raise ValidationError("The uploaded file is not a valid or readable image.")

        return uploaded_file


class TeacherService:
    """
    High-level business service for teachers:
    Directory querying, role-based filtering, subject/class allocation, and audit tracking.
    """

    @staticmethod
    def get_teachers_directory(user, search_query=None, qualification=None, specialization=None, status=None, sort_by=None):
        """
        Retrieves a filtered, searchable, sorted queryset of teachers.
        """
        qs = Teacher.objects.select_related('user').prefetch_related(
            'assignments__subject',
            'assignments__class_offering__grade',
            'assignments__class_offering__section'
        ).all()

        # Text search: name or employee ID or specialization
        if search_query:
            q = search_query.strip()
            qs = qs.filter(
                Q(employee_id__icontains=q) |
                Q(first_name__icontains=q) |
                Q(father_name__icontains=q) |
                Q(grandfather_name__icontains=q) |
                Q(specialization__icontains=q) |
                Q(qualification__icontains=q)
            )

        # Qualification filter
        if qualification:
            qs = qs.filter(qualification__icontains=qualification)

        # Specialization filter
        if specialization:
            qs = qs.filter(specialization__iexact=specialization)

        # Status filter
        if status:
            qs = qs.filter(employment_status=status)

        # Sorting
        sort_options = {
            'id_asc': 'employee_id',
            'id_desc': '-employee_id',
            'name_asc': 'first_name',
            'name_desc': '-first_name',
            'joining_asc': 'joining_date',
            'joining_desc': '-joining_date',
        }
        order_field = sort_options.get(sort_by, 'first_name')
        return qs.order_by(order_field, 'father_name')

    @staticmethod
    def log_audit(request, action, teacher, changes=None):
        """Creates an immutable audit record for teacher management operations."""
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
                entity_name='Teacher',
                record_id=str(teacher.employee_id or teacher.pk),
                ip_address=ip or None,
                changes_json=changes or {},
            )
        except Exception:
            pass

    @staticmethod
    def log_assignment_audit(request, action, assignment, changes=None):
        """Creates an immutable audit record for teacher assignment operations."""
        try:
            actor = request.user if request and request.user.is_authenticated else None
            ip = None
            if request:
                ip = (
                    request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
                    or request.META.get('REMOTE_ADDR')
                )
            record_id = f"{assignment.teacher.employee_id} -> {assignment.class_offering} [{assignment.subject.code}]"
            AuditLog.objects.create(
                actor=actor,
                action=action,
                entity_name='TeacherAssignment',
                record_id=record_id,
                ip_address=ip or None,
                changes_json=changes or {},
            )
        except Exception:
            pass

    @staticmethod
    def assign_teacher_to_class(teacher, class_offering, subject, academic_year=None, is_primary=True, request=None, notes=''):
        """
        Assigns a teacher to a class offering and subject.
        Validates:
          1. Academic year active/not closed.
          2. Class offering belongs to specified academic year.
          3. Avoids duplicate assignment (teacher, class_offering, subject).
        """
        ay = academic_year or class_offering.academic_year
        if ay.is_closed:
            raise ValidationError(f"Academic Year '{ay.name}' is closed and cannot accept new teacher assignments.")

        if class_offering.academic_year_id != ay.id:
            raise ValidationError("The selected class offering does not belong to the specified academic year.")

        # Check existing duplicate assignment
        existing = TeacherAssignment.objects.filter(
            teacher=teacher,
            class_offering=class_offering,
            subject=subject
        ).first()

        if existing:
            raise ValidationError(
                f"{teacher.full_name} is already assigned to {class_offering} for {subject.name}."
            )

        with transaction.atomic():
            assignment = TeacherAssignment.objects.create(
                teacher=teacher,
                class_offering=class_offering,
                subject=subject,
                academic_year=ay,
                is_primary=is_primary,
                notes=notes
            )

            TeacherService.log_assignment_audit(
                request,
                'CREATE',
                assignment,
                {
                    'teacher_id': teacher.employee_id,
                    'teacher_name': teacher.full_name,
                    'class_offering': str(class_offering),
                    'subject': subject.name,
                    'academic_year': ay.name,
                    'is_primary': is_primary
                }
            )

        return assignment

    @staticmethod
    def update_teacher_status(teacher, new_status, remarks, request=None):
        """
        Soft-updates teacher status (e.g. ACTIVE -> ON_LEAVE -> TRANSFERRED).
        Requires mandatory remarks. Preserves all historical records.
        """
        if not remarks or not remarks.strip():
            raise ValidationError("A clear administrative remark is required when changing teacher status.")

        old_status = teacher.employment_status
        if old_status == new_status:
            return teacher

        valid_statuses = [code for code, _ in Teacher.STATUS_CHOICES]
        if new_status not in valid_statuses:
            raise ValidationError(f"Invalid employment status '{new_status}'.")

        with transaction.atomic():
            teacher.employment_status = new_status
            teacher.save()

            TeacherService.log_audit(
                request,
                'UPDATE',
                teacher,
                {
                    'status_change': f"{old_status} -> {new_status}",
                    'remarks': remarks.strip(),
                    'timestamp': timezone.now().isoformat(),
                }
            )

        return teacher
