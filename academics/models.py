from django.db import models
from django.core.exceptions import ValidationError

class AcademicYear(models.Model):
    """
    Academic school year (e.g. 2026/2027 or 2018/2019 E.C.).
    """
    name = models.CharField(max_length=100, unique=True, help_text="e.g. 2026/2027 (2018/2019 E.C.)")
    code = models.CharField(max_length=20, unique=True, help_text="Short identifier e.g. AY-2026")
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False, help_text="Marks the active academic year.")
    is_closed = models.BooleanField(default=False, help_text="Locked past academic years cannot be modified.")

    class Meta:
        verbose_name = 'Academic Year'
        verbose_name_plural = 'Academic Years'
        ordering = ['-start_date']

    def __str__(self):
        status = " (Active)" if self.is_current else ""
        return f"{self.name}{status}"

    def clean(self):
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError({'end_date': "End date must be strictly after the start date."})

    def save(self, *args, **kwargs):
        self.clean()
        if self.is_current:
            # Ensure only one academic year is active at any time
            AcademicYear.objects.filter(is_current=True).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)


class Grade(models.Model):
    """
    Physical secondary school grade level (Grades 9 to 12).
    """
    name = models.CharField(max_length=50, unique=True, help_text="e.g. Grade 9, Grade 10")
    level = models.PositiveSmallIntegerField(unique=True, help_text="Numeric level: 9, 10, 11, or 12")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, help_text="Designates whether this grade level is currently active.")

    class Meta:
        verbose_name = 'Grade Level'
        verbose_name_plural = 'Grade Levels'
        ordering = ['level']

    def __str__(self):
        return self.name


class Section(models.Model):
    """
    Classroom section identifier (e.g. A, B, C, D).
    """
    name = models.CharField(max_length=20, unique=True, help_text="e.g. A, B, C, D")
    description = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True, help_text="Designates whether this section is available for offerings.")

    class Meta:
        verbose_name = 'Section'
        verbose_name_plural = 'Sections'
        ordering = ['name']

    def __str__(self):
        return f"Section {self.name}"


class Stream(models.Model):
    """
    Curriculum specialization stream (General Secondary, Natural Science, Social Science).
    """
    code = models.CharField(max_length=20, unique=True, help_text="e.g. GENERAL, NATURAL, SOCIAL")
    name = models.CharField(max_length=100, help_text="e.g. General Secondary, Natural Science, Social Science")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True, help_text="Designates whether this stream is currently available.")

    class Meta:
        verbose_name = 'Curriculum Stream'
        verbose_name_plural = 'Curriculum Streams'
        ordering = ['name']

    def __str__(self):
        return self.name


class Subject(models.Model):
    """
    Master subject catalog for Ethiopian secondary schools.
    """
    code = models.CharField(max_length=20, unique=True, help_text="e.g. MATH-09, PHYS-11")
    name = models.CharField(max_length=100, help_text="e.g. Mathematics, Physics, Chemistry")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Subject'
        verbose_name_plural = 'Subjects'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class CurriculumSubject(models.Model):
    """
    Maps subjects to Grade and Stream with required credit/weekly hours.
    """
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE, related_name='curriculum_subjects')
    stream = models.ForeignKey(Stream, on_delete=models.SET_NULL, null=True, blank=True, related_name='curriculum_subjects')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='curriculum_allocations')
    credit_hours = models.PositiveSmallIntegerField(default=3, help_text="Periods per week")
    is_elective = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Curriculum Subject'
        verbose_name_plural = 'Curriculum Subjects'
        constraints = [
            models.UniqueConstraint(
                fields=['grade', 'stream', 'subject'],
                name='unique_grade_stream_subject'
            )
        ]

    def __str__(self):
        stream_str = f" [{self.stream.code}]" if self.stream else ""
        return f"{self.grade.name}{stream_str} - {self.subject.name}"


class ClassOffering(models.Model):
    """
    Active section offering for a specific Academic Year, Grade, Section, and Stream.
    e.g., "2026/2027 - Grade 11-A (Natural Science)"
    """
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='class_offerings')
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE, related_name='class_offerings')
    section = models.ForeignKey(Section, on_delete=models.CASCADE, related_name='class_offerings')
    stream = models.ForeignKey(Stream, on_delete=models.SET_NULL, null=True, blank=True, related_name='class_offerings')
    max_capacity = models.PositiveSmallIntegerField(default=50, help_text="Maximum students permitted in this classroom.")

    class Meta:
        verbose_name = 'Class Offering'
        verbose_name_plural = 'Class Offerings'
        constraints = [
            models.UniqueConstraint(
                fields=['academic_year', 'grade', 'section', 'stream'],
                name='unique_class_offering_per_year'
            )
        ]
        ordering = ['academic_year', 'grade', 'section']

    def __str__(self):
        stream_str = f" ({self.stream.name})" if self.stream else ""
        return f"{self.academic_year.code}: {self.grade.name}-{self.section.name}{stream_str}"

    @property
    def display_name(self):
        stream_str = f" ({self.stream.name})" if self.stream else ""
        return f"{self.grade.name} - Section {self.section.name}{stream_str}"

    @property
    def enrolled_students_count(self):
        if hasattr(self, 'student_enrollments'):
            return self.student_enrollments.filter(status='ACTIVE').count()
        elif hasattr(self, 'enrollments'):
            return self.enrollments.filter(status='ACTIVE').count()
        return 0

    @property
    def is_full(self):
        return self.enrolled_students_count >= self.max_capacity

    @property
    def available_seats(self):
        return max(0, self.max_capacity - self.enrolled_students_count)
