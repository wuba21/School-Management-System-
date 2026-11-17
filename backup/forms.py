from django import forms
from backup.models import BackupRecord


class BackupFilterForm(forms.Form):
    backup_type = forms.ChoiceField(
        choices=[('', 'All Types')] + BackupRecord.BACKUP_TYPE_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + BackupRecord.STATUS_CHOICES,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': 'Search filename or notes...'
        })
    )


class USBExportForm(forms.Form):
    backup_id = forms.IntegerField(widget=forms.HiddenInput())
    destination_path = forms.CharField(
        max_length=500,
        required=True,
        label="External USB Mount Directory",
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g., E:\\SchoolBackups (Windows) or /media/usb/backups (Linux)'
        }),
        help_text="Path to an attached, writable external USB flash drive or secondary storage."
    )
