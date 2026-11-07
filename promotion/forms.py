"""
Forms for Student Promotion, Batch Management, Graduation, and Status Transitions.
"""

from django import forms
from django.utils import timezone
from academics.models import AcademicYear, Grade, Section, Stream, ClassOffering
from students.models import Student
from promotion.models import (
    PromotionCriteria,
    PromotionBatch,
    PromotionRecord,
    GraduationRecord,
    StudentStatusHistory
)


class PromotionCriteriaForm(forms.ModelForm):
    """Form to manage school promotion threshold policies."""
    class Meta:
        model = PromotionCriteria
        fields = [
            'name', 'code', 'description',
            'minimum_average', 'max_failing_subjects',
            'require_all_core_passed', 'minimum_attendance_percentage',
            'is_active', 'is_default'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Majang Secondary Standard Policy', 'required': 'required'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. SEC-PROM-2026', 'required': 'required'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Policy details and committee guidelines...'}),
            'minimum_average': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'min': '0', 'max': '100', 'required': 'required'}),
            'max_failing_subjects': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'max': '10', 'required': 'required'}),
            'minimum_attendance_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'min': '0', 'max': '100', 'placeholder': 'Optional (e.g. 75.0)'}),
            'require_all_core_passed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class PromotionBatchCreateForm(forms.ModelForm):
    """Form to initiate a new promotion evaluation cohort."""
    class Meta:
        model = PromotionBatch
        fields = ['name', 'academic_year', 'target_academic_year', 'grade', 'promotion_criteria']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 2026/2027 Grade 9 to 10 Promotion', 'required': 'required'}),
            'academic_year': forms.Select(attrs={'class': 'form-select', 'required': 'required'}),
            'target_academic_year': forms.Select(attrs={'class': 'form-select', 'required': 'required'}),
            'grade': forms.Select(attrs={'class': 'form-select', 'required': 'required'}),
            'promotion_criteria': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_year = AcademicYear.objects.filter(is_current=True).first()
        if current_year and not self.initial.get('academic_year'):
            self.fields['academic_year'].initial = current_year

        self.fields['academic_year'].queryset = AcademicYear.objects.all().order_by('-start_date')
        self.fields['target_academic_year'].queryset = AcademicYear.objects.filter(is_closed=False).order_by('-start_date')
        self.fields['grade'].queryset = Grade.objects.filter(is_active=True).order_by('level')
        self.fields['promotion_criteria'].queryset = PromotionCriteria.objects.filter(is_active=True).order_by('-is_default')


class PromotionRecordEditForm(forms.ModelForm):
    """Form to adjust individual student proposed outcome and assigned destination class."""
    class Meta:
        model = PromotionRecord
        fields = ['final_outcome', 'next_class_offering', 'remarks']
        widgets = {
            'final_outcome': forms.Select(attrs={'class': 'form-select form-select-sm', 'required': 'required'}),
            'next_class_offering': forms.Select(attrs={'class': 'form-select form-select-sm'}),
            'remarks': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Reason or committee notes...'}),
        }

    def __init__(self, *args, target_academic_year=None, target_grade=None, **kwargs):
        super().__init__(*args, **kwargs)
        if target_academic_year and target_grade:
            self.fields['next_class_offering'].queryset = ClassOffering.objects.filter(
                academic_year=target_academic_year,
                grade=target_grade
            ).select_related('grade', 'section', 'stream')
        elif target_academic_year:
            self.fields['next_class_offering'].queryset = ClassOffering.objects.filter(
                academic_year=target_academic_year
            ).select_related('grade', 'section', 'stream')
        else:
            self.fields['next_class_offering'].queryset = ClassOffering.objects.all()
        self.fields['next_class_offering'].required = False


class PromotionApprovalForm(forms.Form):
    """Administrative review form for Principal or Committee approval."""
    DECISION_CHOICES = [
        ('APPROVED', 'Approve Batch for Final Promotion Enrollment'),
        ('REJECTED', 'Return / Reject Batch for Revision'),
    ]
    decision = forms.ChoiceField(
        choices=DECISION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select', 'required': 'required'})
    )
    comments = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Approval notes, conditions, or revision instructions...'})
    )


class StudentStatusChangeForm(forms.ModelForm):
    """Form to record student transfers, withdrawals, or status alterations."""
    student_id = forms.IntegerField(widget=forms.HiddenInput())

    class Meta:
        model = StudentStatusHistory
        fields = ['status_type', 'effective_date', 'reason', 'destination_school', 'documents_issued']
        widgets = {
            'status_type': forms.Select(attrs={'class': 'form-select', 'required': 'required'}),
            'effective_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'required': 'required'}),
            'reason': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Official rationale or circumstances...', 'required': 'required'}),
            'destination_school': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Destination school name and location (if transferring)'}),
            'documents_issued': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Leaving Certificate, Clearance Slip'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.initial.get('effective_date'):
            self.fields['effective_date'].initial = timezone.now().date()


class GraduationActionForm(forms.ModelForm):
    """Form to record Grade 12 graduation approval and certificate numbers."""
    class Meta:
        model = GraduationRecord
        fields = ['status', 'graduation_date', 'certificate_number', 'remarks']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select form-select-sm', 'required': 'required'}),
            'graduation_date': forms.DateInput(attrs={'class': 'form-control form-control-sm', 'type': 'date', 'required': 'required'}),
            'certificate_number': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'MOE Certificate No...'}),
            'remarks': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Honors, distinction, notes...'}),
        }


class PromotionFilterForm(forms.Form):
    """Filter form for promotion batches and candidate directories."""
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.all().order_by('-start_date'),
        required=False,
        empty_label="-- All Source Years --",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    grade = forms.ModelChoiceField(
        queryset=Grade.objects.filter(is_active=True).order_by('level'),
        required=False,
        empty_label="-- All Grades --",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    status = forms.ChoiceField(
        choices=[('', '-- All Statuses --')] + PromotionBatch.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
