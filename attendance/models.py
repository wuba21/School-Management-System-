from django.db import models
from academics.models import ClassOffering
from teachers.models import Teacher
from students.models import StudentEnrollment

class AttendanceSession(models.Model):
    """
    Roll-call event for a class offering on a specific date.
    """
    SESSION_TYPE_CHOICES = [
        ('DAILY', 'Full Day'),
        ('MORNING', 'Morning Period'),
        ('AFTERNOON', 'Afternoon Period'),
    ]

    class_offering = models.ForeignKey(
        ClassOffering,
        on_delete=models.CASCADE,
        related_name='attendance_sessions'
    )
    date = models.DateField()
    session_type = models.CharField(max_length=20, choices=SESSION_TYPE_CHOICES, default='DAILY')
    recorded_by = models.ForeignKey(
        Teacher,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='recorded_attendances'
    )
    remarks = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Attendance Session'
        verbose_name_plural = 'Attendance Sessions'
        constraints = [
            models.UniqueConstraint(
                fields=['class_offering', 'date', 'session_type'],
                name='unique_attendance_session_per_class_date'
            )
        ]
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f"{self.class_offering} - {self.date} ({self.get_session_type_display()})"


class AttendanceRecord(models.Model):
    """
    Attendance mark for an enrolled student in an attendance session.
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
    reason = models.CharField(max_length=255, blank=True, help_text="Reason for absence or excuse")

    class Meta:
        verbose_name = 'Attendance Record'
        verbose_name_plural = 'Attendance Records'
        constraints = [
            models.UniqueConstraint(
                fields=['attendance_session', 'student_enrollment'],
                name='unique_student_attendance_per_session'
            )
        ]

    def __str__(self):
        return f"{self.student_enrollment.student.admission_number}: {self.status}"
