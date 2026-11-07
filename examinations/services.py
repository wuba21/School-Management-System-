"""
Examinations Management Service Layer for SSMS.

Handles business logic, validation, duplicate prevention, and audit logging
for examination cycles and subject configurations.
"""

from datetime import date
from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from academics.models import AcademicYear, Grade, Stream, Subject, CurriculumSubject, ClassOffering
from core.models import AuditLog
from examinations.models import ExamType, Examination, ExamSubject


class ExamAuditHelper:
    """Centralized audit logger for examination operations."""

    @staticmethod
    def log(request, action, entity_name, record_id, changes=None):
        try:
            actor = getattr(request, 'user', None) if request and request.user.is_authenticated else None
            ip = None
            if request:
                x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
                ip = x_forwarded.split(',')[0].strip() if x_forwarded else request.META.get('REMOTE_ADDR')

            AuditLog.objects.create(
                actor=actor,
                action=action,
                entity_name=entity_name,
                record_id=str(record_id),
                ip_address=ip,
                changes_json=changes or {}
            )
        except Exception:
            pass


class ExaminationService:
    """Manages Examination lifecycle and administrative actions."""

    @classmethod
    def create_examination(cls, name, exam_type, academic_year, semester='SEM1',
                           start_date=None, end_date=None, grade=None,
                           class_offering=None, created_by=None, request=None):
        if academic_year.is_closed:
            raise ValidationError(f"Academic Year '{academic_year.name}' is closed. New examinations cannot be scheduled.")

        if start_date and end_date and start_date > end_date:
            raise ValidationError("Examination start date cannot be later than end date.")

        with transaction.atomic():
            exam = Examination.objects.create(
                name=name,
                exam_type=exam_type,
                academic_year=academic_year,
                semester=semester,
                grade=grade,
                class_offering=class_offering,
                start_date=start_date or timezone.now().date(),
                end_date=end_date or timezone.now().date(),
                created_by=created_by,
                status='ACTIVE'
            )

            ExamAuditHelper.log(
                request,
                'CREATE',
                'Examination',
                exam.id,
                {
                    'name': exam.name,
                    'academic_year': academic_year.code,
                    'semester': semester,
                    'exam_type': exam_type.name if exam_type else None,
                    'grade': grade.name if grade else 'All Grades'
                }
            )
        return exam

    @classmethod
    def close_examination(cls, examination, user=None, request=None):
        """Locks an examination to prevent further mark submissions or alterations."""
        if examination.is_closed:
            return examination

        examination.status = 'CLOSED'
        examination.is_locked = True
        examination.save(update_fields=['status', 'is_locked', 'updated_at'])

        ExamAuditHelper.log(
            request,
            'UPDATE',
            'Examination',
            examination.id,
            {'action': 'CLOSE_EXAMINATION', 'status': 'CLOSED'}
        )
        return examination

    @classmethod
    def reopen_examination(cls, examination, user=None, request=None):
        """Reopens a locked examination for administrative revisions."""
        if examination.academic_year.is_closed:
            raise ValidationError("Cannot reopen an examination in a closed academic year.")

        examination.status = 'ACTIVE'
        examination.is_locked = False
        examination.save(update_fields=['status', 'is_locked', 'updated_at'])

        ExamAuditHelper.log(
            request,
            'OVERRIDE',
            'Examination',
            examination.id,
            {'action': 'REOPEN_EXAMINATION', 'status': 'ACTIVE'}
        )
        return examination


class ExamSubjectService:
    """Configures subjects included in examinations with maximum marks and pass thresholds."""

    @classmethod
    def configure_subject(cls, examination, grade, subject, max_marks=100.00,
                          pass_marks=50.00, weight_percentage=100.00, stream=None,
                          exam_date=None, start_time=None, end_time=None, request=None):
        if examination.is_closed:
            raise ValidationError("Cannot configure subjects for a closed or locked examination.")

        if pass_marks > max_marks:
            raise ValidationError(f"Pass marks ({pass_marks}) cannot exceed maximum marks ({max_marks}).")

        # Duplicate check within the same exam, grade, and stream
        dup_qs = ExamSubject.objects.filter(
            examination=examination,
            grade=grade,
            stream=stream,
            subject=subject
        )
        if dup_qs.exists():
            stream_desc = f" in {stream.name}" if stream else ""
            raise ValidationError(
                f"Subject '{subject.name}' is already configured for {grade.name}{stream_desc} in this examination."
            )

        with transaction.atomic():
            exam_subj = ExamSubject.objects.create(
                examination=examination,
                grade=grade,
                stream=stream,
                subject=subject,
                max_marks=max_marks,
                pass_marks=pass_marks,
                weight_percentage=weight_percentage,
                exam_date=exam_date,
                start_time=start_time,
                end_time=end_time,
                status='PENDING'
            )

            ExamAuditHelper.log(
                request,
                'CREATE',
                'ExamSubject',
                exam_subj.id,
                {
                    'examination': examination.name,
                    'grade': grade.name,
                    'subject': subject.name,
                    'max_marks': str(max_marks),
                    'pass_marks': str(pass_marks)
                }
            )
        return exam_subj

    @classmethod
    def auto_configure_from_curriculum(cls, examination, grade=None, stream=None,
                                       default_max=100.00, default_pass=50.00, request=None):
        """
        Pulls all subjects from CurriculumSubject for the specified grade/stream
        and populates ExamSubject records in bulk.
        """
        target_grades = [grade] if grade else ([examination.grade] if examination.grade else list(Grade.objects.filter(is_active=True)))
        created_count = 0

        for gr in target_grades:
            curriculum_qs = CurriculumSubject.objects.filter(grade=gr, subject__is_active=True)
            if stream:
                curriculum_qs = curriculum_qs.filter(models.Q(stream=stream) | models.Q(stream__isnull=True))

            for cs in curriculum_qs:
                exists = ExamSubject.objects.filter(
                    examination=examination,
                    grade=gr,
                    stream=stream,
                    subject=cs.subject
                ).exists()
                if not exists:
                    cls.configure_subject(
                        examination=examination,
                        grade=gr,
                        subject=cs.subject,
                        max_marks=default_max,
                        pass_marks=default_pass,
                        stream=stream,
                        request=request
                    )
                    created_count += 1
        return created_count
