"""
Unit and Integration Tests for Step 21:
Examination Mark Excel/CSV Import and Export in SSMS.

Covers:
1. Excel (.xlsx) and CSV (.csv) template generation with active student rosters
2. Valid Excel import dry-run preview and atomic database commitment
3. Valid CSV import dry-run preview and confirmation
4. Validation: Invalid student admission numbers and cross-grade enrollments
5. Validation: Duplicate student rows in uploaded file
6. Validation: Non-numeric and negative score detection
7. Validation: Scores exceeding maximum allowed marks
8. Security & RBAC: Unauthorized teacher import prevention vs authorized teacher
9. Security & Lockout: Locked / verified exam subjects and published mark protection
10. Export functionality: Granular examination marks export to Excel and CSV
11. Transaction rollback: Atomic integrity when an unexpected error occurs
12. File validation: Files exceeding 5MB limit and unsupported extensions
13. Downloadable error report (.csv) generation for invalid rows
"""

import io
import csv
from decimal import Decimal
from datetime import date
import openpyxl

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError

from accounts.models import Role
from academics.models import AcademicYear, Grade, Section, Stream, Subject, ClassOffering
from students.models import Student, StudentEnrollment
from teachers.models import Teacher, TeacherAssignment
from examinations.models import Examination, ExamType, ExamSubject
from results.models import Mark, GradingScale, GradingRange
from results.services import MarksExportImportService, MarksService
from core.models import AuditLog

User = get_user_model()


