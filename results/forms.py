"""
Forms for Results Management and Grading Configuration.
"""

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from academics.models import AcademicYear, Grade, Stream, Subject, ClassOffering
from teachers.models import TeacherAssignment
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


class ReportCardFilterForm(forms.Form):
    """Filter and search form for the Student Report Card Management Hub."""
    search = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': 'Search student name or admission no...',
        })
    )
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.all().order_by('-start_date'),
        required=False,
        empty_label='All Academic Years',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    examination = forms.ModelChoiceField(
        queryset=Examination.objects.all().order_by('-start_date'),
        required=False,
        empty_label='All Examinations',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    class_offering = forms.ModelChoiceField(
        queryset=ClassOffering.objects.all().select_related('grade', 'section', 'stream', 'academic_year').order_by('grade__level', 'section__name'),
        required=False,
        empty_label='All Classes / Sections',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )

    def __init__(self, *args, teacher=None, **kwargs):
        super().__init__(*args, **kwargs)
        if teacher:
            assigned_offering_ids = ClassOffering.objects.filter(
                teacher_assignments__teacher=teacher
            ).values_list('id', flat=True)
            self.fields['class_offering'].queryset = ClassOffering.objects.filter(
                id__in=assigned_offering_ids
            ).select_related('grade', 'section', 'stream', 'academic_year').order_by('grade__level', 'section__name')


class MarksImportUploadForm(forms.Form):
    """
    Step 21: Form for uploading Excel (.xlsx) and CSV (.csv) examination marks.
    Enforces strict file extension, size limit (5MB), and user assignment filtering.
    """
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.all().order_by('-start_date'),
        required=False,
        empty_label='Filter by Academic Year (Optional)',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'id_import_academic_year'})
    )
    examination = forms.ModelChoiceField(
        queryset=Examination.objects.all().order_by('-start_date'),
        required=False,
        empty_label='Select Examination...',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'id_import_examination'})
    )
    class_offering = forms.ModelChoiceField(
        queryset=ClassOffering.objects.all().select_related('grade', 'section', 'stream').order_by('grade__level', 'section__name'),
        required=False,
        empty_label='All Sections / Target Class (Optional)',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'id': 'id_import_class_offering'})
    )
    exam_subject = forms.ModelChoiceField(
        queryset=ExamSubject.objects.all().select_related('examination', 'subject', 'grade', 'stream').order_by('examination__name', 'grade__level', 'subject__name'),
        required=True,
        empty_label='Select Subject & Grade...',
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_import_exam_subject', 'required': 'required'})
    )
    file = forms.FileField(
        required=True,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'id': 'id_import_file',
            'accept': '.xlsx,.csv',
            'required': 'required'
        }),
        help_text="Upload .xlsx (Excel) or .csv file. Maximum allowed size is 5MB."
    )

    def __init__(self, *args, teacher=None, **kwargs):
        super().__init__(*args, **kwargs)
        if teacher:
            # Teacher is restricted strictly to their assigned subjects and grades
            assigned_pairs = TeacherAssignment.objects.filter(
                teacher=teacher
            ).values_list('subject_id', 'class_offering__grade_id')
            
            q_filter = Q()
            for subj_id, grade_id in assigned_pairs:
                q_filter |= Q(subject_id=subj_id, grade_id=grade_id)
            
            if q_filter:
                self.fields['exam_subject'].queryset = ExamSubject.objects.filter(
                    q_filter
                ).select_related('examination', 'subject', 'grade', 'stream').distinct()
            else:
                self.fields['exam_subject'].queryset = ExamSubject.objects.none()

            assigned_offering_ids = ClassOffering.objects.filter(
                teacher_assignments__teacher=teacher
            ).values_list('id', flat=True)
            self.fields['class_offering'].queryset = ClassOffering.objects.filter(
                id__in=assigned_offering_ids
            ).select_related('grade', 'section', 'stream').order_by('grade__level', 'section__name')

    def clean_file(self):
        uploaded_file = self.cleaned_data.get('file')
        if not uploaded_file:
            raise ValidationError("Please select a file to upload.")

        name = uploaded_file.name.lower()
        if not (name.endswith('.xlsx') or name.endswith('.csv')):
            raise ValidationError("Unsupported file extension. Only Excel (.xlsx) and CSV (.csv) files are supported.")

        if uploaded_file.size > 5 * 1024 * 1024:
            raise ValidationError(f"File size exceeds maximum 5MB limit ({uploaded_file.size / (1024*1024):.1f}MB detected).")

        # --- Magic-byte and structure validation ---
        # 1. Reject files with wrong binary signatures (prevents extension spoofing)
        header = uploaded_file.read(8)
        uploaded_file.seek(0)  # Reset stream for downstream processing

        XLSX_MAGIC = b'PK\x03\x04'       # ZIP-based: .xlsx, .docx, .zip all start with this
        CSV_PRINTABLE_CHARS = set(range(0x20, 0x7F)) | {0x09, 0x0A, 0x0D}  # tab, LF, CR

        if name.endswith('.xlsx'):
            if not header.startswith(XLSX_MAGIC):
                raise ValidationError(
                    "Invalid file content: the uploaded file does not match the expected Excel (.xlsx) format. "
                    "Ensure the file is a genuine Excel spreadsheet."
                )
            # 2. Real workbook parser validation: reject corrupted/truncated ZIP structures
            try:
                import openpyxl
                uploaded_file.seek(0)
                wb = openpyxl.load_workbook(uploaded_file, data_only=True, read_only=True)
                if not wb.sheetnames:
                    raise ValidationError("The Excel workbook contains no worksheets.")
                wb.close()
                uploaded_file.seek(0)
            except Exception as e:
                uploaded_file.seek(0)
                if isinstance(e, ValidationError):
                    raise
                raise ValidationError(
                    "Corrupted or malformed Excel (.xlsx) workbook: unable to parse structure. "
                    "Ensure the file is a valid Microsoft Excel document."
                )
        elif name.endswith('.csv'):
            # CSV must start with printable ASCII/UTF-8 (not binary executable header)
            if any(b not in CSV_PRINTABLE_CHARS and b < 0x80 for b in header[:4]):
                # Allow UTF-8 BOM (EF BB BF) which Excel sometimes adds to CSV exports
                if not header.startswith(b'\xef\xbb\xbf'):
                    raise ValidationError(
                        "Invalid file content: the CSV file appears to contain binary data. "
                        "Ensure the file is a plain-text comma-separated spreadsheet."
                    )
            # 2. Content validation: verify CSV contains readable rows
            try:
                import csv
                import io
                uploaded_file.seek(0)
                sample = uploaded_file.read(4096)
                uploaded_file.seek(0)
                try:
                    text_sample = sample.decode('utf-8-sig')
                except UnicodeDecodeError:
                    text_sample = sample.decode('latin-1')
                reader = csv.reader(io.StringIO(text_sample))
                rows = [r for r in reader if r]
                if not rows:
                    raise ValidationError("The uploaded CSV file is empty or does not contain readable data.")
            except Exception as e:
                uploaded_file.seek(0)
                if isinstance(e, ValidationError):
                    raise
                raise ValidationError("Invalid CSV structure: unable to parse comma-separated rows.")

        return uploaded_file




