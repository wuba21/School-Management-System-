"""
Forms for AI Assistant Module.
Provides interactive filtering for Academic Analysis, Attendance Analysis, Report Generator, and Chat.
"""

from django import forms
from academics.models import AcademicYear, Grade, ClassOffering, Subject
from students.models import Student


class ChatQueryForm(forms.Form):
    """
    User query input form for conversational school assistant.
    """
    query = forms.CharField(
        max_length=500,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Ask me anything about school statistics, subject scores, attendance, or rules...',
            'id': 'chatInput',
            'autocomplete': 'off',
        })
    )


class AcademicAnalysisFilterForm(forms.Form):
    """
    Filter form for Academic Performance Analysis.
    """
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.all().order_by('-start_date'),
        required=False,
        empty_label="All Academic Years",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    grade = forms.ModelChoiceField(
        queryset=Grade.objects.filter(is_active=True).order_by('level'),
        required=False,
        empty_label="All Grades (9–12)",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    class_offering = forms.ModelChoiceField(
        queryset=ClassOffering.objects.all().select_related('grade', 'section').order_by('grade__level', 'section__name'),
        required=False,
        empty_label="All Class Offerings",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Teacher scoping
        if user and getattr(user, 'role', None) and user.role.code == 'TEACHER':
            if hasattr(user, 'teacher_profile'):
                teacher = user.teacher_profile
                assigned_co_ids = list(teacher.assignments.values_list('class_offering_id', flat=True))
                self.fields['class_offering'].queryset = ClassOffering.objects.filter(id__in=assigned_co_ids)
                assigned_grade_ids = list(ClassOffering.objects.filter(id__in=assigned_co_ids).values_list('grade_id', flat=True).distinct())
                self.fields['grade'].queryset = Grade.objects.filter(id__in=assigned_grade_ids)


class AttendanceAnalysisFilterForm(forms.Form):
    """
    Filter form for Attendance Intelligence Analysis.
    """
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.all().order_by('-start_date'),
        required=False,
        empty_label="All Academic Years",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    grade = forms.ModelChoiceField(
        queryset=Grade.objects.filter(is_active=True).order_by('level'),
        required=False,
        empty_label="All Grades (9–12)",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    class_offering = forms.ModelChoiceField(
        queryset=ClassOffering.objects.all().select_related('grade', 'section').order_by('grade__level', 'section__name'),
        required=False,
        empty_label="All Class Offerings",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and getattr(user, 'role', None) and user.role.code == 'TEACHER':
            if hasattr(user, 'teacher_profile'):
                teacher = user.teacher_profile
                assigned_co_ids = list(teacher.assignments.values_list('class_offering_id', flat=True))
                self.fields['class_offering'].queryset = ClassOffering.objects.filter(id__in=assigned_co_ids)
                assigned_grade_ids = list(ClassOffering.objects.filter(id__in=assigned_co_ids).values_list('grade_id', flat=True).distinct())
                self.fields['grade'].queryset = Grade.objects.filter(id__in=assigned_grade_ids)


class AIReportExportForm(forms.Form):
    """
    Form to configure and download AI intelligence summaries in PDF or Excel.
    """
    REPORT_TYPE_CHOICES = [
        ('STUDENT_SUMMARY', 'Student Academic Performance Summary'),
        ('CLASS_DOSSIER', 'Class Section Comprehensive Analysis'),
        ('SUBJECT_DIAGNOSTIC', 'Subject Performance & Difficulty Diagnostic'),
        ('ATTENDANCE_PATTERNS', 'Attendance & Absenteeism Pattern Analysis'),
    ]

    FORMAT_CHOICES = [
        ('PDF', 'Print-Ready PDF Document (ReportLab)'),
        ('EXCEL', 'Data Spreadsheet (.xlsx via OpenPyXL)'),
    ]

    report_type = forms.ChoiceField(
        choices=REPORT_TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'reportTypeSelect'})
    )
    format = forms.ChoiceField(
        choices=FORMAT_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    student = forms.ModelChoiceField(
        queryset=Student.objects.filter(status='ACTIVE').order_by('first_name'),
        required=False,
        empty_label="Select Student...",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'studentSelect'})
    )
    class_offering = forms.ModelChoiceField(
        queryset=ClassOffering.objects.all().select_related('grade', 'section').order_by('grade__level', 'section__name'),
        required=False,
        empty_label="Select Class Section...",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'classSelect'})
    )
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.filter(is_active=True).order_by('name'),
        required=False,
        empty_label="Select Subject...",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'subjectSelect'})
    )
