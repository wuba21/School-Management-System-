"""
Forms for Results Management and Grading Configuration.
"""

from django import forms
from academics.models import AcademicYear, Grade, Subject, ClassOffering
from examinations.models import Examination, ExamSubject
from results.models import GradingScale, GradingRange, ResultApproval


class GradingScaleForm(forms.ModelForm):
    """Configuration form for master grading policy."""
    class Meta:
        model = GradingScale
        fields = ['name', 'code', 'description', 'is_default']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Ethiopian Secondary Standard Scale', 'required': 'required'}),
            'code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. ETH-SEC-2026', 'required': 'required'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Policy explanation...'}),
            'is_default': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class GradingRangeForm(forms.ModelForm):
    """Individual grade bracket form."""
    class Meta:
        model = GradingRange
        fields = ['grade_label', 'min_score', 'max_score', 'gpa_point', 'description', 'is_passing']
        widgets = {
            'grade_label': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'A', 'required': 'required'}),
            'min_score': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.5', 'min': '0', 'max': '100', 'required': 'required'}),
            'max_score': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.5', 'min': '0', 'max': '100', 'required': 'required'}),
            'gpa_point': forms.NumberInput(attrs={'class': 'form-control form-control-sm', 'step': '0.1', 'min': '0', 'max': '4'}),
            'description': forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'e.g. Excellent', 'required': 'required'}),
            'is_passing': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class MarksReviewForm(forms.Form):
    """Form used by Examination Officers and Registrars to approve or return marks."""
    decision = forms.ChoiceField(
        choices=ResultApproval.DECISION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'required': 'required'})
    )
    comments = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control form-control-sm', 'rows': 3, 'placeholder': 'Verification notes, discrepancy details, or return reasons...'})
    )
