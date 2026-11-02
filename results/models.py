from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from students.models import StudentEnrollment
from examinations.models import ExamSubject

class Mark(models.Model):
    """
    Score obtained by an enrolled student on a specific examination subject.
    """
    student_enrollment = models.ForeignKey(
        StudentEnrollment,
        on_delete=models.CASCADE,
        related_name='marks'
    )
    exam_subject = models.ForeignKey(
        ExamSubject,
        on_delete=models.CASCADE,
        related_name='student_marks'
    )
    marks_obtained = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        help_text="Numeric score obtained by the student"
    )
    is_absent = models.BooleanField(
        default=False,
        help_text="True if the student missed the examination"
    )
    remarks = models.CharField(max_length=255, blank=True)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='entered_marks'
    )
    entered_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Student Mark'
        verbose_name_plural = 'Student Marks'
        constraints = [
            models.UniqueConstraint(
                fields=['student_enrollment', 'exam_subject'],
                name='unique_student_mark_per_exam_subject'
            ),
            models.CheckConstraint(
                condition=models.Q(marks_obtained__gte=0.00),
                name='check_marks_obtained_non_negative'
            )
        ]
        ordering = ['student_enrollment', 'exam_subject']

    def __str__(self):
        score_str = "ABSENT" if self.is_absent else f"{self.marks_obtained}/{self.exam_subject.max_marks}"
        return f"{self.student_enrollment.student.admission_number} - {self.exam_subject.subject.name}: {score_str}"

    def clean(self):
        super().clean()
        if self.exam_subject and not self.is_absent:
            if self.marks_obtained > self.exam_subject.max_marks:
                raise ValidationError({
                    'marks_obtained': (
                        f"Score ({self.marks_obtained}) cannot exceed the maximum allowed marks "
                        f"({self.exam_subject.max_marks}) for this examination."
                    )
                })

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
