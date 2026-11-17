import os
import uuid
from datetime import date
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
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

    def get_full_name(self):
        return self.full_name


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


class StudentIDCard(models.Model):
    """
    Step 22: Official Student Identification Card credential record.
    Supports secure offline QR verification via UUID without exposing student PII,
    lifecycle management (ACTIVE, REVOKED, EXPIRED, REPLACED),
    batch issuance, reprint tracking, and audit logging.
    """
    STATUS_CHOICES = [
        ('ACTIVE', 'Active / Valid'),
        ('REVOKED', 'Revoked / Invalidated'),
        ('EXPIRED', 'Expired'),
        ('REPLACED', 'Replaced by New Card'),
    ]

    card_uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Opaque unique token for QR code verification without exposing student PII"
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='id_cards'
    )
    enrollment = models.ForeignKey(
        StudentEnrollment,
        on_delete=models.CASCADE,
        related_name='id_cards',
        null=True,
        blank=True,
        help_text="Enrollment context (grade, section, stream) at time of issuance"
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='student_id_cards'
    )
    card_number = models.CharField(
        max_length=60,
        unique=True,
        help_text="Human-readable institutional card number (e.g. MSS-ID-2026-0001)"
    )
    issue_date = models.DateField(default=timezone.now)
    expiry_date = models.DateField(
        null=True,
        blank=True,
        help_text="Optional card expiry date (e.g. academic year end date)"
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='ACTIVE',
        db_index=True
    )
    reprint_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this card has been reprinted"
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revocation_reason = models.TextField(blank=True)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='issued_id_cards'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Student ID Card'
        verbose_name_plural = 'Student ID Cards'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'academic_year'],
                condition=models.Q(status='ACTIVE'),
                name='unique_active_student_id_card_per_year'
            )
        ]

    def __str__(self):
        return f"{self.card_number} - {self.student.full_name} [{self.get_status_display()}]"

    @property
    def is_valid(self):
        """Verifies if card is currently active and within valid date range."""
        if self.status != 'ACTIVE':
            return False
        if self.expiry_date and self.expiry_date < date.today():
            return False
        if self.student.status != 'ACTIVE':
            return False
        return True

    @property
    def verification_status(self):
        """Returns standard verification status string for QR validation."""
        if self.status == 'REVOKED':
            return 'REVOKED'
        if self.status == 'REPLACED':
            return 'REPLACED'
        if self.expiry_date and self.expiry_date < date.today():
            return 'EXPIRED'
        if self.status == 'EXPIRED':
            return 'EXPIRED'
        if self.student.status != 'ACTIVE':
            return 'STUDENT_INACTIVE'
        if self.status == 'ACTIVE':
            return 'VALID'
        return 'UNKNOWN'

    def revoke(self, reason="", user=None):
        """Revokes the ID card with timestamp and reason."""
        self.status = 'REVOKED'
        self.revoked_at = timezone.now()
        self.revocation_reason = reason
        self.save(update_fields=['status', 'revoked_at', 'revocation_reason', 'updated_at'])


class StudentCertificate(models.Model):
    """
    Step 23: Student Transfer and Leaving Certificate Record.
    Supports official preparation, multi-level review, approval workflow
    (DRAFT -> SUBMITTED -> APPROVED -> ISSUED, plus REJECTED and REVOKED),
    institutional reference numbering, Ethiopian & Gregorian calendar support,
    and internal verification without public PII exposure.
    """
    CERTIFICATE_TYPE_CHOICES = [
        ('TRANSFER', 'Student Transfer Certificate'),
        ('LEAVING', 'Student Leaving Certificate'),
    ]

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('SUBMITTED', 'Submitted for Review'),
        ('APPROVED', 'Approved by Principal'),
        ('REJECTED', 'Rejected'),
        ('ISSUED', 'Officially Issued'),
        ('REVOKED', 'Revoked / Cancelled'),
    ]

    certificate_uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
        help_text="Opaque unique token for internal verification"
    )
    certificate_type = models.CharField(
        max_length=20,
        choices=CERTIFICATE_TYPE_CHOICES,
        db_index=True
    )
    certificate_number = models.CharField(
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        db_index=True,
        help_text="Official institutional reference number (e.g. MSS-TC-2016-0001 or MSS-LC-2016-0001)"
    )
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name='certificates'
    )
    enrollment = models.ForeignKey(
        StudentEnrollment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='certificates',
        help_text="Student enrollment record at time of request"
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.PROTECT,
        related_name='certificates'
    )
    last_grade = models.ForeignKey(
        Grade,
        on_delete=models.PROTECT,
        related_name='certificates'
    )
    section_name = models.CharField(
        max_length=30,
        blank=True,
        help_text="Section name (e.g. Section A, Section B)"
    )
    stream_name = models.CharField(
        max_length=60,
        blank=True,
        help_text="Stream (e.g. Natural Science, Social Science, General Secondary)"
    )
    admission_date = models.DateField(
        null=True,
        blank=True,
        help_text="Original student admission date"
    )
    effective_date = models.DateField(
        default=date.today,
        help_text="Official date of transfer or departure"
    )
    destination_school = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name of the receiving school for transfers"
    )
    reason = models.TextField(
        blank=True,
        help_text="Official reason for transfer or leaving"
    )
    academic_standing = models.CharField(
        max_length=150,
        blank=True,
        help_text="Academic standing summary (e.g. Promoted to Grade 10, Completed Grade 12)"
    )
    conduct = models.CharField(
        max_length=50,
        default='Good',
        blank=True,
        help_text="Student general conduct (e.g. Excellent, Very Good, Good)"
    )
    remarks = models.TextField(
        blank=True,
        help_text="Official institutional remarks or verified examination results"
    )

    # Workflow & Lifecycle
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='DRAFT',
        db_index=True
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='requested_certificates'
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_certificates'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='approved_certificates',
        help_text="Principal or designated administrative approver"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_remarks = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)

    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='issued_certificates'
    )
    issue_date = models.DateField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='revoked_certificates'
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revocation_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Student Certificate'
        verbose_name_plural = 'Student Certificates'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'certificate_type', 'academic_year'],
                condition=models.Q(status__in=['DRAFT', 'SUBMITTED', 'APPROVED', 'ISSUED']),
                name='unique_active_certificate_per_student_type_year'
            )
        ]

    def __str__(self):
        ref = self.certificate_number or f"DRAFT-{self.pk}"
        return f"{self.get_certificate_type_display()} - {self.student.full_name} [{ref}]"

    @property
    def is_issued(self):
        return self.status == 'ISSUED'

    @property
    def is_approved(self):
        return self.status in ['APPROVED', 'ISSUED']

    @property
    def can_be_approved(self):
        return self.status in ['DRAFT', 'SUBMITTED']

    @property
    def can_be_issued(self):
        return self.status == 'APPROVED'

    @property
    def can_be_edited(self):
        return self.status in ['DRAFT', 'SUBMITTED']
