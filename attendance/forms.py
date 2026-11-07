"""
Forms for the Attendance Management System.
"""

from django import forms
from django.utils import timezone
from academics.models import AcademicYear, ClassOffering, Grade, Subject
from teachers.models import Teacher, TeacherAssignment
from attendance.models import AttendanceSession, AttendanceRecord


class AttendanceSessionCreateForm(forms.ModelForm):
    """
    Form to schedule/open a new attendance session.
    Role-aware: filters class offerings according to teacher assignments.
    """
    class Meta:
        model = AttendanceSession
        fields = ['class_offering', 'date', 'session_type', 'subject', 'remarks']
        widgets = {
            'class_offering': forms.Select(attrs={'class': 'form-select', 'required': 'required'}),
            'date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'required': 'required'}),
            'session_type': forms.Select(attrs={'class': 'form-select', 'required': 'required'}),
            'subject': forms.Select(attrs={'class': 'form-select'}),
            'remarks': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Optional session notes...'}),
        }

    def __init__(self, *args, user=None, academic_year=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        if not self.initial.get('date'):
            self.fields['date'].initial = timezone.now().date()

        # Determine academic year
        ay = academic_year or AcademicYear.objects.filter(is_current=True).first()

        offerings_qs = ClassOffering.objects.select_related('grade', 'section', 'stream')
        if ay:
            offerings_qs = offerings_qs.filter(academic_year=ay)

        # Teacher role restriction: only show classes assigned to this teacher
        is_teacher = False
        teacher_profile = None
        if user and user.is_authenticated:
            user_role = getattr(getattr(user, 'role', None), 'code', None)
            if user_role == 'TEACHER':
                is_teacher = True
                teacher_profile = getattr(user, 'teacher_profile', None)

        if is_teacher and teacher_profile:
            assigned_offering_ids = TeacherAssignment.objects.filter(
                teacher=teacher_profile
            ).values_list('class_offering_id', flat=True)
            offerings_qs = offerings_qs.filter(id__in=assigned_offering_ids)

        self.fields['class_offering'].queryset = offerings_qs.order_by('grade__level', 'section__name')

        # Subject choices
        if is_teacher and teacher_profile:
            assigned_subject_ids = TeacherAssignment.objects.filter(
                teacher=teacher_profile
            ).values_list('subject_id', flat=True)
            self.fields['subject'].queryset = Subject.objects.filter(id__in=assigned_subject_ids, is_active=True)
        else:
            self.fields['subject'].queryset = Subject.objects.filter(is_active=True).order_by('name')

        self.fields['subject'].required = False

    def clean(self):
        cleaned_data = super().clean()
        session_type = cleaned_data.get('session_type')
        subject = cleaned_data.get('subject')

        if session_type == 'PERIOD' and not subject:
            self.add_error('subject', "Subject is required for 'Subject Period' attendance.")

        return cleaned_data


class AttendanceFilterForm(forms.Form):
    """Filter bar for searching and narrowing attendance logs."""
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.all().order_by('-start_date'),
        required=False,
        empty_label="All Academic Years",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    grade = forms.ModelChoiceField(
        queryset=Grade.objects.filter(is_active=True).order_by('level'),
        required=False,
        empty_label="All Grades",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    class_offering = forms.ModelChoiceField(
        queryset=ClassOffering.objects.all().select_related('grade', 'section'),
        required=False,
        empty_label="All Class Offerings",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'})
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date'})
    )
    status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + AttendanceSession.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    session_type = forms.ChoiceField(
        choices=[('', 'All Session Types')] + AttendanceSession.SESSION_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )


class SingleRecordUpdateForm(forms.ModelForm):
    """Modal or detail form to correct a single student attendance record."""
    class Meta:
        model = AttendanceRecord
        fields = ['status', 'reason']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'reason': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Reason for absence/excuse'}),
        }
