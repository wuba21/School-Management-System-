from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from students.models import StudentEnrollment
from examinations.models import Examination, ExamSubject


class GradingScale(models.Model):
    """
    Configurable grading policy defining score brackets, grade labels, and passing thresholds.
    Allows administrators to configure standard A-F, GPA points, or custom competency levels.
    """
    name = models.CharField(max_length=100, unique=True, help_text="e.g. Ethiopian Secondary Standard Scale")
    code = models.CharField(max_length=30, unique=True, default="DEFAULT")
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=True, help_text="Marks the active grading scale for report cards.")
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Grading Scale'
        verbose_name_plural = 'Grading Scales'
        ordering = ['name']

    def __str__(self):
        default_str = " (Default)" if self.is_default else ""
        return f"{self.name}{default_str}"

    def save(self, *args, **kwargs):
        if self.is_default:
            GradingScale.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    def get_grade_for_score(self, percentage):
        """
        Evaluates a percentage score against ranges and returns the matching GradingRange.
        Safe against edge bounds (0.00 to 100.00).
        """
        if percentage is None:
            return None
        percentage = round(float(percentage), 2)
        for gr in self.ranges.order_by('-min_score'):
            if gr.min_score <= percentage <= gr.max_score:
                return gr
        # Fallback to lowest range if below 0 or near bottom
        return self.ranges.order_by('min_score').first()


class GradingRange(models.Model):
    """
    Individual grade boundary (e.g. 90.00% to 100.00% -> A, Excellent, 4.0 GPA).
    """
    grading_scale = models.ForeignKey(
        GradingScale,
        on_delete=models.CASCADE,
        related_name='ranges'
    )
    grade_label = models.CharField(max_length=10, help_text="e.g. A, B, C, D, F")
    min_score = models.DecimalField(max_digits=5, decimal_places=2, help_text="Minimum score percentage")
    max_score = models.DecimalField(max_digits=5, decimal_places=2, help_text="Maximum score percentage")
    gpa_point = models.DecimalField(max_digits=4, decimal_places=2, default=0.00)
    description = models.CharField(max_length=100, help_text="e.g. Excellent, Very Good, Unsatisfactory")
    is_passing = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Grading Range'
        verbose_name_plural = 'Grading Ranges'
        ordering = ['-min_score']
        constraints = [
            models.UniqueConstraint(
                fields=['grading_scale', 'grade_label'],
                name='unique_grade_label_per_scale'
            )
        ]

    def __str__(self):
        return f"{self.grade_label} ({self.min_score}% - {self.max_score}%): {self.description}"

    def clean(self):
        if self.min_score >= self.max_score:
            raise ValidationError({'min_score': "Minimum score must be strictly less than maximum score."})