class MarksExportForm(forms.Form):
    """
    Step 21: Filterable Export Form for examination marks to Excel and CSV.
    """
    academic_year = forms.ModelChoiceField(
        queryset=AcademicYear.objects.all().order_by('-start_date'),
        required=False,
        empty_label='All Academic Years',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    examination = forms.ModelChoiceField(
        queryset=Examination.objects.all().order_by('-start_date'),
        required=False,
        empty_label='All Examinations',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    grade = forms.ModelChoiceField(
        queryset=Grade.objects.all().order_by('level'),
        required=False,
        empty_label='All Grades',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    class_offering = forms.ModelChoiceField(
        queryset=ClassOffering.objects.all().select_related('grade', 'section', 'stream').order_by('grade__level', 'section__name'),
        required=False,
        empty_label='All Sections / Classes',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    stream = forms.ModelChoiceField(
        queryset=Stream.objects.all().order_by('name'),
        required=False,
        empty_label='All Streams',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    subject = forms.ModelChoiceField(
        queryset=Subject.objects.all().order_by('name'),
        required=False,
        empty_label='All Subjects',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    file_format = forms.ChoiceField(
        choices=[
            ('xlsx', 'Excel Spreadsheet (.xlsx)'),
            ('csv', 'Comma Separated Values (.csv)')
        ],
        initial='xlsx',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )

    def __init__(self, *args, teacher=None, **kwargs):
        super().__init__(*args, **kwargs)
        if teacher:
            assigned_offering_ids = ClassOffering.objects.filter(
                teacher_assignments__teacher=teacher
            ).values_list('id', flat=True)
            self.fields['class_offering'].queryset = ClassOffering.objects.filter(
                id__in=assigned_offering_ids
            ).select_related('grade', 'section', 'stream').order_by('grade__level', 'section__name')

            assigned_subj_ids = TeacherAssignment.objects.filter(
                teacher=teacher
            ).values_list('subject_id', flat=True)
            self.fields['subject'].queryset = Subject.objects.filter(
                id__in=assigned_subj_ids
            ).order_by('name')
