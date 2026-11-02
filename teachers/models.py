from django.db import models
from django.conf import settings
from academics.models import ClassOffering, Subject

class Teacher(models.Model):
    """
    Teacher professional profile, linked OneToOne with a User account.
    """
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='teacher_profile'
    )
    employee_id = models.CharField(max_length=50, unique=True, help_text="Unique employee/payroll ID")
    first_name = models.CharField(max_length=50)
    father_name = models.CharField(max_length=50)
    grandfather_name = models.CharField(max_length=50, blank=True)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    qualification = models.CharField(max_length=100, help_text="e.g. B.Ed in Mathematics, M.Sc in Physics")
    specialization = models.CharField(max_length=100, help_text="Primary teaching subject specialization")
    joining_date = models.DateField()
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


class TeacherAssignment(models.Model):
    """
    Allocates a teacher to teach a specific subject in a specific ClassOffering.
    """
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name='assignments')
    class_offering = models.ForeignKey(ClassOffering, on_delete=models.CASCADE, related_name='teacher_assignments')
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='teacher_assignments')
    is_primary = models.BooleanField(default=True, help_text="Marks primary subject instructor vs assistant.")

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
