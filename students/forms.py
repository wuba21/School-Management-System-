"""
Student Management Forms for SSMS.

Forms:
  - StudentRegistrationForm : Full admission registration including optional class enrollment
  - StudentEditForm         : Comprehensive edit form for existing student profiles
  - StudentEnrollmentForm   : Assigns a student to a class offering for a specific academic year
  - StudentStatusUpdateForm : Manages student status transitions with audit remarks
"""

import re
from datetime import date
from django import forms
from django.core.exceptions import ValidationError

from students.models import Student, StudentEnrollment, StudentIDCard, StudentCertificate
from academics.models import AcademicYear, Grade, ClassOffering, Stream
from teachers.models import TeacherAssignment
from students.services import AdmissionNumberService, FileUploadSecurityService


class StudentRegistrationForm(forms.ModelForm):
    """
    Form for registering a new student into the school system.
    Supports auto-generated or manual admission numbers, Ethiopian three-part names,
    emergency contact info, and optional initial classroom enrollment.
    """
    auto_generate_admission_number = forms.BooleanField(
        required=False,
        initial=True,
        label="Auto-generate Admission Number",
        help_text="Uncheck to provide a custom or legacy school admission number."
    )

    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.filter(is_closed=False).order_by('-start_date'),
        required=False,
        empty_label="-- Select Academic Year --",
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Select academic year for initial enrollment."
    )

    class_offering = forms.ModelChoiceField(
        queryset=ClassOffering.objects.select_related('grade', 'section', 'stream', 'academic_year').all(),
        required=False,
        empty_label="-- Select Class & Section (Optional) --",
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Select classroom to enroll the student immediately upon registration."
    )

    class Meta:
        model = Student
        fields = [
            'admission_number',
            'first_name',
            'father_name',
            'grandfather_name',
            'gender',
            'date_of_birth',
            'photo',
            'phone_number',
            'address',
            'emergency_contact_name',
            'emergency_contact_phone',
            'emergency_contact_relation',
        ]
        widgets = {
            'admission_number': forms.TextInput(attrs={
                'class': 'form-control font-monospace',
                'placeholder': 'e.g. SSMS/2026/0001',
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': "Student's given name (e.g. Chaltu or Amanuel)",
            }),
            'father_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': "Father's name (e.g. Tolessa or Kebede)",
            }),
            'grandfather_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': "Grandfather's name (e.g. Gemechu or Desta)",
            }),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'date_of_birth': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'photo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
                'onchange': 'previewImage(this, "photo-preview")',
            }),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 0911223344 (optional)',
            }),
            'address': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Woreda 01, Godere, Majang Zone',
            }),
            'emergency_contact_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Full name of parent or primary guardian',
            }),
            'emergency_contact_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 0911223344',
            }),
            'emergency_contact_relation': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Father, Mother, Guardian, Uncle',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Allow admission_number to be omitted if auto-generating
        self.fields['admission_number'].required = False

        # Prepopulate current academic year
        current_year = AcademicYear.objects.filter(is_current=True).first()
        if current_year:
            self.fields['academic_year'].initial = current_year
            # Limit class offerings to active year by default
            self.fields['class_offering'].queryset = ClassOffering.objects.filter(
                academic_year=current_year
            ).select_related('grade', 'section', 'stream')

        # Suggest next admission number if field is blank
        if not self.data and not self.initial.get('admission_number'):
            try:
                suggested_number = AdmissionNumberService.generate_next_admission_number(current_year)
                self.fields['admission_number'].initial = suggested_number
            except Exception:
                pass

    def clean_first_name(self):
        name = self.cleaned_data.get('first_name', '').strip()
        if not name or len(name) < 2:
            raise ValidationError("Given name must be at least 2 characters.")
        if not re.match(r'^[A-Za-z\s\'-]+$', name):
            raise ValidationError("Name may only contain letters, spaces, hyphens, and apostrophes.")
        return name.title()

    def clean_father_name(self):
        name = self.cleaned_data.get('father_name', '').strip()
        if not name or len(name) < 2:
            raise ValidationError("Father's name must be at least 2 characters.")
        if not re.match(r'^[A-Za-z\s\'-]+$', name):
            raise ValidationError("Father's name may only contain letters, spaces, hyphens, and apostrophes.")
        return name.title()

    def clean_grandfather_name(self):
        name = self.cleaned_data.get('grandfather_name', '').strip()
        if not name or len(name) < 2:
            raise ValidationError("Grandfather's name must be at least 2 characters.")
        if not re.match(r'^[A-Za-z\s\'-]+$', name):
            raise ValidationError("Grandfather's name may only contain letters, spaces, hyphens, and apostrophes.")
        return name.title()

    def clean_admission_number(self):
        num = self.cleaned_data.get('admission_number') or ''
        num = num.strip()

        if not num:
            ay_id = self.data.get('academic_year')
            academic_year = AcademicYear.objects.filter(pk=ay_id).first() if ay_id else None
            num = AdmissionNumberService.generate_next_admission_number(academic_year)

        return AdmissionNumberService.validate_admission_number(num)

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            today = date.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if dob > today:
                raise ValidationError("Date of birth cannot be in the future.")
            if age < 10:
                raise ValidationError(f"Student age ({age} years) is below minimum secondary school age (10 years).")
            if age > 30:
                raise ValidationError(f"Student age ({age} years) exceeds standard secondary school age limit.")
        return dob

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and hasattr(photo, 'file'):
            return FileUploadSecurityService.validate_student_photo(photo)
        return photo

    def clean(self):
        cleaned_data = super().clean()
        offering = cleaned_data.get('class_offering')
        ay = cleaned_data.get('academic_year')

        if offering and ay and offering.academic_year_id != ay.id:
            self.add_error('class_offering', "Selected class offering does not belong to the chosen academic year.")

        return cleaned_data


