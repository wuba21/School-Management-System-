from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from academics.models import AcademicYear, Grade, Stream, Subject, ClassOffering
from teachers.models import Teacher


class ExamType(models.Model):
    """
    Configurable assessment or examination category.
    Allows schools to define Quizzes, Midterms, Finals, or Continuous Assessments.
    """
    name = models.CharField(max_length=50, unique=True, help_text="e.g. Midterm Examination, Final Examination, Quiz")
    code = models.CharField(max_length=20, unique=True, help_text="Short identifier e.g. MIDTERM, FINAL, QUIZ")
    description = models.CharField(max_length=255, blank=True)
    default_weight = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100.00,
        help_text="Default weight percentage towards semester grade"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Examination Type'
        verbose_name_plural = 'Examination Types'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class Examination(models.Model):
    """
    Formal examination or assessment cycle (e.g. Semester 1 Midterm, Final Exam).
    """
    SEMESTER_CHOICES = [
        ('SEM1', 'Semester 1'),
        ('SEM2', 'Semester 2'),
    ]

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ACTIVE', 'Active / In Progress'),
        ('SUBMITTED', 'Submitted for Review'),
        ('PUBLISHED', 'Published'),
        ('CLOSED', 'Closed / Locked'),
    ]

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='examinations'
    )
    exam_type = models.ForeignKey(
        ExamType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='examinations',
        help_text="Configurable examination category."
    )
    semester = models.CharField(max_length=10, choices=SEMESTER_CHOICES, default='SEM1')
    name = models.CharField(max_length=100, help_text="e.g. Semester 1 Final Examination")
    grade = models.ForeignKey(
        Grade,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='examinations',
        help_text="Target grade level (leave blank if school-wide)."
    )
    class_offering = models.ForeignKey(
        ClassOffering,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='examinations',
        help_text="Optional specific class offering targeting."
    )
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    is_active = models.BooleanField(default=True)
    is_locked = models.BooleanField(default=False, help_text="Locked examinations cannot accept score edits.")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='created_examinations'
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Examination'
        verbose_name_plural = 'Examinations'
        ordering = ['-academic_year__start_date', 'semester', 'name']

    def __str__(self):
        grade_str = f" [{self.grade.name}]" if self.grade else ""
        return f"{self.academic_year.code} - {self.get_semester_display()}: {self.name}{grade_str}"

    @property
    def is_closed(self):
        return self.is_locked or self.status == 'CLOSED'

    @property
    def is_published(self):
        return self.status == 'PUBLISHED'

    @property
    def total_subjects(self):
        return self.exam_subjects.count()

    def clean(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValidationError({'end_date': "End date cannot be earlier than start date."})
        if self.academic_year and self.academic_year.is_closed:
            raise ValidationError("Cannot create or modify examinations in a closed academic year.")

    def save(self, *args, **kwargs):
        self.clean()
        if self.status == 'CLOSED':
            self.is_locked = True
        elif not self.is_locked and self.status == 'ACTIVE':
            self.is_active = True
        super().save(*args, **kwargs)


class ExamSubject(models.Model):
    """
    Subject configuration for an examination, defining maximum marks, pass marks, and weighting.
    Configurable to match school grading policies.
    """
    STATUS_CHOICES = [
        ('PENDING', 'Pending Marks Entry'),
        ('SUBMITTED', 'Submitted for Verification'),
        ('VERIFIED', 'Verified / Approved'),
        ('RETURNED', 'Returned for Correction'),
        ('PUBLISHED', 'Published'),
    ]

    examination = models.ForeignKey(
        Examination,
        on_delete=models.CASCADE,
        related_name='exam_subjects'
    )
    grade = models.ForeignKey(
        Grade,
        on_delete=models.CASCADE,
        related_name='exam_subjects'
    )
    stream = models.ForeignKey(
        Stream,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exam_subjects'
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='exam_subjects'
    )
    max_marks = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100.00,
        help_text="Maximum possible marks (e.g. 100 for final exam or 30 for quiz)"
    )
    pass_marks = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=50.00,
        help_text="Passing score threshold"
    )
    weight_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=100.00,
        help_text="Weight percentage towards final semester mark"
    )
    exam_date = models.DateField(null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    submitted_by = models.ForeignKey(
        Teacher,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='submitted_exam_subjects'
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='verified_exam_subjects'
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_remarks = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Examination Subject'
        verbose_name_plural = 'Examination Subjects'
        constraints = [
            models.UniqueConstraint(
                fields=['examination', 'grade', 'stream', 'subject'],
                name='unique_exam_grade_stream_subject'
            )
        ]
        ordering = ['grade__level', 'subject__name']

    def __str__(self):
        stream_str = f" [{self.stream.code}]" if self.stream else ""
        return f"{self.examination.name} - {self.grade.name}{stream_str}: {self.subject.name} (Max: {self.max_marks})"

    @property
    def is_locked(self):
        return self.examination.is_closed or self.status in ('VERIFIED', 'PUBLISHED')

    @property
    def total_marks_entered(self):
        return self.student_marks.exclude(marks_obtained__isnull=True).count()

    def clean(self):
        if self.pass_marks > self.max_marks:
            raise ValidationError({'pass_marks': "Passing marks cannot exceed maximum possible marks."})
        if self.max_marks <= 0:
            raise ValidationError({'max_marks': "Maximum marks must be greater than zero."})
