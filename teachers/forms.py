"""
Teacher Management Forms for SSMS.

Includes:
  - TeacherRegistrationForm (with auto ID generation and photo validation)
  - TeacherEditForm (tracking field-level change history)
  - TeacherStatusUpdateForm (with mandatory justification remarks)
  - TeacherAssignmentForm (assigning teacher to class offering & subject)
"""

import os
from datetime import date
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from teachers.models import Teacher, TeacherAssignment
from academics.models import AcademicYear, ClassOffering, Subject
from teachers.services import TeacherIDService, FileUploadSecurityService


class TeacherRegistrationForm(forms.ModelForm):
    """
    Teacher registration form with automated ID generation, safe photo upload,
    and demographic validation.
    """
    auto_generate_teacher_id = forms.BooleanField(
        required=False,
        initial=True,
        label="Auto-generate Teacher ID",
        help_text="Uncheck to enter an existing government payroll or school ID."
    )

    class Meta:
        model = Teacher
        fields = [
            'employee_id',
            'first_name',
            'father_name',
            'grandfather_name',
            'gender',
            'date_of_birth',
            'photo',
            'phone_number',
            'email',
            'address',
            'qualification',
            'specialization',
            'joining_date',
            'employment_status',
        ]
        widgets = {
            'employee_id': forms.TextInput(attrs={'class': 'form-control font-monospace', 'placeholder': 'e.g. EMP/2026/0001'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'father_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Father Name'}),
            'grandfather_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Grandfather Name'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*', 'onchange': 'previewImage(this, "photo-preview")'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+251 91 123 4567'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'teacher@school.edu.et'}),
            'address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Kebele, Town, Woreda'}),
            'qualification': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. B.Ed in Physics, M.Sc in Mathematics'}),
            'specialization': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Mathematics, Physics, Chemistry'}),
            'joining_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'employment_status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['employee_id'].required = False
        self.fields['grandfather_name'].required = False
        self.fields['date_of_birth'].required = False
        self.fields['photo'].required = False
        self.fields['phone_number'].required = False
        self.fields['email'].required = False
        self.fields['address'].required = False

        if not self.initial.get('joining_date'):
            self.fields['joining_date'].initial = timezone.localdate()

        # Suggest next ID if field is blank
        if not self.data and not self.initial.get('employee_id'):
            try:
                suggested_id = TeacherIDService.generate_next_teacher_id()
                self.fields['employee_id'].initial = suggested_id
                self.fields['employee_id'].widget.attrs['placeholder'] = f"Suggested: {suggested_id}"
            except Exception:
                pass

    def clean_employee_id(self):
        num = self.cleaned_data.get('employee_id', '')
        if not num or not num.strip():
            num = TeacherIDService.generate_next_teacher_id()
        num = num.strip()
        return TeacherIDService.validate_teacher_id(num)

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and hasattr(photo, 'file'):
            return FileUploadSecurityService.validate_image_file(photo)
        return photo

    def clean_date_of_birth(self):
        dob = self.cleaned_data.get('date_of_birth')
        if dob:
            today = timezone.localdate()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if age < 18:
                raise ValidationError("Teacher must be at least 18 years old.")
            if age > 80:
                raise ValidationError("Please enter a valid date of birth.")
        return dob

    def clean_first_name(self):
        name = self.cleaned_data.get('first_name', '').strip()
        if not name.replace('-', '').replace(' ', '').isalpha():
            raise ValidationError("First name must contain only letters.")
        return name.title()

    def clean_father_name(self):
        name = self.cleaned_data.get('father_name', '').strip()
        if not name.replace('-', '').replace(' ', '').isalpha():
            raise ValidationError("Father name must contain only letters.")
        return name.title()

    def clean_grandfather_name(self):
        name = self.cleaned_data.get('grandfather_name', '').strip()
        if name and not name.replace('-', '').replace(' ', '').isalpha():
            raise ValidationError("Grandfather name must contain only letters.")
        return name.title() if name else ''


