from django.db import models
from django.contrib.auth.models import AbstractUser

class Role(models.Model):
    """
    Role definition for Role-Based Access Control (RBAC).
    """
    PRINCIPAL = 'PRINCIPAL'
    REGISTRAR = 'REGISTRAR'
    TEACHER = 'TEACHER'
    ADMIN = 'ADMIN'

    ROLE_CHOICES = [
        (PRINCIPAL, 'School Principal'),
        (REGISTRAR, 'Registrar'),
        (TEACHER, 'Teacher'),
        (ADMIN, 'System Administrator'),
    ]

    code = models.CharField(max_length=50, unique=True, choices=ROLE_CHOICES)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'User Role'
        verbose_name_plural = 'User Roles'
        ordering = ['name']

    def __str__(self):
        return self.name


class User(AbstractUser):
    """
    Custom user model for the school management system.
    Extends standard Django AbstractUser.
    """
    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
        help_text="Primary system role for permission enforcement."
    )
    phone_number = models.CharField(max_length=20, blank=True)
    is_approved = models.BooleanField(default=True, help_text="Designates whether this user has administrative approval.")

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['username']

    def __str__(self):
        role_label = self.role.name if self.role else "No Role"
        return f"{self.username} ({role_label})"

    @property
    def is_principal(self):
        return self.role is not None and self.role.code == Role.PRINCIPAL

    @property
    def is_registrar(self):
        return self.role is not None and self.role.code == Role.REGISTRAR

    @property
    def is_teacher_user(self):
        return self.role is not None and self.role.code == Role.TEACHER

    @property
    def is_sysadmin(self):
        return self.is_superuser or (self.role is not None and self.role.code == Role.ADMIN)
