"""
Academic Management Forms for SSMS.

Includes:
  - AcademicYearForm (calendar dates, status flags, validation)
  - GradeForm (grade level management)
  - SectionForm (configurable sections)
  - StreamForm (curriculum streams e.g. Natural/Social Science)
  - SubjectForm (master subject catalog)
  - ClassOfferingForm (section allocation per academic year)
  - CurriculumSubjectForm (subject assignment to grade/stream)
  - ClassEnrollmentForm & ClassBatchEnrollmentForm (student enrollment into classes)
  - ClassTeacherAssignmentForm (allocating teachers to classes)
"""

from django import forms
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils import timezone

from academics.models import AcademicYear, Grade, Section, Stream, Subject, CurriculumSubject, ClassOffering
from students.models import Student, StudentEnrollment
from teachers.models import Teacher, TeacherAssignment


class AcademicYearForm(forms.ModelForm):
    """Form for creating and editing Academic Years."""

    class Meta:
        model = AcademicYear
        fields = ['name', 'code', 'start_date', 'end_date', 'is_current', 'is_closed']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 2026/2027 (2018/2019 E.C.)'}),
            'code': forms.TextInput(attrs={'class': 'form-control font-monospace', 'placeholder': 'e.g. AY-2026'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_current': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_closed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get('start_date')
        end = cleaned_data.get('end_date')

        if start and end and start >= end:
            self.add_error('end_date', "End date must be strictly after the start date.")

        return cleaned_data


class GradeForm(forms.ModelForm):
    """Form for managing Grade levels."""

    class Meta:
        model = Grade
        fields = ['name', 'level', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Grade 9, Grade 10'}),
            'level': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '9, 10, 11, or 12', 'min': 1, 'max': 15}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Description or cycle...'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class SectionForm(forms.ModelForm):
    """Form for managing configurable Section names."""

    class Meta:
        model = Section
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. A, B, C, Red, Blue'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional room designation...'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_name(self):
        return self.cleaned_data.get('name', '').strip().upper()


class StreamForm(forms.ModelForm):
    """Form for managing curriculum streams."""

    class Meta:
        model = Stream
        fields = ['code', 'name', 'description', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control font-monospace', 'placeholder': 'e.g. NATURAL, SOCIAL'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Natural Science, Social Science'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Optional notes on stream...'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_code(self):
        return self.cleaned_data.get('code', '').strip().upper()


class SubjectForm(forms.ModelForm):
    """Form for managing master subjects."""

    class Meta:
        model = Subject
        fields = ['code', 'name', 'description', 'is_active']
        widgets = {
            'code': forms.TextInput(attrs={'class': 'form-control font-monospace', 'placeholder': 'e.g. MATH-09, BIO-11'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Mathematics, Biology'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Subject outline...'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_code(self):
        return self.cleaned_data.get('code', '').strip().upper()


class ClassOfferingForm(forms.ModelForm):
    """Form for provisioning classrooms for an academic year."""

    class Meta:
        model = ClassOffering
        fields = ['academic_year', 'grade', 'section', 'stream', 'max_capacity']
        widgets = {
            'academic_year': forms.Select(attrs={'class': 'form-select'}),
            'grade': forms.Select(attrs={'class': 'form-select'}),
            'section': forms.Select(attrs={'class': 'form-select'}),
            'stream': forms.Select(attrs={'class': 'form-select'}),
            'max_capacity': forms.NumberInput(attrs={'class': 'form-control', 'min': 10, 'max': 100}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filter to active options
        self.fields['academic_year'].queryset = AcademicYear.objects.filter(is_closed=False).order_by('-start_date')
        self.fields['grade'].queryset = Grade.objects.filter(is_active=True).order_by('level')
        self.fields['section'].queryset = Section.objects.filter(is_active=True).order_by('name')
        self.fields['stream'].queryset = Stream.objects.filter(is_active=True).order_by('name')
        self.fields['stream'].required = False
        self.fields['stream'].empty_label = "-- General / No Stream --"

        current_ay = AcademicYear.objects.filter(is_current=True).first()
        if current_ay and not self.initial.get('academic_year'):
            self.fields['academic_year'].initial = current_ay

    def clean(self):
        cleaned_data = super().clean()
        ay = cleaned_data.get('academic_year')
        grade = cleaned_data.get('grade')
        section = cleaned_data.get('section')
        stream = cleaned_data.get('stream')

        if ay and grade and section:
            existing = ClassOffering.objects.filter(
                academic_year=ay,
                grade=grade,
                section=section,
                stream=stream
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                stream_str = f" ({stream.name})" if stream else ""
                raise ValidationError(
                    f"Classroom offering for {grade.name} - Section {section.name}{stream_str} already exists in {ay.name}."
                )

        return cleaned_data


class CurriculumSubjectForm(forms.ModelForm):
    """Form for assigning subjects to Grade levels and Streams."""

    class Meta:
        model = CurriculumSubject
        fields = ['grade', 'stream', 'subject', 'credit_hours', 'is_elective']
        widgets = {
            'grade': forms.Select(attrs={'class': 'form-select'}),
            'stream': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.Select(attrs={'class': 'form-select'}),
            'credit_hours': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 10}),
            'is_elective': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['grade'].queryset = Grade.objects.filter(is_active=True).order_by('level')
        self.fields['stream'].queryset = Stream.objects.filter(is_active=True).order_by('name')
        self.fields['stream'].required = False
        self.fields['stream'].empty_label = "-- All Streams / General --"
        self.fields['subject'].queryset = Subject.objects.filter(is_active=True).order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        grade = cleaned_data.get('grade')
        stream = cleaned_data.get('stream')
        subject = cleaned_data.get('subject')

        if grade and subject:
            existing = CurriculumSubject.objects.filter(
                grade=grade,
                stream=stream,
                subject=subject
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                stream_str = f" in {stream.name}" if stream else ""
                raise ValidationError(
                    f"{subject.name} is already assigned to {grade.name}{stream_str}."
                )

        return cleaned_data


class ClassEnrollmentForm(forms.Form):
    """Form to enroll an individual student into a specific classroom."""
    student = forms.ModelChoiceField(
        queryset=Student.objects.filter(status='ACTIVE').order_by('first_name', 'father_name'),
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text="Select an active student to enroll."
    )

    def __init__(self, *args, class_offering=None, **kwargs):
        self.class_offering = class_offering
        super().__init__(*args, **kwargs)

        if class_offering:
            # Exclude students already enrolled in this academic year
            enrolled_ids = StudentEnrollment.objects.filter(
                academic_year=class_offering.academic_year
            ).values_list('student_id', flat=True)
            self.fields['student'].queryset = Student.objects.filter(
                status='ACTIVE'
            ).exclude(pk__in=enrolled_ids).order_by('first_name', 'father_name')


class ClassTeacherAssignmentForm(forms.ModelForm):
    """Form to assign a teacher to a specific Class Offering and Subject."""

    class Meta:
        model = TeacherAssignment
        fields = ['teacher', 'subject', 'is_primary', 'notes']
        widgets = {
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.Select(attrs={'class': 'form-select'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Periods 1 & 2 Mon/Wed'}),
        }

    def __init__(self, *args, class_offering=None, **kwargs):
        self.class_offering = class_offering
        super().__init__(*args, **kwargs)

        # Filter teachers to active only
        self.fields['teacher'].queryset = Teacher.objects.filter(is_active=True).order_by('first_name')

        if class_offering:
            # Prefer subjects in this grade's curriculum
            curriculum_subjects = CurriculumSubject.objects.filter(
                grade=class_offering.grade
            )
            if class_offering.stream:
                curriculum_subjects = curriculum_subjects.filter(
                    Q(stream=class_offering.stream) | Q(stream__isnull=True)
                )
            subj_ids = curriculum_subjects.values_list('subject_id', flat=True)
            if subj_ids.exists():
                self.fields['subject'].queryset = Subject.objects.filter(
                    pk__in=subj_ids, is_active=True
                ).order_by('name')
            else:
                self.fields['subject'].queryset = Subject.objects.filter(is_active=True).order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        teacher = cleaned_data.get('teacher')
        subject = cleaned_data.get('subject')

        if self.class_offering and teacher and subject:
            existing = TeacherAssignment.objects.filter(
                teacher=teacher,
                class_offering=self.class_offering,
                subject=subject
            )
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise ValidationError(
                    f"{teacher.full_name} is already assigned to teach {subject.name} in {self.class_offering}."
                )

        return cleaned_data
