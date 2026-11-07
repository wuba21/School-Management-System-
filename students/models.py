import os
import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from academics.models import AcademicYear, Grade, ClassOffering


def student_photo_upload_to(instance, filename):
    """
    Generate an unguessable, safe UUID file path for uploaded student portraits.
    Prevents directory traversal, file overwrites, and malicious executable filenames.
    """
    ext = os.path.splitext(filename)[1].lower() if '.' in filename else '.jpg'
    safe_name = f"{uuid.uuid4().hex}{ext}"
    return f"students/photos/{safe_name}"


class Student(models.Model):
    """
    Student master profile supporting Ethiopian three-part naming.
    """
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
    ]

    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('TRANSFERRED', 'Transferred Out'),
        ('WITHDRAWN', 'Withdrawn'),
        ('DROPPED', 'Dropped Out'),
        ('GRADUATED', 'Graduated'),
    ]

    admission_number = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique student admission number (e.g. SSMS/2026/0001)"
    )
    first_name = models.CharField(max_length=50, help_text="Student's given name")
    father_name = models.CharField(max_length=50, help_text="Father's name")
    grandfather_name = models.CharField(max_length=50, help_text="Grandfather's name")
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    date_of_birth = models.DateField()
    photo = models.ImageField(
        upload_to=student_photo_upload_to,
        blank=True,
        null=True,
        help_text="Student portrait photograph (JPEG, PNG, WebP; max 2MB)"
    )
    phone_number = models.CharField(
        max_length=30,
        blank=True,
        help_text="Student or parent phone number, if available"
    )
    address = models.CharField(max_length=255, blank=True, help_text="Kebele/Zone/Village in Majang Zone")
    emergency_contact_name = models.CharField(max_length=100, help_text="Parent or guardian name")
    emergency_contact_phone = models.CharField(max_length=30, help_text="Primary phone number")
    emergency_contact_relation = models.CharField(max_length=50, help_text="e.g. Father, Mother, Guardian")
    admission_date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')

    class Meta:
        verbose_name = 'Student'
        verbose_name_plural = 'Students'
        ordering = ['first_name', 'father_name']

    def __str__(self):
        return f"{self.full_name} ({self.admission_number})"

    @property
    def full_name(self):
        return f"{self.first_name} {self.father_name} {self.grandfather_name}".strip()


class StudentEnrollment(models.Model):
    """
    Historical enrollment record linking a student to a class offering in an academic year.
    Preserves multi-year longitudinal records.
    """
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('PROMOTED', 'Promoted'),
        ('RETAINED', 'Retained / Repeat'),
        ('WITHDRAWN', 'Withdrawn'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrollments')
    class_offering = models.ForeignKey(ClassOffering, on_delete=models.CASCADE, related_name='student_enrollments')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='enrollments')
    enrollment_date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')

    class Meta:
        verbose_name = 'Student Enrollment'
        verbose_name_plural = 'Student Enrollments'
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'academic_year'],
                name='unique_student_enrollment_per_year'
            )
        ]
        ordering = ['-academic_year__start_date', 'student']

    def __str__(self):
        return f"{self.student.admission_number} - {self.class_offering}"

    def clean(self):
        try:
            if self.class_offering_id and self.academic_year_id:
                if self.class_offering.academic_year_id != self.academic_year_id:
                    raise ValidationError("Class offering must belong to the selected academic year.")
        except Exception as e:
            if isinstance(e, ValidationError):
                raise e


class PromotionRecord(models.Model):
    """
    Permanent academic history recording year-to-year progression, retention, or graduation.
    """
    DECISION_CHOICES = [
        ('PROMOTED', 'Promoted to Next Grade'),
        ('RETAINED', 'Retained in Same Grade'),
        ('GRADUATED', 'Graduated Secondary School'),
        ('CONDITIONAL', 'Conditional Promotion (Under Review)'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='promotion_records')
    from_academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name='promotions_from'
    )
    to_academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name='promotions_to'
    )
    from_grade = models.ForeignKey(
        Grade,
        on_delete=models.PROTECT,
        related_name='promotions_from_grade'
    )
    to_grade = models.ForeignKey(
        Grade,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='promotions_to_grade'
    )
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES)
    average_mark = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    rank_in_section = models.PositiveSmallIntegerField(null=True, blank=True)
    remarks = models.TextField(blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Principal or official authorizing this promotion"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Promotion Record'
        verbose_name_plural = 'Promotion Records'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student.admission_number}: {self.from_grade} -> {self.decision}"
