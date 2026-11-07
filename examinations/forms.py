"""
Forms for Examination Management.
"""

from django import forms
from django.utils import timezone
from academics.models import AcademicYear, Grade, Stream, Subject, ClassOffering
from examinations.models import ExamType, Examination, ExamSubject


class ExaminationCreateForm(forms.ModelForm):
    """Form to schedule or configure a new formal assessment/examination."""
    class Meta:
        model = Examination
        fields = ['name', 'exam_type', 'academic_year', 'semester', 'grade', 'class_offering', 'start_date', 'end_date']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Semester 1 Midterm Examination', 'required': 'required'}),
            'exam_type': forms.Select(attrs={'class': 'form-select', 'required': 'required'}),
            'academic_year': forms.Select(attrs={'class': 'form-select', 'required': 'required'}),
            'semester': forms.Select(attrs={'class': 'form-select', 'required': 'required'}),
            'grade': forms.Select(attrs={'class': 'form-select'}),
            'class_offering': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'required': 'required'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'required': 'required'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Default academic year to active year
        current_year = AcademicYear.objects.filter(is_current=True).first()
        if current_year and not self.initial.get('academic_year'):
            self.fields['academic_year'].initial = current_year

        self.fields['academic_year'].queryset = AcademicYear.objects.filter(is_closed=False).order_by('-start_date')
        self.fields['exam_type'].queryset = ExamType.objects.filter(is_active=True).order_by('name')
        self.fields['grade'].queryset = Grade.objects.filter(is_active=True).order_by('level')
        self.fields['class_offering'].queryset = ClassOffering.objects.filter(academic_year=current_year).select_related('grade', 'section')
        self.fields['grade'].required = False
        self.fields['class_offering'].required = False


class ExamSubjectConfigForm(forms.ModelForm):
    """Configures a subject under an examination with marks thresholds."""
    class Meta:
        model = ExamSubject
        fields = ['subject', 'max_marks', 'pass_marks', 'weight_percentage', 'exam_date', 'start_time', 'end_time']
        widgets = {
            'subject': forms.Select(attrs={'class': 'form-select', 'required': 'required'}),
            'max_marks': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'min': '1', 'required': 'required'}),
            'pass_marks': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'min': '0', 'required': 'required'}),
            'weight_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '1', 'min': '1', 'max': '100'}),
            'exam_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
        }

    def __init__(self, *args, examination=None, grade=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['subject'].queryset = Subject.objects.filter(is_active=True).order_by('name')
        self.fields['exam_date'].required = False
        self.fields['start_time'].required = False
        self.fields['end_time'].required = False


class ExaminationFilterForm(forms.Form):
    """Filter bar for browsing examinations directory."""
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.all().order_by('-start_date'),
        required=False,
        empty_label="All Academic Years",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    semester = forms.ChoiceField(
        choices=[('', 'All Semesters')] + Examination.SEMESTER_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    exam_type = forms.ModelChoiceField(
        queryset=ExamType.objects.filter(is_active=True),
        required=False,
        empty_label="All Exam Types",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    grade = forms.ModelChoiceField(
        queryset=Grade.objects.filter(is_active=True).order_by('level'),
        required=False,
        empty_label="All Grades",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + Examination.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
