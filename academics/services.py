"""
Academic Management Service Layer for SSMS.

Handles business logic, validation, constraints, and audit logging for:
  - Academic Years (calendar cycles, single-current constraint, lock on close)
  - Grade Levels, Sections, Curriculum Streams, and Master Subjects
  - Class Offerings (grade-section offerings per academic year)
  - Curriculum Allocations (CurriculumSubject mappings)
  - Teacher Allocations (TeacherAssignment integration)
  - Student Class Enrollment (preservation of historical records, duplicate prevention)
"""

from datetime import date
from django.db import transaction
from django.db.models import Q, Count
from django.core.exceptions import ValidationError
from django.utils import timezone

from academics.models import AcademicYear, Grade, Section, Stream, Subject, CurriculumSubject, ClassOffering
from students.models import Student, StudentEnrollment
from teachers.models import Teacher, TeacherAssignment
from core.models import AuditLog


class AcademicAuditService:
    """Centralized audit logging helper for academic structural actions."""

    @staticmethod
    def log(request, action, entity_name, record_id, changes=None):
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
                entity_name=entity_name,
                record_id=str(record_id),
                ip_address=ip or None,
                changes_json=changes or {},
            )
        except Exception:
            pass


class AcademicYearService:
    """Manages academic year lifecycles, active status, and locks."""

    @classmethod
    def get_current_year(cls):
        """Returns the single currently active academic year or None."""
        return AcademicYear.objects.filter(is_current=True).first()

    @classmethod
    def activate_year(cls, year, request=None):
        """Sets an academic year as the active session and deactivates all others."""
        if year.is_closed:
            raise ValidationError(f"Cannot activate closed academic year '{year.name}'. Re-open it first.")

        with transaction.atomic():
            # Deactivate any currently active year
            AcademicYear.objects.filter(is_current=True).exclude(pk=year.pk).update(is_current=False)
            year.is_current = True
            year.save()

            AcademicAuditService.log(
                request,
                'UPDATE',
                'AcademicYear',
                year.code,
                {'action': 'ACTIVATED', 'name': year.name, 'is_current': True}
            )
        return year

    @classmethod
    def close_year(cls, year, request=None):
        """Locks an academic year to prevent further alterations."""
        with transaction.atomic():
            year.is_closed = True
            year.is_current = False
            year.save()

            AcademicAuditService.log(
                request,
                'UPDATE',
                'AcademicYear',
                year.code,
                {'action': 'CLOSED', 'name': year.name, 'is_closed': True, 'is_current': False}
            )
        return year

    @classmethod
    def reopen_year(cls, year, request=None):
        """Re-opens a closed academic year for administrative corrections."""
        with transaction.atomic():
            year.is_closed = False
            year.save()

            AcademicAuditService.log(
                request,
                'UPDATE',
                'AcademicYear',
                year.code,
                {'action': 'REOPENED', 'name': year.name, 'is_closed': False}
            )
        return year


class StructureService:
    """Manages Grades, Sections, Streams, and Subjects."""

    @staticmethod
    def toggle_active_state(model_class, obj_id, request=None):
        """Toggles the is_active status of a Grade, Section, Stream, or Subject."""
        obj = model_class.objects.get(pk=obj_id)
        new_state = not obj.is_active
        obj.is_active = new_state
        obj.save()

        AcademicAuditService.log(
            request,
            'UPDATE',
            model_class.__name__,
            getattr(obj, 'code', None) or getattr(obj, 'name', str(obj.pk)),
            {'is_active': new_state}
        )
        return obj


class ClassOfferingService:
    """Manages Classroom Offerings (Grade-Section-Stream per Academic Year)."""

    @classmethod
    def create_offering(cls, academic_year, grade, section, stream=None, max_capacity=50, request=None):
        if academic_year.is_closed:
            raise ValidationError(f"Academic Year '{academic_year.name}' is closed. New class offerings cannot be added.")

        # Check for duplicates
        existing = ClassOffering.objects.filter(
            academic_year=academic_year,
            grade=grade,
            section=section,
            stream=stream
        ).first()

        if existing:
            stream_label = f" ({stream.name})" if stream else ""
            raise ValidationError(
                f"Class Offering '{grade.name} - Section {section.name}{stream_label}' already exists for {academic_year.name}."
            )

        with transaction.atomic():
            offering = ClassOffering.objects.create(
                academic_year=academic_year,
                grade=grade,
                section=section,
                stream=stream,
                max_capacity=max_capacity
            )

            AcademicAuditService.log(
                request,
                'CREATE',
                'ClassOffering',
                str(offering),
                {
                    'academic_year': academic_year.code,
                    'grade': grade.name,
                    'section': section.name,
                    'stream': stream.name if stream else 'None',
                    'max_capacity': max_capacity
                }
            )
        return offering


