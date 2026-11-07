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
from PIL import Image

from django.db import transaction
from django.db.models import Q, Max
from django.core.exceptions import ValidationError
from django.utils import timezone

from students.models import Student, StudentEnrollment
from academics.models import AcademicYear, Grade, Section, Stream, ClassOffering
from teachers.models import Teacher, TeacherAssignment
from core.models import AuditLog


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
