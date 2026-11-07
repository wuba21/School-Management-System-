"""
Forms for Timetable and Class Scheduling Management System.
Includes clean Bootstrap 5 styling, period/day configuration,
lesson entry forms with conflict validation, and approval forms.
"""

from django import forms
from django.db import models
from django.core.exceptions import ValidationError

from academics.models import AcademicYear, Grade, ClassOffering, Subject
from teachers.models import Teacher, TeacherAssignment
from timetable.models import (
    Classroom,
    SchoolDay,
    Period,
    Timetable,
    TimetableEntry,
    DAY_OF_WEEK_CHOICES,
    DAY_NAME_MAP,
)


class ClassroomForm(forms.ModelForm):
    """Form for adding and editing physical classrooms and laboratories."""
    class Meta:
        model = Classroom
        fields = ['name', 'code', 'building', 'room_type', 'capacity', 'is_active', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Block A - Room 101'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. R-101 or LAB-CHEM'}),
            'building': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Main Academic Block'}),
            'room_type': forms.Select(attrs={'class': 'form-select'}),
            'capacity': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 50'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Facilities, equipment, or notes...'}),
        }


class SchoolDayForm(forms.ModelForm):
    """Form to configure school working days."""
    class Meta:
        model = SchoolDay
        fields = ['academic_year', 'day_of_week', 'name', 'short_name', 'order', 'is_active']
        widgets = {
            'academic_year': forms.Select(attrs={'class': 'form-select'}),
            'day_of_week': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Monday'}),
            'short_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Mon'}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 7}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class PeriodForm(forms.ModelForm):
    """Form to configure daily timetable periods and break slots."""
    class Meta:
        model = Period
        fields = ['academic_year', 'period_number', 'name', 'start_time', 'end_time', 'is_break', 'break_type', 'is_active']
        widgets = {
            'academic_year': forms.Select(attrs={'class': 'form-select'}),
            'period_number': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Period 1 or Lunch Break'}),
            'start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'is_break': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_is_break'}),
            'break_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_break_type'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        st = cleaned_data.get('start_time')
        et = cleaned_data.get('end_time')
        if st and et and st >= et:
            raise ValidationError({'end_time': "Period end time must be after start time."})
        return cleaned_data


class TimetableCreateForm(forms.ModelForm):
    """Form to initiate a new class timetable draft."""
    class Meta:
        model = Timetable
        fields = ['academic_year', 'class_offering', 'name', 'valid_from', 'valid_until']
        widgets = {
            'academic_year': forms.Select(attrs={'class': 'form-select', 'id': 'id_academic_year'}),
            'class_offering': forms.Select(attrs={'class': 'form-select', 'id': 'id_class_offering'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Leave blank for automatic name generation'}),
            'valid_from': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'valid_until': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].required = False
        self.fields['academic_year'].queryset = AcademicYear.objects.all().order_by('-start_date')
        current_year = AcademicYear.objects.filter(is_current=True).first()
        if current_year and not self.initial.get('academic_year'):
            self.initial['academic_year'] = current_year.id
            self.fields['class_offering'].queryset = ClassOffering.objects.filter(academic_year=current_year).select_related('grade', 'section')


class TimetableEntryForm(forms.ModelForm):
    """Form to schedule an individual lesson entry within a timetable."""
    class Meta:
        model = TimetableEntry
        fields = ['day_of_week', 'period', 'subject', 'teacher', 'classroom', 'notes']
        widgets = {
            'day_of_week': forms.Select(attrs={'class': 'form-select'}),
            'period': forms.Select(attrs={'class': 'form-select'}),
            'subject': forms.Select(attrs={'class': 'form-select'}),
            'teacher': forms.Select(attrs={'class': 'form-select'}),
            'classroom': forms.Select(attrs={'class': 'form-select'}),
            'notes': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional lesson note / focus'}),
        }

    def __init__(self, timetable=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if timetable:
            ay = timetable.academic_year
            # Only instructional non-break active periods
            self.fields['period'].queryset = Period.objects.filter(
                models.Q(academic_year=ay) | models.Q(academic_year__isnull=True),
                is_active=True,
                is_break=False
            ).order_by('period_number')

            # Classroom active only
            self.fields['classroom'].queryset = Classroom.objects.filter(is_active=True).order_by('building', 'name')
            self.fields['classroom'].required = False

            # Active teachers only
            self.fields['teacher'].queryset = Teacher.objects.filter(is_active=True).order_by('first_name', 'father_name')

            # Only subjects offered in this curriculum or class offering
            self.fields['subject'].queryset = Subject.objects.filter(is_active=True).order_by('name')


class TimetableApprovalForm(forms.Form):
    """Committee review form to authorize or return a timetable."""
    decision = forms.ChoiceField(
        choices=[('APPROVED', 'Approve Timetable'), ('REJECTED', 'Return to Draft for Revisions')],
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )
    comments = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Enter review committee notes, feedback, or justification...'})
    )


class TimetableCopyForm(forms.Form):
    """Form to clone a timetable structure into another class offering."""
    target_class_offering = forms.ModelChoiceField(
        queryset=ClassOffering.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label="Target Class Offering"
    )

    def __init__(self, source_timetable, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Exclude source class offering
        self.fields['target_class_offering'].queryset = ClassOffering.objects.filter(
            academic_year=source_timetable.academic_year
        ).exclude(pk=source_timetable.class_offering_id).select_related('grade', 'section')


class TimetableFilterForm(forms.Form):
    """Form for filtering timetable lists and dashboards."""
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.all().order_by('-start_date'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    grade = forms.ModelChoiceField(
        queryset=Grade.objects.filter(is_active=True).order_by('level'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + Timetable.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    teacher = forms.ModelChoiceField(
        queryset=Teacher.objects.filter(is_active=True).order_by('first_name'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