class CurriculumService:
    """Manages Grade/Stream subject allocations via CurriculumSubject."""

    @classmethod
    def assign_curriculum_subject(cls, grade, subject, stream=None, credit_hours=3, is_elective=False, request=None):
        existing = CurriculumSubject.objects.filter(
            grade=grade,
            stream=stream,
            subject=subject
        ).first()

        if existing:
            stream_str = f" in {stream.name}" if stream else ""
            raise ValidationError(f"{subject.name} is already allocated to {grade.name}{stream_str}.")

        with transaction.atomic():
            curr = CurriculumSubject.objects.create(
                grade=grade,
                stream=stream,
                subject=subject,
                credit_hours=credit_hours,
                is_elective=is_elective
            )

            AcademicAuditService.log(
                request,
                'CREATE',
                'CurriculumSubject',
                str(curr),
                {
                    'grade': grade.name,
                    'subject': subject.name,
                    'stream': stream.name if stream else 'None',
                    'credit_hours': credit_hours,
                    'is_elective': is_elective
                }
            )
        return curr


class ClassEnrollmentService:
    """Handles student enrollment into class offerings, ensuring historical preservation."""

    @classmethod
    def enroll_student(cls, student, class_offering, academic_year=None, status='ACTIVE', request=None):
        ay = academic_year or class_offering.academic_year

        if ay.is_closed:
            raise ValidationError(f"Academic Year '{ay.name}' is closed. Student enrollments cannot be modified.")

        if class_offering.academic_year_id != ay.id:
            raise ValidationError("The selected class offering does not belong to the chosen academic year.")

        # Capacity check: reject enrollment if the class is already full
        if class_offering.is_full:
            raise ValidationError(
                f"Class {class_offering} has reached its maximum capacity of "
                f"{class_offering.max_capacity} students. Increase the capacity or choose another class."
            )

        # Duplicate check: Student cannot have multiple enrollments in the same academic year
        existing = StudentEnrollment.objects.filter(
            student=student,
            academic_year=ay
        ).first()

        if existing:
            raise ValidationError(
                f"Student {student.full_name} ({student.admission_number}) is already enrolled in "
                f"{existing.class_offering} for {ay.name}. Transfer the student instead."
            )

        with transaction.atomic():
            enrollment = StudentEnrollment.objects.create(
                student=student,
                class_offering=class_offering,
                academic_year=ay,
                status=status
            )

            # Ensure student status is active
            if student.status != 'ACTIVE':
                student.status = 'ACTIVE'
                student.save()

            AcademicAuditService.log(
                request,
                'CREATE',
                'StudentEnrollment',
                f"{student.admission_number} -> {class_offering}",
                {
                    'student': student.full_name,
                    'admission_number': student.admission_number,
                    'class_offering': str(class_offering),
                    'academic_year': ay.code
                }
            )
        return enrollment

    @classmethod
    def batch_enroll_students(cls, student_ids, class_offering, request=None):
        """Enrolls a list of student IDs into a classroom, reporting successes and skips."""
        ay = class_offering.academic_year
        if ay.is_closed:
            raise ValidationError(f"Academic Year '{ay.name}' is closed.")

        enrolled = []
        skipped = []

        students = Student.objects.filter(pk__in=student_ids)
        for s in students:
            # Check capacity
            if class_offering.is_full:
                skipped.append((s, "Classroom reached maximum capacity."))
                continue

            try:
                enrollment = cls.enroll_student(s, class_offering, ay, request=request)
                enrolled.append(enrollment)
            except ValidationError as e:
                skipped.append((s, str(e)))

        return enrolled, skipped
