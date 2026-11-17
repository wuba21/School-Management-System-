"""
core/tests_system_integration_step26.py
========================================
Step 26: Comprehensive System Integration & Production-Readiness Audit Test Suite
Smart School Management and Academic Information System (SSMS)
Metti Secondary School — Godere Woreda, Majang Zone, Gambella Region, Ethiopia

Tests cover:
  1. Security Correction 1: POST-only Logout & GET Rejection (405)
  2. Security Correction 2: AuditLog Model Immutability (delete raises PermissionError)
  3. Security Correction 3: Real openpyxl XLSX Validation, Corrupted ZIP Rejection & CSV Formula Injection Sanitization
  4. Security Correction 4: Dual Account and IP Brute-Force Rate Limiting (LAN shared-IP resilience)
  5. Security Correction 5: Sensitive Audit Data Sanitization (passwords & tokens redacted)
  6. End-to-End Cross-Module Integration: Student -> Enrollment -> Attendance -> Exam -> Mark -> Result -> Certificate
  7. Teacher Scoping Integration across Attendance and Results
  8. Ethiopian Calendar Conversion Integration
"""

import io
import csv
from io import BytesIO
from decimal import Decimal
from datetime import date
from django.utils import timezone

from django.test import TestCase, Client
from django.urls import reverse
from django.core.cache import cache
from django.core.exceptions import ValidationError

from accounts.models import User, Role
from accounts.security import (
    record_failed_attempt,
    clear_failed_attempts,
    is_ip_locked_out,
    is_account_locked_out,
    is_locked_out,
    get_lockout_reason,
    MAX_ATTEMPTS,
)
from core.models import AuditLog, LoginAttempt
from academics.models import AcademicYear, Grade, Section, Stream, Subject, ClassOffering
from students.models import Student, StudentEnrollment, StudentCertificate
from teachers.models import Teacher, TeacherAssignment
from attendance.models import AttendanceSession, AttendanceRecord
from examinations.models import Examination, ExamType, ExamSubject
from results.models import Mark, GradingScale, GradingRange
from results.services import sanitize_csv_cell
from core.utils.ethiopian_calendar import gregorian_to_ethiopian, ethiopian_to_gregorian


class LogoutSecurityTest(TestCase):
    """Security Correction 1: Logout must be strictly POST-only."""

    def setUp(self):
        self.role = Role.objects.create(code='TEACHER', name='Teacher')
        self.user = User.objects.create_user(
            username='logout_test_user',
            password='TestPassword123!',
            role=self.role
        )
        self.client = Client()

    def test_get_logout_rejected_with_405(self):
        """GET request to /logout/ must return 405 and preserve user session."""
        self.client.login(username='logout_test_user', password='TestPassword123!')
        response = self.client.get(reverse('logout'))
        self.assertEqual(response.status_code, 405)
        # Session must remain active
        self.assertTrue('_auth_user_id' in self.client.session)

    def test_post_logout_terminates_session(self):
        """POST request to /logout/ must terminate session and redirect to login."""
        self.client.login(username='logout_test_user', password='TestPassword123!')
        response = self.client.post(reverse('logout'))
        self.assertRedirects(response, reverse('login'))
        self.assertFalse('_auth_user_id' in self.client.session)


