from django.db import models
from academics.models import AcademicYear, Grade, Stream, Subject

class Examination(models.Model):
    """
    Formal examination or assessment cycle (e.g. Semester 1 Midterm, Continuous Assessment).
    """
    SEMESTER_CHOICES = [
        ('SEM1', 'Semester 1'),
        ('SEM2', 'Semester 2'),
    ]

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='examinations'
    )
    semester = models.CharField(max_length=10, choices=SEMESTER_CHOICES)
    name = models.CharField(max_length=100, help_text="e.g. Semester 1 Final Examination")
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)
    is_locked = models.BooleanField(default=False, help_text="Locked examinations cannot accept score edits.")

    class Meta:
        verbose_name = 'Examination'
        verbose_name_plural = 'Examinations'
        ordering = ['-academic_year__start_date', 'semester', 'name']

    def __str__(self):
        return f"{self.academic_year.code} - {self.get_semester_display()}: {self.name}"


class ExamSubject(models.Model):
    """
    Subject configuration for an examination, defining maximum marks, pass marks, and weighting.
    Configurable to match Ministry of Education grading policies.
    """
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

    class Meta:
        verbose_name = 'Examination Subject'
        verbose_name_plural = 'Examination Subjects'
        constraints = [
            models.UniqueConstraint(
                fields=['examination', 'grade', 'stream', 'subject'],
                name='unique_exam_grade_stream_subject'
            )
        ]

    def __str__(self):
        stream_str = f" [{self.stream.code}]" if self.stream else ""
        return f"{self.examination.name} - {self.grade.name}{stream_str}: {self.subject.name} (Max: {self.max_marks})"
