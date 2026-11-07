from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from academics.models import ClassOffering, AcademicYear, Subject
from teachers.models import Teacher
from students.models import StudentEnrollment


class AttendanceSession(models.Model):
    """
    Roll-call session for a class offering on a specific date and time slot / subject.
    Supports daily attendance (morning/afternoon/full-day) or period-based tracking.
    """
    SESSION_TYPE_CHOICES = [
        ('DAILY', 'Full Day (Daily)'),
        ('MORNING', 'Morning Period'),
        ('AFTERNOON', 'Afternoon Period'),
        ('PERIOD', 'Subject Period'),
    ]

    STATUS_CHOICES = [
        ('OPEN', 'Open / In Progress'),
        ('SUBMITTED', 'Submitted'),
        ('CLOSED', 'Closed / Locked'),
    ]

    class_offering = models.ForeignKey(
        ClassOffering,
        on_delete=models.CASCADE,
        related_name='attendance_sessions'
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='attendance_sessions',
        null=True,
        blank=True
    )
    date = models.DateField(default=timezone.now)
    session_type = models.CharField(max_length=20, choices=SESSION_TYPE_CHOICES, default='DAILY')
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='attendance_sessions',
        help_text="Optional subject for period-based attendance."
    )
    recorded_by = models.ForeignKey(
        Teacher,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='recorded_attendances',
        help_text="Teacher who conducted the roll call."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_attendance_sessions',
        help_text="User account that initiated the session."
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='OPEN',
        help_text="Closed sessions are locked from further standard teacher edits."
    )
    remarks = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Attendance Session'
        verbose_name_plural = 'Attendance Sessions'
        constraints = [
            models.UniqueConstraint(
                fields=['class_offering', 'date', 'session_type'],
                condition=models.Q(subject__isnull=True),
                name='unique_session_without_subject'
            ),
            models.UniqueConstraint(
                fields=['class_offering', 'date', 'session_type', 'subject'],
                condition=models.Q(subject__isnull=False),
                name='unique_session_with_subject'
            ),
        ]
        ordering = ['-date', '-created_at']

    def __str__(self):
        subj_str = f" - {self.subject.code}" if self.subject else ""
        return f"{self.class_offering.display_name} | {self.date} ({self.get_session_type_display()}{subj_str})"

    @property
    def is_closed(self):
        return self.status == 'CLOSED'

    @property
    def is_editable(self):
        if self.is_closed:
            return False
        if self.academic_year and self.academic_year.is_closed:
            return False
        return True

    @property
    def total_records(self):
        return self.records.count()

    @property
    def present_count(self):
        return self.records.filter(status='PRESENT').count()

    @property
    def absent_count(self):
        return self.records.filter(status='ABSENT').count()

    @property
    def late_count(self):
        return self.records.filter(status='LATE').count()

    @property
    def excused_count(self):
        return self.records.filter(status='EXCUSED').count()

    @property
    def attendance_percentage(self):
        total = self.total_records
        if total == 0:
            return 0.0
        # In educational standard: Present and Late count as attendance attended
        attended = self.present_count + self.late_count
        return round((attended / total) * 100, 1)

    def clean(self):
        if self.class_offering_id:
            if not self.academic_year_id:
                self.academic_year = self.class_offering.academic_year
            elif self.academic_year_id != self.class_offering.academic_year_id:
                raise ValidationError("Academic year must match the selected class offering's academic year.")

            if self.academic_year_id and self.academic_year.is_closed:
                raise ValidationError(f"Cannot manage attendance in closed academic year '{self.academic_year.name}'.")

        if self.session_type == 'PERIOD' and not self.subject_id:
            raise ValidationError({'subject': "Subject is required when session type is 'Subject Period'."})

    def save(self, *args, **kwargs):
        if self.class_offering and not self.academic_year:
            self.academic_year = self.class_offering.academic_year
        self.clean()
        super().save(*args, **kwargs)


class AttendanceRecord(models.Model):
    """
    Individual student attendance mark for a specific session.
    """
    STATUS_CHOICES = [
        ('PRESENT', 'Present'),
        ('ABSENT', 'Absent'),
        ('LATE', 'Late'),
        ('EXCUSED', 'Excused Absence'),
    ]

    attendance_session = models.ForeignKey(
        AttendanceSession,
        on_delete=models.CASCADE,
        related_name='records'
    )
    student_enrollment = models.ForeignKey(
        StudentEnrollment,
        on_delete=models.CASCADE,
        related_name='attendance_records'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PRESENT')
    reason = models.CharField(max_length=255, blank=True, help_text="Reason for absence or excuse.")
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='recorded_attendance_marks'
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Attendance Record'
        verbose_name_plural = 'Attendance Records'
        constraints = [
            models.UniqueConstraint(
                fields=['attendance_session', 'student_enrollment'],
                name='unique_student_attendance_per_session'
            )
        ]
        ordering = ['student_enrollment__student__first_name', 'student_enrollment__student__father_name']

    def __str__(self):
        return f"{self.student_enrollment.student.admission_number}: {self.get_status_display()} ({self.attendance_session.date})"

    @property
    def remarks(self):
        return self.reason

    @remarks.setter
    def remarks(self, val):
        self.reason = val or ""

    def clean(self):
        if self.attendance_session_id and self.student_enrollment_id:
            if self.student_enrollment.class_offering_id != self.attendance_session.class_offering_id:
                raise ValidationError("Student must be actively enrolled in the session's class offering.")
            if self.attendance_session.is_closed:
                raise ValidationError("Cannot modify records of a closed attendance session.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