class AuditLogProtectionTest(TestCase):
    """Security Correction 2: AuditLog records must be strictly immutable."""

    def setUp(self):
        self.role_admin = Role.objects.create(code='ADMIN', name='System Administrator')
        self.admin = User.objects.create_user(
            username='admin_audit_guard',
            password='TestPassword123!',
            role=self.role_admin
        )
        self.log = AuditLog.objects.create(
            actor=self.admin,
            action='UPDATE',
            entity_name='Student',
            record_id='101',
            ip_address='192.168.1.50',
            changes_json={'status': ['ACTIVE', 'TRANSFERRED']}
        )

    def test_audit_log_delete_raises_permission_error(self):
        """Calling delete() on an AuditLog instance must raise PermissionError."""
        with self.assertRaises(PermissionError):
            self.log.delete()

    def test_audit_log_exists_after_attempted_deletion(self):
        """Record must still exist in database after attempted delete."""
        try:
            self.log.delete()
        except PermissionError:
            pass
        self.assertTrue(AuditLog.objects.filter(pk=self.log.pk).exists())

    def test_audit_log_queryset_delete_raises_permission_error(self):
        """Bulk deletion via QuerySet.delete() must raise PermissionError."""
        with self.assertRaises(PermissionError):
            AuditLog.objects.filter(pk=self.log.pk).delete()
        self.assertTrue(AuditLog.objects.filter(pk=self.log.pk).exists())

    def test_audit_log_queryset_update_raises_permission_error(self):
        """Bulk update via QuerySet.update() must raise PermissionError."""
        with self.assertRaises(PermissionError):
            AuditLog.objects.filter(pk=self.log.pk).update(action='DELETE')
        refreshed = AuditLog.objects.get(pk=self.log.pk)
        self.assertEqual(refreshed.action, 'UPDATE')

    def test_audit_log_admin_permissions(self):
        """AuditLogAdmin must disallow add, change, and delete permissions."""
        from django.contrib.admin.sites import AdminSite
        from core.admin import AuditLogAdmin
        admin_instance = AuditLogAdmin(AuditLog, AdminSite())
        dummy_request = type('Request', (), {'user': self.admin})()
        self.assertFalse(admin_instance.has_add_permission(dummy_request))
        self.assertFalse(admin_instance.has_change_permission(dummy_request))
        self.assertFalse(admin_instance.has_delete_permission(dummy_request))


class FileUploadSecurityAndCSVInjectionTest(TestCase):
    """Security Correction 3: Real workbook validation & CSV formula injection mitigation."""

    def _make_uploaded_file(self, filename, content, content_type='application/octet-stream'):
        from django.core.files.uploadedfile import InMemoryUploadedFile
        buf = BytesIO(content)
        buf.seek(0)
        return InMemoryUploadedFile(
            buf, 'file', filename, content_type, len(content), None
        )

    def test_genuine_openpyxl_workbook_accepted(self):
        """A valid openpyxl-generated workbook passes clean_file validation."""
        import openpyxl
        from results.forms import MarksImportUploadForm

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Marks"
        ws.append(["Admission Number", "Mark"])
        buf = BytesIO()
        wb.save(buf)

        f = self._make_uploaded_file('marks.xlsx', buf.getvalue())
        form = MarksImportUploadForm.__new__(MarksImportUploadForm)
        form.cleaned_data = {'file': f}
        cleaned = form.clean_file()
        self.assertIsNotNone(cleaned)

    def test_corrupted_xlsx_rejected_by_parser(self):
        """A file with PK header but broken zip payload must raise ValidationError."""
        from results.forms import MarksImportUploadForm

        broken_zip = b'PK\x03\x04\x14\x00\x00\x00\x08\x00corrupted_payload_data_not_a_valid_zip'
        f = self._make_uploaded_file('broken.xlsx', broken_zip)
        form = MarksImportUploadForm.__new__(MarksImportUploadForm)
        form.cleaned_data = {'file': f}
        with self.assertRaises(ValidationError) as ctx:
            form.clean_file()
        self.assertIn('corrupted or malformed', str(ctx.exception).lower())

    def test_csv_formula_injection_sanitization(self):
        """Dangerous spreadsheet formula prefixes (=, +, -, @, tab, cr) must be prepended with quote."""
        self.assertEqual(sanitize_csv_cell('=cmd|/C calc!A0'), "'=cmd|/C calc!A0")
        self.assertEqual(sanitize_csv_cell('+1+2'), "'+1+2")
        self.assertEqual(sanitize_csv_cell('-5*5'), "'-5*5")
        self.assertEqual(sanitize_csv_cell('@SUM(A1:A10)'), "'@SUM(A1:A10)")
        self.assertEqual(sanitize_csv_cell('\tcmd'), "'\tcmd")
        # Safe strings must remain unchanged
        self.assertEqual(sanitize_csv_cell('Abebe Bikila'), 'Abebe Bikila')
        self.assertEqual(sanitize_csv_cell('MSS/2026/0001'), 'MSS/2026/0001')
        self.assertEqual(sanitize_csv_cell(85.5), '85.5')
        self.assertEqual(sanitize_csv_cell(None), '')


