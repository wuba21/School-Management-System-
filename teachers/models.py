import os
import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from academics.models import ClassOffering, Subject, AcademicYear


def teacher_photo_upload_path(instance, filename):
    """
    Generates a cryptographically random filename for uploaded teacher photos.
    Prevents directory traversal and malicious overwrites.
    """
    ext = filename.split('.')[-1].lower() if '.' in filename else 'jpg'
    safe_name = f"{uuid.uuid4().hex}.{ext}"
    return f"teachers/photos/{safe_name}"


class Teacher(models.Model):
    """
    Teacher professional profile, optionally linked OneToOne with a User account.
    Supports historical tracking, role separation, and soft-state employment status.
    """
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
    ]

    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
        ('ON_LEAVE', 'On Leave'),
        ('TRANSFERRED', 'Transferred / Departed'),
        ('RETIRED', 'Retired'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='teacher_profile'
    )
    employee_id = models.CharField(max_length=50, unique=True, help_text="Unique employee/payroll ID")
    first_name = models.CharField(max_length=50)
    father_name = models.CharField(max_length=50)
    grandfather_name = models.CharField(max_length=50, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    date_of_birth = models.DateField(null=True, blank=True, help_text="Date of birth")
    photo = models.ImageField(upload_to=teacher_photo_upload_path, blank=True, null=True, help_text="Teacher photograph")
    phone_number = models.CharField(max_length=20, blank=True, help_text="Primary phone number")
    email = models.EmailField(blank=True, help_text="Email address")
    address = models.TextField(blank=True, help_text="Residential or postal address")
    qualification = models.CharField(max_length=100, help_text="e.g. B.Ed in Mathematics, M.Sc in Physics")
    specialization = models.CharField(max_length=100, help_text="Primary teaching subject specialization")
    joining_date = models.DateField(help_text="Employment commencement date")
    employment_status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='ACTIVE',
        help_text="Current employment status"
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Teacher'
        verbose_name_plural = 'Teachers'
        ordering = ['first_name', 'father_name']

    def __str__(self):
        return f"{self.first_name} {self.father_name} ({self.employee_id})"

    @property
    def full_name(self):
        parts = [self.first_name, self.father_name, self.grandfather_name]
        return " ".join([p for p in parts if p]).strip()

    def save(self, *args, **kwargs):
        self.is_active = (self.employment_status == 'ACTIVE')
        super().save(*args, **kwargs)


class TeacherAssignment(models.Model):
    """
    Allocates a teacher to teach a specific subject in a specific ClassOffering.
    Preserves historical teaching assignments across academic years.
    """
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='assignments')
    class_offering = models.ForeignKey(ClassOffering, on_delete=models.CASCADE, related_name='teacher_assignments')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='teacher_assignments')
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='teacher_assignments'
    )
    is_primary = models.BooleanField(default=True, help_text="Marks primary subject instructor vs assistant.")
    assigned_at = models.DateTimeField(default=timezone.now)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'Teacher Assignment'
        verbose_name_plural = 'Teacher Assignments'
        constraints = [
            models.UniqueConstraint(
                fields=['teacher', 'class_offering', 'subject'],
                name='unique_teacher_class_subject'
            )
        ]

    def __str__(self):
        return f"{self.teacher.full_name} -> {self.class_offering} [{self.subject.name}]"

    def save(self, *args, **kwargs):
        if self.class_offering and not self.academic_year:
            self.academic_year = self.class_offering.academic_year
        super().save(*args, **kwargs)