class Step21MarksImportExportTests(TestCase):
    """Comprehensive test suite for examination marks Excel/CSV import and export."""

    @classmethod
    def setUpTestData(cls):
        # 1. User Roles
        cls.admin_role, _ = Role.objects.get_or_create(code='ADMIN', defaults={'name': 'System Administrator'})
        cls.principal_role, _ = Role.objects.get_or_create(code='PRINCIPAL', defaults={'name': 'School Principal'})
        cls.teacher_role, _ = Role.objects.get_or_create(code='TEACHER', defaults={'name': 'Teacher'})

        # 2. Staff Accounts
        cls.admin_user = User.objects.create_user(
            username='admin_step21', password='password123', role=cls.admin_role, is_staff=True, is_superuser=True
        )
        cls.teacher1_user = User.objects.create_user(
            username='teacher1_step21', password='password123', role=cls.teacher_role
        )
        cls.teacher2_user = User.objects.create_user(
            username='teacher2_step21', password='password123', role=cls.teacher_role
        )

        cls.teacher1 = Teacher.objects.create(
            user=cls.teacher1_user,
            first_name='Ayele',
            father_name='Mulu',
            employee_id='T-MET-01',
            joining_date=date(2021, 9, 1)
        )
        cls.teacher2 = Teacher.objects.create(
            user=cls.teacher2_user,
            first_name='Chala',
            father_name='Tolosa',
            employee_id='T-MET-02',
            joining_date=date(2022, 9, 1)
        )

        # 3. Academic Structure
        cls.academic_year = AcademicYear.objects.create(
            name='2026/2027',
            code='AY2026',
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_current=True
        )
        cls.grade10 = Grade.objects.create(name='Grade 10', level=10)
        cls.grade11 = Grade.objects.create(name='Grade 11', level=11)
        cls.sec_a = Section.objects.create(name='A')
        cls.sec_b = Section.objects.create(name='B')
        cls.stream_natural = Stream.objects.create(name='Natural Science', code='NAT')

        cls.offering_10a = ClassOffering.objects.create(
            academic_year=cls.academic_year,
            grade=cls.grade10,
            section=cls.sec_a,
            stream=None
        )
        cls.offering_11a = ClassOffering.objects.create(
            academic_year=cls.academic_year,
            grade=cls.grade11,
            section=cls.sec_a,
            stream=cls.stream_natural
        )

        # Subjects
        cls.subj_eng = Subject.objects.create(name='English Language', code='ENG10')
        cls.subj_math = Subject.objects.create(name='Mathematics', code='MAT10')
        cls.subj_phy = Subject.objects.create(name='Physics', code='PHY11')

        # Teacher Assignments
        # Teacher 1 teaches English in Grade 10-A
        TeacherAssignment.objects.create(
            teacher=cls.teacher1,
            class_offering=cls.offering_10a,
            subject=cls.subj_eng,
            academic_year=cls.academic_year
        )
        # Teacher 2 teaches Physics in Grade 11-A
        TeacherAssignment.objects.create(
            teacher=cls.teacher2,
            class_offering=cls.offering_11a,
            subject=cls.subj_phy,
            academic_year=cls.academic_year
        )

        # 4. Students & Enrollments
        cls.student1 = Student.objects.create(
            admission_number='MSS/2026/101',
            first_name='Abebe',
            father_name='Kebede',
            grandfather_name='Wolde',
            gender='M',
            date_of_birth=date(2010, 5, 12)
        )
        cls.enr1 = StudentEnrollment.objects.create(
            student=cls.student1,
            academic_year=cls.academic_year,
            class_offering=cls.offering_10a,
            status='ACTIVE'
        )

        cls.student2 = Student.objects.create(
            admission_number='MSS/2026/102',
            first_name='Derartu',
            father_name='Tulu',
            grandfather_name='Bekele',
            gender='F',
            date_of_birth=date(2010, 3, 20)
        )
        cls.enr2 = StudentEnrollment.objects.create(
            student=cls.student2,
            academic_year=cls.academic_year,
            class_offering=cls.offering_10a,
            status='ACTIVE'
        )

        # Student 3 in Grade 11
        cls.student3 = Student.objects.create(
            admission_number='MSS/2026/103',
            first_name='Fatuma',
            father_name='Roba',
            grandfather_name='Dibaba',
            gender='F',
            date_of_birth=date(2009, 8, 14)
        )
        cls.enr3 = StudentEnrollment.objects.create(
            student=cls.student3,
            academic_year=cls.academic_year,
            class_offering=cls.offering_11a,
            status='ACTIVE'
        )

        # 5. Examination & ExamSubjects
        cls.exam_type, _ = ExamType.objects.get_or_create(name='Final Exam', defaults={'code': 'FINAL'})
        cls.exam = Examination.objects.create(
            name='Semester 1 Final Examination',
            academic_year=cls.academic_year,
            exam_type=cls.exam_type,
            semester='SEM1',
            start_date=date(2026, 12, 10),
            end_date=date(2026, 12, 24),
            status='ACTIVE'
        )

        cls.es_eng = ExamSubject.objects.create(
            examination=cls.exam,
            grade=cls.grade10,
            subject=cls.subj_eng,
            max_marks=Decimal('100.00'),
            pass_marks=Decimal('50.00'),
            status='PENDING'
        )
        cls.es_phy = ExamSubject.objects.create(
            examination=cls.exam,
            grade=cls.grade11,
            subject=cls.subj_phy,
            max_marks=Decimal('100.00'),
            pass_marks=Decimal('50.00'),
            status='PENDING'
        )

    def _create_excel_file(self, rows):
        """Helper to create an in-memory openpyxl workbook file."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Marks Entry Template"
        for row in rows:
            ws.append(row)
        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)
        return SimpleUploadedFile("marks.xlsx", stream.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    def _create_csv_file(self, rows):
        """Helper to create an in-memory CSV file."""
        stream = io.StringIO()
        writer = csv.writer(stream)
        for row in rows:
            writer.writerow(row)
        csv_bytes = ('\ufeff' + stream.getvalue()).encode('utf-8')
        return SimpleUploadedFile("marks.csv", csv_bytes, content_type="text/csv")

    def test_template_download_excel_and_csv(self):
        """Verifies template generation returns valid Excel and CSV files with active student rosters."""
        self.client.force_login(self.admin_user)

        # 1. Excel Template Download
        url_xlsx = reverse('marks_template_download') + f"?exam_subject={self.es_eng.id}&format=xlsx"
        resp_xlsx = self.client.get(url_xlsx)
        self.assertEqual(resp_xlsx.status_code, 200)
        self.assertEqual(resp_xlsx['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertIn('Marks_Template_ENG10', resp_xlsx['Content-Disposition'])

        # Verify Excel content contains students
        wb = openpyxl.load_workbook(io.BytesIO(resp_xlsx.content))
        ws = wb.active
        content_text = " ".join(str(cell.value) for row in ws.iter_rows() for cell in row if cell.value)
        self.assertIn('MSS/2026/101', content_text)
        self.assertIn('Abebe Kebede Wolde', content_text)
        self.assertIn('MSS/2026/102', content_text)

        # 2. CSV Template Download
        url_csv = reverse('marks_template_download') + f"?exam_subject={self.es_eng.id}&format=csv"
        resp_csv = self.client.get(url_csv)
        self.assertEqual(resp_csv.status_code, 200)
        self.assertIn('text/csv', resp_csv['Content-Type'])
        self.assertIn('Marks_Template_ENG10', resp_csv['Content-Disposition'])
        csv_text = resp_csv.content.decode('utf-8-sig')
        self.assertIn('Admission Number,Student Full Name', csv_text)
        self.assertIn('MSS/2026/101,Abebe Kebede Wolde', csv_text)

    def test_valid_excel_import_and_commit(self):
        """Verifies dry-run preview and confirmation of valid Excel marks spreadsheet."""
        self.client.force_login(self.admin_user)

        # Prepare valid Excel file
        headers = ["Admission Number", "Student Full Name", "Grade", "Section", "Stream", "Subject Code", "Subject Name", "Examination", "Max Mark", "Mark Obtained", "Is Absent", "Remarks"]
        row1 = ["MSS/2026/101", "Abebe Kebede", "Grade 10", "A", "General", "ENG10", "English Language", self.exam.name, 100, 88.5, "NO", "Good job"]
        row2 = ["MSS/2026/102", "Derartu Tulu", "Grade 10", "A", "General", "ENG10", "English Language", self.exam.name, 100, "", "YES", "Absent with excuse"]
        excel_file = self._create_excel_file([headers, row1, row2])

        # Step 1: Upload to Import View (Preview)
        url_import = reverse('marks_import')
        post_data = {
            'exam_subject': self.es_eng.id,
            'file': excel_file
        }
        resp_preview = self.client.post(url_import, post_data)
        self.assertEqual(resp_preview.status_code, 200)
        self.assertContains(resp_preview, "Import Preview")
        self.assertContains(resp_preview, "Abebe Kebede")
        self.assertContains(resp_preview, "88.5")
        self.assertContains(resp_preview, "ABSENT")

        # Verify preview saved in session
        self.assertIn('marks_import_preview', self.client.session)
        preview_data = self.client.session['marks_import_preview']
        self.assertEqual(preview_data['valid_count'], 2)
        self.assertEqual(preview_data['invalid_count'], 0)

        # Step 2: Confirm Import
        url_confirm = reverse('marks_import_confirm')
        resp_confirm = self.client.post(url_confirm)
        self.assertEqual(resp_confirm.status_code, 302) # Redirect to marks entry

        # Verify Database Records Created
        mark1 = Mark.objects.get(student_enrollment=self.enr1, exam_subject=self.es_eng)
        self.assertEqual(mark1.marks_obtained, Decimal('88.50'))
        self.assertFalse(mark1.is_absent)
        self.assertEqual(mark1.remarks, "Good job")
        self.assertEqual(mark1.status, 'DRAFT')

        mark2 = Mark.objects.get(student_enrollment=self.enr2, exam_subject=self.es_eng)
        self.assertIsNone(mark2.marks_obtained)
        self.assertTrue(mark2.is_absent)

    def test_valid_csv_import_and_commit(self):
        """Verifies dry-run preview and confirmation of valid CSV marks spreadsheet."""
        self.client.force_login(self.admin_user)

        headers = ["Admission Number", "Student Full Name", "Grade", "Section", "Stream", "Subject Code", "Subject Name", "Examination", "Max Mark", "Mark Obtained", "Is Absent", "Remarks"]
        row1 = ["MSS/2026/101", "Abebe Kebede", "Grade 10", "A", "General", "ENG10", "English Language", self.exam.name, 100, 95.0, "NO", "Top score"]
        csv_file = self._create_csv_file([headers, row1])

        # Preview
        resp_preview = self.client.post(reverse('marks_import'), {'exam_subject': self.es_eng.id, 'file': csv_file})
        self.assertEqual(resp_preview.status_code, 200)
        self.assertContains(resp_preview, "95")

        # Confirm
        resp_confirm = self.client.post(reverse('marks_import_confirm'))
        self.assertEqual(resp_confirm.status_code, 302)

        mark1 = Mark.objects.get(student_enrollment=self.enr1, exam_subject=self.es_eng)
        self.assertEqual(mark1.marks_obtained, Decimal('95.00'))

    def test_invalid_student_id_detection(self):
        """Verifies non-existent student IDs and students enrolled in different grades are flagged."""
        self.client.force_login(self.admin_user)

        headers = ["Admission Number", "Student Full Name", "Mark Obtained", "Is Absent"]
        # MSS/NON_EXISTENT does not exist; MSS/2026/103 is Grade 11 student uploaded for Grade 10 exam subject
        row1 = ["MSS/NON_EXISTENT", "Ghost Student", 75.0, "NO"]
        row2 = ["MSS/2026/103", "Fatuma Roba", 80.0, "NO"]
        excel_file = self._create_excel_file([headers, row1, row2])

        resp = self.client.post(reverse('marks_import'), {'exam_subject': self.es_eng.id, 'file': excel_file})
        self.assertEqual(resp.status_code, 200)

        preview = self.client.session.get('marks_import_preview')
        self.assertEqual(preview['invalid_count'], 2)
        self.assertEqual(preview['valid_count'], 0)

        errors_text = " ".join(r['error_message'] for r in preview['invalid_rows'])
        self.assertIn("does not exist in SSMS student records", errors_text)
        self.assertIn("not enrolled in Grade 10", errors_text)

    def test_duplicate_student_records_detection(self):
        """Verifies duplicate student admission numbers in the uploaded file are caught and rejected."""
        self.client.force_login(self.admin_user)

        headers = ["Admission Number", "Student Full Name", "Mark Obtained", "Is Absent"]
        row1 = ["MSS/2026/101", "Abebe Kebede", 70.0, "NO"]
        row2 = ["MSS/2026/101", "Abebe Kebede Duplicate", 85.0, "NO"]
        excel_file = self._create_excel_file([headers, row1, row2])

        self.client.post(reverse('marks_import'), {'exam_subject': self.es_eng.id, 'file': excel_file})
        preview = self.client.session.get('marks_import_preview')

        self.assertEqual(preview['invalid_count'], 1)
        self.assertIn("Duplicate student admission number 'MSS/2026/101'", preview['invalid_rows'][0]['error_message'])

    def test_invalid_numeric_values_and_negative_scores(self):
        """Verifies non-numeric values and negative scores are rejected."""
        self.client.force_login(self.admin_user)

        headers = ["Admission Number", "Student Full Name", "Mark Obtained", "Is Absent"]
        row_alpha = ["MSS/2026/101", "Abebe Kebede", "NOT_A_NUMBER", "NO"]
        row_neg = ["MSS/2026/102", "Derartu Tulu", "-12.5", "NO"]
        excel_file = self._create_excel_file([headers, row_alpha, row_neg])

        self.client.post(reverse('marks_import'), {'exam_subject': self.es_eng.id, 'file': excel_file})
        preview = self.client.session.get('marks_import_preview')

        self.assertEqual(preview['invalid_count'], 2)
        errors_text = " ".join(r['error_message'] for r in preview['invalid_rows'])
        self.assertIn("Invalid numeric score 'NOT_A_NUMBER'", errors_text)
        self.assertIn("Negative mark (-12.5) is not allowed", errors_text)

    def test_marks_exceeding_maximum_score(self):
        """Verifies scores exceeding the subject's maximum allowed marks are flagged."""
        self.client.force_login(self.admin_user)

        headers = ["Admission Number", "Student Full Name", "Mark Obtained", "Is Absent"]
        # Max marks is 100.00
        row_over = ["MSS/2026/101", "Abebe Kebede", "105.00", "NO"]
        excel_file = self._create_excel_file([headers, row_over])

        self.client.post(reverse('marks_import'), {'exam_subject': self.es_eng.id, 'file': excel_file})
        preview = self.client.session.get('marks_import_preview')

        self.assertEqual(preview['invalid_count'], 1)
        self.assertIn("exceeds maximum allowed score of 100.00", preview['invalid_rows'][0]['error_message'])

    def test_unauthorized_teacher_import_prevented(self):
        """Verifies teachers can only import marks for their assigned classes and subjects."""
        # Teacher 1 is assigned to Grade 10 English, NOT Grade 11 Physics
        self.client.force_login(self.teacher1_user)

        headers = ["Admission Number", "Student Full Name", "Mark Obtained", "Is Absent"]
        row = ["MSS/2026/103", "Fatuma Roba", 80.0, "NO"]
        excel_file = self._create_excel_file([headers, row])

        # Teacher 1 attempting to import Physics for Grade 11 raises PermissionDenied (HTTP 403)
        resp = self.client.post(reverse('marks_import'), {'exam_subject': self.es_phy.id, 'file': excel_file})
        self.assertEqual(resp.status_code, 403)

        # But Teacher 1 CAN import English for Grade 10
        row_eng = ["MSS/2026/101", "Abebe Kebede", 85.0, "NO"]
        excel_eng = self._create_excel_file([headers, row_eng])
        resp_ok = self.client.post(reverse('marks_import'), {'exam_subject': self.es_eng.id, 'file': excel_eng})
        self.assertEqual(resp_ok.status_code, 200)
        self.assertContains(resp_ok, "Import Preview")

    def test_locked_examination_record_import_blocked(self):
        """Verifies verified or locked exam subjects reject file uploads."""
        self.client.force_login(self.admin_user)

        # Lock the exam subject by setting status to VERIFIED
        self.es_eng.status = 'VERIFIED'
        self.es_eng.save()

        headers = ["Admission Number", "Student Full Name", "Mark Obtained", "Is Absent"]
        row = ["MSS/2026/101", "Abebe Kebede", 90.0, "NO"]
        excel_file = self._create_excel_file([headers, row])

        resp = self.client.post(reverse('marks_import'), {'exam_subject': self.es_eng.id, 'file': excel_file})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "verified or locked. File import is disabled.")

        # Unlock exam subject
        self.es_eng.status = 'PENDING'
        self.es_eng.save()

    def test_cannot_overwrite_verified_mark(self):
        """Verifies existing individual marks that are verified or published cannot be overwritten via import."""
        self.client.force_login(self.admin_user)

        # Create an existing VERIFIED mark
        Mark.objects.create(
            student_enrollment=self.enr1,
            exam_subject=self.es_eng,
            marks_obtained=Decimal('90.00'),
            status='VERIFIED'
        )

        headers = ["Admission Number", "Student Full Name", "Mark Obtained", "Is Absent"]
        row = ["MSS/2026/101", "Abebe Kebede", 75.0, "NO"]
        excel_file = self._create_excel_file([headers, row])

        self.client.post(reverse('marks_import'), {'exam_subject': self.es_eng.id, 'file': excel_file})
        preview = self.client.session.get('marks_import_preview')
        self.assertEqual(preview['invalid_count'], 1)
        self.assertIn("already verified/published and locked against overwriting", preview['invalid_rows'][0]['error_message'])

    def test_excel_and_csv_export_functionality(self):
        """Verifies marks can be filtered and exported to Excel and CSV formats."""
        self.client.force_login(self.admin_user)

        # Record a test mark
        Mark.objects.create(
            student_enrollment=self.enr1,
            exam_subject=self.es_eng,
            marks_obtained=Decimal('92.00'),
            status='DRAFT',
            remarks='Solid performance'
        )

        # 1. Excel Export
        url_export_xlsx = reverse('marks_export') + f"?examination={self.exam.id}&subject={self.subj_eng.id}&file_format=xlsx&export=1"
        resp_xlsx = self.client.get(url_export_xlsx)
        self.assertEqual(resp_xlsx.status_code, 200)
        self.assertEqual(resp_xlsx['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertIn('Marks_Export_', resp_xlsx['Content-Disposition'])

        wb = openpyxl.load_workbook(io.BytesIO(resp_xlsx.content))
        ws = wb.active
        content_text = " ".join(str(cell.value) for row in ws.iter_rows() for cell in row if cell.value)
        self.assertIn('MSS/2026/101', content_text)
        self.assertIn('Abebe Kebede Wolde', content_text)
        self.assertIn('92', content_text)

        # 2. CSV Export
        url_export_csv = reverse('marks_export') + f"?examination={self.exam.id}&subject={self.subj_eng.id}&file_format=csv&export=1"
        resp_csv = self.client.get(url_export_csv)
        self.assertEqual(resp_csv.status_code, 200)
        self.assertIn('text/csv', resp_csv['Content-Type'])
        csv_text = resp_csv.content.decode('utf-8-sig')
        self.assertIn('MSS/2026/101', csv_text)
        self.assertIn('Abebe Kebede Wolde', csv_text)
        self.assertIn('92.00', csv_text)

    def test_download_error_report(self):
        """Verifies error report CSV export returns clean list of invalid rows with explanations."""
        self.client.force_login(self.admin_user)

        headers = ["Admission Number", "Student Full Name", "Mark Obtained", "Is Absent"]
        row_bad = ["MSS/INVALID_ADMISSION", "Nonexistent Student", "999.0", "NO"]
        excel_file = self._create_excel_file([headers, row_bad])

        # Step 1: Upload bad file
        self.client.post(reverse('marks_import'), {'exam_subject': self.es_eng.id, 'file': excel_file})

        # Step 2: Download error report
        resp_err = self.client.get(reverse('marks_import_errors'))
        self.assertEqual(resp_err.status_code, 200)
        self.assertIn('text/csv', resp_err['Content-Type'])
        self.assertIn('Marks_Import_Errors_', resp_err['Content-Disposition'])

        csv_text = resp_err.content.decode('utf-8-sig')
        self.assertIn("MSS/INVALID_ADMISSION", csv_text)
        self.assertIn("Row Number,Admission Number,Student Name,Submitted Mark,Error Description", csv_text)

    def test_large_file_size_validation(self):
        """Verifies files exceeding 5MB are rejected by the upload form."""
        self.client.force_login(self.admin_user)

        # Create a dummy 6MB file
        huge_content = b"A" * (6 * 1024 * 1024)
        huge_file = SimpleUploadedFile("huge.xlsx", huge_content, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        resp = self.client.post(reverse('marks_import'), {'exam_subject': self.es_eng.id, 'file': huge_file})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "File size exceeds maximum 5MB limit")

    def test_transaction_rollback_on_failure(self):
        """Verifies atomic rollback so that if an unexpected error occurs during commit, no rows remain partially saved."""
        valid_rows = [
            {
                'row_num': 2,
                'enrollment_id': self.enr1.id,
                'admission_number': self.student1.admission_number,
                'student_name': self.student1.full_name,
                'mark_obtained': '85.00',
                'is_absent': False,
                'remarks': 'Valid',
            }
        ]

        # Simulate lock condition triggering exception
        self.es_eng.status = 'PUBLISHED'
        self.es_eng.save()

        with self.assertRaises(ValidationError):
            MarksExportImportService.commit_import_marks(
                exam_subject_id=self.es_eng.id,
                valid_rows=valid_rows,
                user=self.admin_user
            )

        # Mark was not saved in DB
        self.assertFalse(Mark.objects.filter(student_enrollment=self.enr1, exam_subject=self.es_eng).exists())