class TeacherEditForm(forms.ModelForm):
    """
    Form for updating an existing teacher record with change detection.
    """
    class Meta:
        model = Teacher
        fields = [
            'first_name',
            'father_name',
            'grandfather_name',
            'gender',
            'date_of_birth',
            'photo',
            'phone_number',
            'email',
            'address',
            'qualification',
            'specialization',
            'joining_date',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'father_name': forms.TextInput(attrs={'class': 'form-control'}),
            'grandfather_name': forms.TextInput(attrs={'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'date_of_birth': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*', 'onchange': 'previewImage(this, "photo-preview")'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'qualification': forms.TextInput(attrs={'class': 'form-control'}),
            'specialization': forms.TextInput(attrs={'class': 'form-control'}),
            'joining_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo and hasattr(photo, 'file'):
            return FileUploadSecurityService.validate_image_file(photo)
        return photo

    def get_diff(self):
        """Returns dict of changed fields: {field: {'old': ..., 'new': ...}}"""
        diff = {}
        for field in self.changed_data:
            old_val = getattr(self.instance, field)
            new_val = self.cleaned_data.get(field)
            diff[field] = {
                'old': str(old_val) if old_val is not None else '',
                'new': str(new_val) if new_val is not None else ''
            }
        return diff


class TeacherStatusUpdateForm(forms.Form):
    """
    Form for updating teacher employment status with required justification remarks.
    """
    employment_status = forms.ChoiceField(
        choices=Teacher.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    remarks = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Mandatory administrative justification for status change...'}),
        help_text="Provide official remarks (e.g. Maternity Leave approval, Transfer to Gambella Secondary School, Retirement)."
    )

    def __init__(self, *args, teacher=None, **kwargs):
        super().__init__(*args, **kwargs)
        if teacher:
            self.fields['employment_status'].initial = teacher.employment_status


class TeacherAssignmentForm(forms.ModelForm):
    """
    Form for allocating a teacher to a specific Class Offering and Subject.
    """
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.filter(is_closed=False).order_by('-start_date'),
        required=True,
        empty_label="-- Select Academic Year --",
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Select academic year for this teaching assignment."
    )

    class_offering = forms.ModelChoiceField(
        queryset=ClassOffering.objects.select_related('grade', 'section', 'stream', 'academic_year').all(),
        required=True,
        empty_label="-- Select Classroom Section --",
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Select grade and section."
    )

    subject = forms.ModelChoiceField(
        queryset=Subject.objects.filter(is_active=True).order_by('name'),
        required=True,
        empty_label="-- Select Subject --",
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Select subject to be taught."
    )

    is_primary = forms.BooleanField(
        required=False,
        initial=True,
        label="Primary Instructor",
        help_text="Check if teacher is primary course instructor."
    )

    notes = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional remarks or period schedule...'}),
        help_text="e.g. Periods: Mon/Wed/Fri Period 2"
    )

    class Meta:
        model = TeacherAssignment
        fields = ['academic_year', 'class_offering', 'subject', 'is_primary', 'notes']

    def __init__(self, *args, teacher=None, **kwargs):
        self.teacher = teacher
        super().__init__(*args, **kwargs)

        current_ay = AcademicYear.objects.filter(is_current=True).first()
        if current_ay:
            self.fields['academic_year'].initial = current_ay
            self.fields['class_offering'].queryset = ClassOffering.objects.filter(
                academic_year=current_ay
            ).select_related('grade', 'section', 'stream')

    def clean(self):
        cleaned_data = super().clean()
        ay = cleaned_data.get('academic_year')
        offering = cleaned_data.get('class_offering')
        subject = cleaned_data.get('subject')

        if offering and ay and offering.academic_year_id != ay.id:
            self.add_error('class_offering', "Selected classroom does not belong to the chosen academic year.")

        if self.teacher and offering and subject:
            existing = TeacherAssignment.objects.filter(
                teacher=self.teacher,
                class_offering=offering,
                subject=subject
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise ValidationError(
                    f"{self.teacher.full_name} is already assigned to teach {subject.name} in {offering}."
                )

        return cleaned_data