class StudentEditForm(forms.ModelForm):
    """
    Form for updating an existing student profile.
    Maintains historical admission number integrity and validates photo uploads.
    """
    class Meta:
        model = Student
        fields = [
            'admission_number',
            'first_name',
            'father_name',
            'grandfather_name',
            'gender',
            'date_of_birth',
            'photo',
            'phone_number',
            'address',
            'emergency_contact_name',
            'emergency_contact_phone',
            'emergency_contact_relation',
            'status',
        ]
        widgets = {
            'admission_number': forms.TextInput(attrs={
                'class': 'form-control font-monospace',
            }),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'father_name': forms.TextInput(attrs={'class': 'form-control'}),
            'grandfather_name': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'date_of_birth': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'photo': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
                'onchange': 'previewImage(this, "photo-preview")',
            }),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_contact_name': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_contact_phone': forms.TextInput(attrs={'class': 'form-control'}),
            'emergency_contact_relation': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean_admission_number(self):
        num = self.cleaned_data.get('admission_number', '').strip()
        return AdmissionNumberService.validate_admission_number(num, exclude_student_id=self.instance.pk)

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and hasattr(photo, 'file'):
            return FileUploadSecurityService.validate_student_photo(photo)
        return photo


class StudentEnrollmentForm(forms.ModelForm):
    """
    Form for enrolling an existing student into a class offering for a given academic year.
    Strictly prevents duplicate enrollments within the same academic year.
    """
    class Meta:
        model = StudentEnrollment
        fields = ['academic_year', 'class_offering', 'status']
        widgets = {
            'academic_year': forms.Select(attrs={'class': 'form-select'}),
            'class_offering': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, student=None, **kwargs):
        self.student = student
        super().__init__(*args, **kwargs)
        self.fields['academic_year'].queryset = AcademicYear.objects.filter(is_closed=False).order_by('-start_date')
        
        # Default to current active academic year
        current_year = AcademicYear.objects.filter(is_current=True).first()
        if current_year and not self.is_bound:
            self.fields['academic_year'].initial = current_year
            self.fields['class_offering'].queryset = ClassOffering.objects.filter(
                academic_year=current_year
            ).select_related('grade', 'section', 'stream')
        else:
            self.fields['class_offering'].queryset = ClassOffering.objects.select_related(
                'grade', 'section', 'stream', 'academic_year'
            ).all()

    def clean(self):
        cleaned_data = super().clean()
        ay = cleaned_data.get('academic_year')
        offering = cleaned_data.get('class_offering')

        if offering and ay and offering.academic_year_id != ay.id:
            self.add_error('class_offering', "The selected class offering does not belong to the chosen academic year.")

        if self.student and ay:
            existing = StudentEnrollment.objects.filter(
                student=self.student,
                academic_year=ay
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise ValidationError(
                    f"Student {self.student.full_name} is already enrolled in {ay.name}. "
                    "A student cannot have more than one enrollment per academic year."
                )

        return cleaned_data


class StudentStatusUpdateForm(forms.Form):
    """
    Form to manage student academic status changes (Transferred, Graduated, Withdrawn, Active).
    Requires a logged administrative remark to preserve institutional accountability.
    """
    status = forms.ChoiceField(
        choices=Student.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="New Enrollment Status"
    )
    remarks = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'State the official reason or document reference (e.g. Transfer Certificate #, Relocation)...',
        }),
        required=True,
        help_text="Mandatory audit explanation for student status alteration."
    )