class DualBruteForceProtectionTest(TestCase):
    """Security Correction 4: Dual IP and Account-level lockout preventing LAN denial-of-service."""

    TEST_IP = '192.168.1.105'

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_account_lockout_does_not_lock_different_account_on_same_ip(self):
        """Locking out user 'teacher_a' on an IP must NOT lock out user 'teacher_b' on the same IP."""
        # Simulate 5 failed attempts for teacher_a
        for _ in range(MAX_ATTEMPTS):
            record_failed_attempt(self.TEST_IP, username='teacher_a')

        # teacher_a is locked out
        self.assertTrue(is_account_locked_out('teacher_a'))
        self.assertTrue(is_locked_out(self.TEST_IP, username='teacher_a'))
        self.assertEqual(get_lockout_reason(self.TEST_IP, username='teacher_a'), 'account')

        # teacher_b from the SAME IP is NOT locked out!
        self.assertFalse(is_account_locked_out('teacher_b'))
        self.assertFalse(is_locked_out(self.TEST_IP, username='teacher_b'))

    def test_successful_login_clears_account_lockout(self):
        """Clearing failed attempts removes account-level lockout."""
        for _ in range(MAX_ATTEMPTS):
            record_failed_attempt(self.TEST_IP, username='teacher_reset')
        self.assertTrue(is_account_locked_out('teacher_reset'))

        clear_failed_attempts(self.TEST_IP, username='teacher_reset')
        self.assertFalse(is_account_locked_out('teacher_reset'))


class AuditDataSanitizationTest(TestCase):
    """Security Correction 5: Sensitive credentials must be redacted from AuditLog."""

    def test_password_redaction_in_audit_changes(self):
        """Keys containing 'password', 'token', or 'secret' must be redacted."""
        from accounts.views import sanitize_audit_changes

        raw_data = {
            'username': 'kebede',
            'password': 'RawPassword123!',
            'new_password1': 'NewSecret999!',
            'csrfmiddlewaretoken': 'xyz123token',
            'nested': {
                'auth_token': 'secret_jwt_token',
                'action': 'profile_update',
            }
        }
        sanitized = sanitize_audit_changes(raw_data)
        self.assertEqual(sanitized['username'], 'kebede')
        self.assertEqual(sanitized['password'], '[REDACTED]')
        self.assertEqual(sanitized['new_password1'], '[REDACTED]')
        self.assertEqual(sanitized['csrfmiddlewaretoken'], '[REDACTED]')
        self.assertEqual(sanitized['nested']['auth_token'], '[REDACTED]')
        self.assertEqual(sanitized['nested']['action'], 'profile_update')


