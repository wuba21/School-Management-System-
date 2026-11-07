from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from academics.models import AcademicYear, Grade, Stream, ClassOffering
from students.models import Student, StudentEnrollment


class PromotionCriteria(models.Model):
    """
    Configurable school policy governing student promotion, repetition, and graduation.
    No passing thresholds or rules are hard-coded.
    """
    name = models.CharField(max_length=150, help_text="e.g. Majang Secondary Standard Promotion Policy")
    code = models.CharField(max_length=50, unique=True, help_text="Short unique identifier, e.g. SEC-PROM-2026")
    description = models.TextField(blank=True)
    minimum_average = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50.00,
        help_text="Minimum overall academic average percentage to qualify for promotion"
    )
    max_failing_subjects = models.PositiveSmallIntegerField(
        default=2,
        help_text="Maximum allowed failing subjects (below passing score) to still qualify for conditional promotion"
    )
    require_all_core_passed = models.BooleanField(
        default=False,
        help_text="If enabled, student must pass all designated core curriculum subjects"
    )
    minimum_attendance_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional attendance percentage threshold (e.g. 75.00%). Leave blank if attendance is not factored."
    )
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Promotion Criteria'
        verbose_name_plural = 'Promotion Criteria'
        ordering = ['-is_default', 'name']

    def __str__(self):
        return f"{self.name} (Min Avg: {self.minimum_average}%, Max Fail: {self.max_failing_subjects})"

    def save(self, *args, **kwargs):
        if self.is_default:
            PromotionCriteria.objects.exclude(pk=self.pk).filter(is_default=True).update(is_default=False)
        super().save(*args, **kwargs)