class IDCardFilterForm(forms.Form):
    """
    Step 22: Search and filter form for Student ID Card Management Hub.
    Supports teacher class-scoping and multi-parameter filtering.
    """
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': 'Search student name or admission no...',
        })
    )
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.all().order_by('-start_date'),
        required=False,
        empty_label='All Academic Years',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    grade = forms.ModelChoiceField(
        queryset=Grade.objects.all().order_by('level'),
        required=False,
        empty_label='All Grades',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    class_offering = forms.ModelChoiceField(
        queryset=ClassOffering.objects.all().select_related('grade', 'section', 'stream').order_by('grade__level', 'section__name'),
        required=False,
        empty_label='All Classes / Sections',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    status = forms.ChoiceField(
        choices=[
            ('ALL', 'All Card Statuses'),
            ('ACTIVE', 'Active / Valid Cards'),
            ('REVOKED', 'Revoked Cards'),
            ('EXPIRED', 'Expired Cards'),
            ('NOT_ISSUED', 'No Active Card Issued'),
        ],
        required=False,
        initial='ALL',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )

    def __init__(self, *args, teacher=None, **kwargs):
        super().__init__(*args, **kwargs)
        if teacher:
            assigned_offering_ids = ClassOffering.objects.filter(
                teacher_assignments__teacher=teacher
            ).values_list('id', flat=True)
            self.fields['class_offering'].queryset = ClassOffering.objects.filter(
                id__in=assigned_offering_ids
            ).select_related('grade', 'section', 'stream').order_by('grade__level', 'section__name')


class IDCardRevokeForm(forms.Form):
    """
    Step 22: Modal form for revoking an invalid or replaced Student ID card.
    """
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control form-control-sm',
            'rows': 3,
            'placeholder': 'State the official reason (e.g. Card reported lost/stolen, student transferred, photo replaced)...',
            'required': 'required'
        }),
        required=True,
        label="Revocation Reason",
        help_text="Mandatory justification for invalidating this ID card credential."
    )


class CertificateRequestForm(forms.ModelForm):
    """
    Step 23: Form for requesting a Student Transfer Certificate or Leaving Certificate.
    """
    class Meta:
        model = StudentCertificate
        fields = [
            'certificate_type',
            'academic_year',
            'last_grade',
            'section_name',
            'stream_name',
            'effective_date',
            'destination_school',
            'reason',
            'academic_standing',
            'conduct',
            'remarks',
        ]
        widgets = {
            'certificate_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_certificate_type'}),
            'academic_year': forms.Select(attrs={'class': 'form-select'}),
            'last_grade': forms.Select(attrs={'class': 'form-select'}),
            'section_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Section A'}),
            'stream_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Natural Science, Social Science, General'}),
            'effective_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'destination_school': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Receiving school name (Required for transfers)'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Reason for transfer or leaving (e.g. Family relocation, completed Grade 12)...'}),
            'academic_standing': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Promoted to Grade 10, Completed Grade 12 National Examinations'}),
            'conduct': forms.Select(choices=[
                ('Excellent', 'Excellent'),
                ('Very Good', 'Very Good'),
                ('Good', 'Good'),
                ('Satisfactory', 'Satisfactory')
            ], attrs={'class': 'form-select'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Official institutional notes, exam results, or clearance remarks...'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        cert_type = cleaned_data.get('certificate_type')
        dest_school = cleaned_data.get('destination_school')

        if cert_type == 'TRANSFER' and not dest_school:
            self.add_error('destination_school', "Destination school is required for Student Transfer Certificates.")

        return cleaned_data


class CertificateFilterForm(forms.Form):
    """
    Step 23: Multi-parameter filter form for Certificate Management Hub.
    """
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': 'Search student name, admission #, or certificate #...'
        })
    )
    certificate_type = forms.ChoiceField(
        choices=[
            ('ALL', 'All Certificate Types'),
            ('TRANSFER', 'Transfer Certificates'),
            ('LEAVING', 'Leaving Certificates'),
        ],
        required=False,
        initial='ALL',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.all().order_by('-start_date'),
        required=False,
        empty_label='All Academic Years',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    grade = forms.ModelChoiceField(
        queryset=Grade.objects.all().order_by('level'),
        required=False,
        empty_label='All Grades',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    status = forms.ChoiceField(
        choices=[
            ('ALL', 'All Statuses'),
            ('DRAFT', 'Draft'),
            ('SUBMITTED', 'Submitted for Review'),
            ('APPROVED', 'Approved (Pending Issue)'),
            ('ISSUED', 'Officially Issued'),
            ('REJECTED', 'Rejected'),
            ('REVOKED', 'Revoked / Cancelled'),
        ],
        required=False,
        initial='ALL',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )


class CertificateApprovalForm(forms.Form):
    """
    Step 23: Form for Principal or Admin to approve or reject a certificate request.
    """
    decision = forms.ChoiceField(
        choices=[
            ('APPROVE', 'Approve Certificate Request'),
            ('REJECT', 'Reject Request'),
        ],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )
    approval_remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control form-control-sm',
            'rows': 2,
            'placeholder': 'Optional approval remarks or instructions for the registrar...'
        })
    )
    rejection_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control form-control-sm',
            'rows': 2,
            'placeholder': 'Mandatory justification if rejecting this request...'
        })
    )

    def clean(self):
        cleaned_data = super().clean()
        decision = cleaned_data.get('decision')
        rejection_reason = cleaned_data.get('rejection_reason')

        if decision == 'REJECT' and not rejection_reason:
            self.add_error('rejection_reason', "A clear justification is required when rejecting a certificate request.")

        return cleaned_data


class CertificateRevokeForm(forms.Form):
    """
    Step 23: Modal form for revoking an issued or approved certificate.
    """
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control form-control-sm',
            'rows': 3,
            'placeholder': 'State the official reason for revocation (e.g. Issued in error, student cancelled transfer, incorrect grades)...',
            'required': 'required'
        }),
        required=True,
        label="Revocation Reason",
        help_text="Mandatory justification for revoking this official certificate."
    )