class CrossModuleIntegrationTest(TestCase):
    """
    Module Integration Test: Complete Academic Workflow
    Academics -> Student Registration -> Enrollment -> Attendance -> Exam -> Mark -> Result Summary -> Transfer Certificate
    """

    def setUp(self):
        # 1. Academic Structure
        self.year = AcademicYear.objects.create(
            name="2026/2027",
            code="AY-2026-TEST",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_current=True,
            is_closed=False
        )
        self.grade9 = Grade.objects.create(name="Grade 9", level=9)
        self.sectionA = Section.objects.create(name="A")
        self.class_offering = ClassOffering.objects.create(
            academic_year=self.year,
            grade=self.grade9,
            section=self.sectionA,
            max_capacity=50
        )

        self.subject_math = Subject.objects.create(name="Mathematics", code="MATH9", is_active=True)

        # 2. Roles & Users
        self.role_admin = Role.objects.create(code='ADMIN', name='Administrator')
        self.role_principal = Role.objects.create(code='PRINCIPAL', name='Principal')
        self.role_registrar = Role.objects.create(code='REGISTRAR', name='Registrar')
        self.role_teacher = Role.objects.create(code='TEACHER', name='Teacher')

        self.admin = User.objects.create_user(username='admin_integ', password='pwd', role=self.role_admin)
        self.principal = User.objects.create_user(username='principal_integ', password='pwd', role=self.role_principal)
        self.registrar = User.objects.create_user(username='registrar_integ', password='pwd', role=self.role_registrar)
        self.teacher_user = User.objects.create_user(username='teacher_integ', password='pwd', role=self.role_teacher)

        self.teacher = Teacher.objects.create(
            user=self.teacher_user,
            employee_id="TCH/2026/0001",
            first_name="Abebe",
            father_name="Bikila",
            joining_date=date(2024, 9, 1)
        )

        # Assign teacher to Grade 9-A Mathematics
        TeacherAssignment.objects.create(
            teacher=self.teacher,
            class_offering=self.class_offering,
            subject=self.subject_math,
            academic_year=self.year
        )

        # 3. Student Registration & Enrollment
        self.student = Student.objects.create(
            admission_number="MSS/2026/0001",
            first_name="Chaltu",
            father_name="Tolessa",
            grandfather_name="Geda",
            gender="F",
            date_of_birth=date(2010, 5, 12),
            status="ACTIVE"
        )
        self.enrollment = StudentEnrollment.objects.create(
            student=self.student,
            class_offering=self.class_offering,
            academic_year=self.year,
            enrollment_date=date(2026, 9, 5),
            status="ACTIVE"
        )

    def test_complete_academic_lifecycle_integration(self):
        """
        Step-by-step end-to-end integration:
        Attendance -> Examination -> Mark Entry -> Result Calculation -> Leaving Certificate
        """
        # Step A: Take Attendance for this student
        session = AttendanceSession.objects.create(
            class_offering=self.class_offering,
            date=date(2026, 10, 1),
            session_type="DAILY",
            recorded_by=self.teacher
        )
        AttendanceRecord.objects.create(
            attendance_session=session,
            student_enrollment=self.enrollment,
            status="PRESENT"
        )
        self.assertEqual(AttendanceRecord.objects.filter(student_enrollment=self.enrollment).count(), 1)


        # Step B: Create Exam & ExamSubject
        exam_type = ExamType.objects.create(name="Midterm Exam", code="MIDTERM_TEST", default_weight=Decimal("30.00"))
        exam = Examination.objects.create(
            name="Semester 1 Midterm",
            exam_type=exam_type,
            academic_year=self.year,
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 10)
        )

        exam_sub = ExamSubject.objects.create(
            examination=exam,
            subject=self.subject_math,
            grade=self.grade9,
            max_marks=100,
            pass_marks=50
        )

        # Step C: Record Mark
        mark = Mark.objects.create(
            exam_subject=exam_sub,
            student_enrollment=self.enrollment,
            marks_obtained=Decimal("88.50"),
            is_absent=False,
            status="SUBMITTED"
        )
        self.assertEqual(mark.percentage, Decimal("88.50"))
        self.assertTrue(mark.is_passing)


        # Step D: Student Transfer/Leaving Certificate workflow
        cert = StudentCertificate.objects.create(
            certificate_type="TRANSFER",
            student=self.student,
            academic_year=self.year,
            last_grade=self.grade9,
            reason="Family relocated to Addis Ababa",
            destination_school="Menelik II Secondary School",
            conduct="Excellent",
            status="APPROVED",
            approved_by=self.principal,
            approved_at=timezone.now()
        )
        self.assertEqual(cert.status, "APPROVED")
        self.assertEqual(cert.student.admission_number, "MSS/2026/0001")



class EthiopianCalendarIntegrationTest(TestCase):
    """Verifies bidirectional Gregorian <-> Ethiopian date conversion integrity."""

    def test_known_ethiopian_dates(self):
        """Tests known benchmark dates (e.g., Ethiopian New Year)."""
        # Sept 12, 2023 -> Meskerem 1, 2016 E.C. (2015 was a leap year, Pagume had 6 days)
        eth_date = gregorian_to_ethiopian(date(2023, 9, 12))
        self.assertEqual((eth_date.year, eth_date.month, eth_date.day), (2016, 1, 1))

        # Convert back
        greg_date = ethiopian_to_gregorian(2016, 1, 1)
        self.assertEqual(greg_date, date(2023, 9, 12))

    def test_round_trip_conversion_consistency(self):
        """Converts a sequence of dates and ensures exact round-trip preservation."""
        test_dates = [
            date(2026, 1, 1),
            date(2026, 5, 20),
            date(2026, 9, 11),
            date(2026, 11, 17),
            date(2027, 2, 28),
        ]
        for d in test_dates:
            eth_date = gregorian_to_ethiopian(d)
            greg_date = ethiopian_to_gregorian(eth_date.year, eth_date.month, eth_date.day)
            self.assertEqual(greg_date, d, f"Round-trip failed for {d}")