class PromotionBatch(models.Model):
    """
    Batch transaction envelope for evaluating and transitioning an entire cohort/grade of students.
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Draft Preparation'),
        ('SUBMITTED', 'Submitted for Committee Review'),
        ('APPROVED', 'Approved by Committee/Principal'),
        ('FINALIZED', 'Finalized & Enrolled in Next Year'),
        ('REJECTED', 'Returned / Rejected for Revision'),
    ]

    name = models.CharField(max_length=150, help_text="e.g. 2026/2027 Grade 9 to 10 Promotion Cohort")
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='promotion_batches_source',
        help_text="Source / Completed academic year"
    )
    target_academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='promotion_batches_target',
        help_text="Destination / Next academic year"
    )
    grade = models.ForeignKey(
        Grade,
        on_delete=models.CASCADE,
        related_name='promotion_batches',
        help_text="Source grade level being evaluated"
    )
    promotion_criteria = models.ForeignKey(
        PromotionCriteria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='batches'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_promotion_batches'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_promotion_batches'
    )
    approval_date = models.DateTimeField(null=True, blank=True)
    approval_remarks = models.TextField(blank=True)
    finalized_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Promotion Batch'
        verbose_name_plural = 'Promotion Batches'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} [{self.get_status_display()}]"

    def clean(self):
        if self.academic_year_id and self.target_academic_year_id:
            if self.academic_year == self.target_academic_year:
                raise ValidationError("Target academic year must be different from source academic year.")
            if self.target_academic_year.start_date <= self.academic_year.start_date:
                raise ValidationError("Target academic year must start after the source academic year.")

    @property
    def total_candidates(self):
        return self.records.count()

    @property
    def promoted_count(self):
        return self.records.filter(final_outcome='PROMOTED').count()

    @property
    def repeated_count(self):
        return self.records.filter(final_outcome='REPEATED').count()

    @property
    def graduated_count(self):
        return self.records.filter(final_outcome='GRADUATED').count()

    @property
    def pending_count(self):
        return self.records.filter(final_outcome='PENDING').count()


class PromotionRecord(models.Model):
    """
    Individual student promotion evaluation, recommendation, and approved outcome.
    Preserves historical enrollment without overwriting.
    """
    OUTCOME_CHOICES = [
        ('PROMOTED', 'Promoted to Next Grade'),
        ('REPEATED', 'Repeat Current Grade'),
        ('GRADUATED', 'Graduated (Grade 12 Complete)'),
        ('TRANSFERRED', 'Transferred Out'),
        ('WITHDRAWN', 'Withdrawn / Dropped Out'),
        ('PENDING', 'Pending Administrative Review'),
    ]

    DECISION_STATUS_CHOICES = [
        ('PENDING', 'Pending Review'),
        ('APPROVED', 'Approved by Committee'),
        ('REJECTED', 'Rejected'),
        ('FINALIZED', 'Finalized & Enrolled'),
    ]

    batch = models.ForeignKey(
        PromotionBatch,
        on_delete=models.CASCADE,
        related_name='records'
    )
    student_enrollment = models.ForeignKey(
        StudentEnrollment,
        on_delete=models.CASCADE,
        related_name='academic_promotions'
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='academic_promotions'
    )
    previous_academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='+'
    )
    next_academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='+'
    )
    previous_grade = models.ForeignKey(
        Grade,
        on_delete=models.CASCADE,
        related_name='+'
    )
    next_grade = models.ForeignKey(
        Grade,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        help_text="Target grade level. Same grade if repeating; null if graduated or withdrawn."
    )
    previous_class_offering = models.ForeignKey(
        ClassOffering,
        on_delete=models.CASCADE,
        related_name='+'
    )
    next_class_offering = models.ForeignKey(
        ClassOffering,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+',
        help_text="Specific allocated classroom section in destination academic year."
    )
    recommended_outcome = models.CharField(
        max_length=20,
        choices=OUTCOME_CHOICES,
        default='PENDING',
        help_text="Algorithmic recommendation generated from performance criteria"
    )
    final_outcome = models.CharField(
        max_length=20,
        choices=OUTCOME_CHOICES,
        default='PENDING',
        help_text="Authorized human decision by Registrar / Examination Committee"
    )
    decision_status = models.CharField(
        max_length=20,
        choices=DECISION_STATUS_CHOICES,
        default='PENDING'
    )
    academic_average = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Computed overall academic average mark across examination cycles"
    )
    total_failing_subjects = models.PositiveSmallIntegerField(
        default=0,
        help_text="Number of subjects where student did not meet passing threshold"
    )
    attendance_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Overall attendance presence percentage during the academic year"
    )
    has_incomplete_results = models.BooleanField(
        default=False,
        help_text="Flags students with missing examination marks or unrecorded subjects"
    )
    remarks = models.TextField(
        blank=True,
        help_text="Administrative remarks, committee rationale, or condition details"
    )
    is_enrolled_in_next_year = models.BooleanField(
        default=False,
        help_text="Designates whether new StudentEnrollment record has been generated"
    )
    new_enrollment = models.ForeignKey(
        StudentEnrollment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='promoted_from_record'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Promotion Record'
        verbose_name_plural = 'Promotion Records'
        constraints = [
            models.UniqueConstraint(
                fields=['batch', 'student_enrollment'],
                name='unique_promotion_record_per_batch'
            )
        ]
        ordering = ['student__first_name', 'student__father_name']

    def __str__(self):
        return f"{self.student.admission_number} - {self.student.full_name}: {self.get_final_outcome_display()}"


class GraduationRecord(models.Model):
    """
    Formal Grade 12 graduation registry.
    Requires official review and stores Ministry/School leaving details.
    """
    STATUS_CHOICES = [
        ('ELIGIBLE', 'Eligible for Graduation Review'),
        ('APPROVED', 'Approved for Graduation'),
        ('GRADUATED', 'Formally Graduated'),
        ('WITHHELD', 'Withheld / Incomplete'),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='graduation_records'
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='graduation_records'
    )
    grade = models.ForeignKey(
        Grade,
        on_delete=models.CASCADE,
        related_name='+'
    )
    stream = models.ForeignKey(
        Stream,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )
    graduation_date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ELIGIBLE')
    cumulative_average = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    certificate_number = models.CharField(max_length=100, blank=True, help_text="Official leaving certificate identifier")
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_graduations'
    )
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Graduation Record'
        verbose_name_plural = 'Graduation Records'
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'academic_year'],
                name='unique_graduation_per_student_year'
            )
        ]
        ordering = ['-graduation_date', 'student__first_name']

    def __str__(self):
        return f"{self.student.admission_number} - {self.student.full_name} ({self.academic_year.name}): {self.get_status_display()}"


class StudentStatusHistory(models.Model):
    """
    Comprehensive audit log for student lifecycle transitions:
    transfers, withdrawals, dropouts, readmissions, and graduations.
    Preserves academic history without record deletion.
    """
    STATUS_TYPE_CHOICES = [
        ('TRANSFER_OUT', 'Transferred Out to Another School'),
        ('WITHDRAWAL', 'Formal Withdrawal by Parent/Guardian'),
        ('DROPOUT', 'Drop Out'),
        ('SUSPENSION', 'Disciplinary Suspension'),
        ('READMISSION', 'Re-admitted to School'),
        ('GRADUATION', 'Completed Secondary Graduation'),
    ]

    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='status_histories'
    )
    status_type = models.CharField(max_length=30, choices=STATUS_TYPE_CHOICES)
    effective_date = models.DateField(default=timezone.now)
    reason = models.TextField(help_text="Detailed justification or documentation rationale")
    destination_school = models.CharField(
        max_length=200,
        blank=True,
        help_text="Destination school name, zone, or region (for transfers)"
    )
    documents_issued = models.CharField(
        max_length=255,
        blank=True,
        help_text="e.g. Clearance Form, Official Transcript, Transfer Certificate"
    )
    authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='authorized_status_changes'
    )
    previous_status = models.CharField(max_length=30, blank=True)
    new_status = models.CharField(max_length=30, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Student Status History'
        verbose_name_plural = 'Student Status Histories'
        ordering = ['-effective_date', '-created_at']

    def __str__(self):
        return f"{self.student.admission_number} - {self.get_status_type_display()} on {self.effective_date}"