class Mark(models.Model):
    """
    Score obtained by an enrolled student on a specific examination subject.
    Preserves missing marks as unentered without artificially converting to zero.
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Draft / Saved'),
        ('SUBMITTED', 'Submitted for Verification'),
        ('VERIFIED', 'Verified / Approved'),
        ('RETURNED', 'Returned for Correction'),
        ('PUBLISHED', 'Published'),
    ]

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
        null=True,
        blank=True,
        help_text="Numeric score obtained. Leave blank if missing/unmarked."
    )
    is_absent = models.BooleanField(
        default=False,
        help_text="True if the student missed the examination."
    )
    is_excused = models.BooleanField(
        default=False,
        help_text="True if absence is formally excused."
    )
    remarks = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
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
                check=models.Q(marks_obtained__isnull=True) | models.Q(marks_obtained__gte=0.00),
                name='check_marks_obtained_non_negative_or_null'
            )
        ]
        ordering = ['student_enrollment__student__first_name', 'student_enrollment__student__father_name']

    def __str__(self):
        score_str = "ABSENT" if self.is_absent else (f"{self.marks_obtained}/{self.exam_subject.max_marks}" if self.marks_obtained is not None else "UNMARKED")
        return f"{self.student_enrollment.student.admission_number} - {self.exam_subject.subject.name}: {score_str}"

    @property
    def percentage(self):
        if self.is_absent or self.marks_obtained is None:
            return None
        if self.exam_subject.max_marks > 0:
            return round((float(self.marks_obtained) / float(self.exam_subject.max_marks)) * 100, 2)
        return 0.0

    @property
    def is_passing(self):
        if self.is_absent or self.marks_obtained is None:
            return False
        return self.marks_obtained >= self.exam_subject.pass_marks

    def clean(self):
        super().clean()
        if self.marks_obtained is not None and not self.is_absent:
            if self.marks_obtained < 0:
                raise ValidationError({'marks_obtained': "Score cannot be negative."})
            if self.exam_subject and self.marks_obtained > self.exam_subject.max_marks:
                raise ValidationError({
                    'marks_obtained': (
                        f"Score ({self.marks_obtained}) cannot exceed maximum allowed marks "
                        f"({self.exam_subject.max_marks}) for {self.exam_subject.subject.name}."
                    )
                })

        # Ensure student is in the grade of the examination subject
        if self.student_enrollment and self.exam_subject:
            student_grade = self.student_enrollment.class_offering.grade
            if student_grade != self.exam_subject.grade:
                raise ValidationError("Student's grade does not match examination subject grade.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class ResultApproval(models.Model):
    """
    Verification review record for marks submitted by teachers.
    Implements a strict audit trail before publishing results.
    """
    DECISION_CHOICES = [
        ('APPROVED', 'Approved & Verified'),
        ('RETURNED', 'Returned for Correction'),
    ]

    exam_subject = models.ForeignKey(
        ExamSubject,
        on_delete=models.CASCADE,
        related_name='approvals'
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='result_approvals'
    )
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES)
    comments = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Result Approval'
        verbose_name_plural = 'Result Approvals'
        ordering = ['-reviewed_at']

    def __str__(self):
        return f"{self.exam_subject} -> {self.get_decision_display()} by {self.reviewed_by} ({self.reviewed_at:%Y-%m-%d})"


class StudentResultSummary(models.Model):
    """
    Aggregated examination performance summary for an enrolled student across all subjects.
    Supports report cards, ranking, averages, and semester performance calculations.
    """
    STATUS_CHOICES = [
        ('PROVISIONAL', 'Provisional (Pending Full Approval)'),
        ('VERIFIED', 'Verified'),
        ('PUBLISHED', 'Published'),
    ]

    student_enrollment = models.ForeignKey(
        StudentEnrollment,
        on_delete=models.CASCADE,
        related_name='result_summaries'
    )
    examination = models.ForeignKey(
        Examination,
        on_delete=models.CASCADE,
        related_name='result_summaries'
    )
    total_obtained = models.DecimalField(max_digits=7, decimal_places=2, default=0.00)
    total_max = models.DecimalField(max_digits=7, decimal_places=2, default=0.00)
    average_mark = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    overall_grade = models.CharField(max_length=10, blank=True)
    grade_description = models.CharField(max_length=100, blank=True)
    subjects_passed = models.PositiveSmallIntegerField(default=0)
    subjects_failed = models.PositiveSmallIntegerField(default=0)
    total_subjects = models.PositiveSmallIntegerField(default=0)
    is_complete = models.BooleanField(default=True, help_text="False if student has missing/unentered marks.")
    rank = models.PositiveIntegerField(null=True, blank=True, help_text="Class rank for this examination.")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PROVISIONAL')
    teacher_remarks = models.CharField(max_length=255, blank=True)
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Student Result Summary'
        verbose_name_plural = 'Student Result Summaries'
        constraints = [
            models.UniqueConstraint(
                fields=['student_enrollment', 'examination'],
                name='unique_student_examination_summary'
            )
        ]
        ordering = ['-average_mark', 'student_enrollment__student__first_name']

    def __str__(self):
        return f"{self.student_enrollment.student.admission_number} - {self.examination.name}: Avg {self.average_mark} ({self.overall_grade})"

    @property
    def total_marks_obtained(self):
        return self.total_obtained

    @property
    def total_max_marks(self):
        return self.total_max
