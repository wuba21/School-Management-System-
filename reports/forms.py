"""
Report and Analytics Filter Forms for SSMS.
Provides unified, multi-dimensional filtering across academic years, grades, classes,
sections, streams, subjects, examinations, teachers, and date ranges.
"""

from django import forms
from django.utils import timezone
from academics.models import AcademicYear, Grade, Section, Stream, ClassOffering, Subject
from examinations.models import Examination
from teachers.models import Teacher


class ReportFilterForm(forms.Form):
    """
    Unified filter form for reporting and analytics views.
    All fields are optional to allow flexible drill-down.
    """
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.all().order_by('-start_date'),
        required=False,
        empty_label="All Academic Years",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'filter_academic_year'})
    )
    grade = forms.ModelChoiceField(
        queryset=Grade.objects.filter(is_active=True).order_by('level'),
        required=False,
        empty_label="All Grades (9-12)",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'filter_grade'})
    )
    class_offering = forms.ModelChoiceField(
        queryset=ClassOffering.objects.all().select_related('grade', 'section', 'academic_year').order_by('grade__level', 'section__name'),
        required=False,
        empty_label="All Classes / Sections",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'filter_class_offering'})
    )
    section = forms.ModelChoiceField(
        queryset=Section.objects.filter(is_active=True).order_by('name'),
        required=False,
        empty_label="All Sections",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'filter_section'})
    )
    stream = forms.ModelChoiceField(
        queryset=Stream.objects.filter(is_active=True).order_by('name'),
        required=False,
        empty_label="All Streams",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'filter_stream'})
    )
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.filter(is_active=True).order_by('name'),
        required=False,
        empty_label="All Subjects",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'filter_subject'})
    )
    examination = forms.ModelChoiceField(
        queryset=Examination.objects.all().order_by('-start_date'),
        required=False,
        empty_label="All Examinations",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'filter_examination'})
    )
    teacher = forms.ModelChoiceField(
        queryset=Teacher.objects.filter(is_active=True).order_by('first_name', 'father_name'),
        required=False,
        empty_label="All Teachers",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'filter_teacher'})
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date', 'id': 'filter_date_from'})
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date', 'id': 'filter_date_to'})
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': 'Search student / teacher / ID...',
            'id': 'filter_search'
        })
    )

    def __init__(self, *args, **kwargs):
        academic_year_id = kwargs.pop('academic_year_id', None)
        teacher_user = kwargs.pop('teacher_user', None)
        super().__init__(*args, **kwargs)

        # Narrow class offerings if an academic year is explicitly filtered
        if academic_year_id:
            self.fields['class_offering'].queryset = self.fields['class_offering'].queryset.filter(
                academic_year_id=academic_year_id
            )

        # If logged in user is a Teacher, restrict teacher filter to themselves
        if teacher_user and hasattr(teacher_user, 'teacher_profile'):
            self.fields['teacher'].queryset = Teacher.objects.filter(id=teacher_user.teacher_profile.id)
            self.fields['teacher'].initial = teacher_user.teacher_profile.id
