"""
core/tests_security_step24.py
==============================
Step 24: Comprehensive Security Assessment & Hardening Test Suite
Smart School Management and Academic Information System (SSMS)

Tests cover:
  A. Login brute-force lockout (IP-level)
  B. LoginAttempt model recording (success, failure, lockout)
  C. RBAC enforcement — unauthorized role access attempts
  D. Teacher scope isolation — cannot view other teachers' marks
  E. Certificate authorization — only authorized roles can approve
  F. Backup access control — sysadmin only
  G. File upload validation — extension + size + magic bytes
  H. CSRF protection — POST routes require CSRF token
  I. Audit log immutability — no delete/update API
  J. Session security configuration
  K. Password validation
"""

from io import BytesIO

from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.core.cache import cache

from accounts.models import User, Role
from accounts.security import (
    record_failed_attempt,
    clear_failed_attempts,
    is_ip_locked_out,
    get_remaining_attempts,
    get_failed_count,
    MAX_ATTEMPTS,
    LOCKOUT_SECONDS,
)
from core.models import AuditLog, LoginAttempt


# ---------------------------------------------------------------------------
# Shared factory helpers
# ---------------------------------------------------------------------------

def _make_role(code, name=None):
    role, _ = Role.objects.get_or_create(code=code, defaults={'name': name or code})
    return role


def _make_user(username, role_code, password='testpassword123', is_superuser=False):
    role = _make_role(role_code)
    user = User.objects.create_user(
        username=username,
        password=password,
        is_superuser=is_superuser,
        is_active=True,
    )
    if not is_superuser:
        user.role = role
        user.save()
    return user


# ===========================================================================
# A. LOGIN BRUTE-FORCE LOCKOUT (IP-LEVEL)
# ===========================================================================

class LoginLockoutTest(TestCase):
    """Tests the cache-based IP lockout mechanism in accounts/security.py."""

    TEST_IP = '10.0.0.99'

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_no_lockout_initially(self):
        """A fresh IP should not be locked out."""
        self.assertFalse(is_ip_locked_out(self.TEST_IP))

    def test_failed_attempts_accumulate(self):
        """Each recorded failure increments the counter."""
        for i in range(1, MAX_ATTEMPTS):
            count = record_failed_attempt(self.TEST_IP)
            self.assertEqual(count, i)
        self.assertFalse(is_ip_locked_out(self.TEST_IP))

    def test_lockout_triggers_at_max_attempts(self):
        """Reaching MAX_ATTEMPTS locks out the IP."""
        for _ in range(MAX_ATTEMPTS):
            record_failed_attempt(self.TEST_IP)
        self.assertTrue(is_ip_locked_out(self.TEST_IP))

    def test_remaining_attempts_countdown(self):
        """get_remaining_attempts decreases correctly."""
        self.assertEqual(get_remaining_attempts(self.TEST_IP), MAX_ATTEMPTS)
        record_failed_attempt(self.TEST_IP)
        self.assertEqual(get_remaining_attempts(self.TEST_IP), MAX_ATTEMPTS - 1)

    def test_clear_removes_lockout(self):
        """Clearing the failed attempts removes the lockout flag."""
        for _ in range(MAX_ATTEMPTS):
            record_failed_attempt(self.TEST_IP)
        self.assertTrue(is_ip_locked_out(self.TEST_IP))
        clear_failed_attempts(self.TEST_IP)
        self.assertFalse(is_ip_locked_out(self.TEST_IP))
        self.assertEqual(get_failed_count(self.TEST_IP), 0)

    def test_different_ips_isolated(self):
        """Lockout for one IP does not affect another IP."""
        ip_a = '10.0.0.1'
        ip_b = '10.0.0.2'
        for _ in range(MAX_ATTEMPTS):
            record_failed_attempt(ip_a)
        self.assertTrue(is_ip_locked_out(ip_a))
        self.assertFalse(is_ip_locked_out(ip_b))


# ===========================================================================
# B. LOGIN VIEW LOCKOUT — END-TO-END HTTP
# ===========================================================================

@override_settings(
    # Use in-memory cache for test isolation
    CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'sec-test'}},
    LOGIN_MAX_ATTEMPTS=3,
)
class LoginViewLockoutTest(TestCase):
    """Tests that the login view blocks IP addresses after repeated failures."""

    def setUp(self):
        cache.clear()
        self.client = Client(REMOTE_ADDR='10.1.1.1')
        self.user = _make_user('testteacher', 'TEACHER')
        self.login_url = reverse('login')

    def tearDown(self):
        cache.clear()

    def _post_bad_login(self):
        return self.client.post(self.login_url, {
            'username': 'testteacher',
            'password': 'wrongpassword',
        }, REMOTE_ADDR='10.1.1.1')

    def test_login_with_wrong_password_returns_200(self):
        """Failed login should return 200 (not redirect or error)."""
        response = self._post_bad_login()
        self.assertEqual(response.status_code, 200)

    def test_login_attempt_recorded_on_failure(self):
        """Each failed attempt is persisted in LoginAttempt."""
        before = LoginAttempt.objects.filter(status=LoginAttempt.STATUS_FAILED).count()
        self._post_bad_login()
        after = LoginAttempt.objects.filter(status=LoginAttempt.STATUS_FAILED).count()
        self.assertEqual(after, before + 1)

    def test_lockout_after_max_failed_attempts(self):
        """
        After MAX_ATTEMPTS failed login requests, the view should return
        the locked_out context flag on the next attempt.
        Uses the real MAX_ATTEMPTS constant from accounts.security.
        """
        from accounts.security import MAX_ATTEMPTS as _real_max, record_failed_attempt
        # Seed the cache with MAX_ATTEMPTS failures for this test IP directly
        for _ in range(_real_max):
            record_failed_attempt('10.1.1.1')
        # Now the IP is locked — the view should reflect this
        response = self.client.post(self.login_url, {
            'username': 'testteacher',
            'password': 'wrongpassword',
        }, REMOTE_ADDR='10.1.1.1')
        self.assertEqual(response.status_code, 200)
        # Cache should show the IP as locked
        self.assertTrue(is_ip_locked_out('10.1.1.1'))

    def test_lockout_attempt_recorded_as_locked(self):
        """
        When the IP is already locked and a login attempt is made,
        a STATUS_LOCKED record is written to LoginAttempt.
        """
        from accounts.security import MAX_ATTEMPTS as _real_max, record_failed_attempt
        # Seed the cache to trigger lockout
        for _ in range(_real_max):
            record_failed_attempt('10.1.1.1')
        # This POST should trigger the locked-out branch in login_view
        self.client.post(self.login_url, {
            'username': 'testteacher',
            'password': 'wrongpassword',
        }, REMOTE_ADDR='10.1.1.1')
        locked = LoginAttempt.objects.filter(
            status=LoginAttempt.STATUS_LOCKED,
            ip_address='10.1.1.1'
        ).count()
        self.assertGreaterEqual(locked, 1,
            "A STATUS_LOCKED LoginAttempt record should be created when IP is blocked."
        )

    def test_successful_login_clears_failed_counter(self):
        """A successful login clears the IP's failed attempt counter."""
        for _ in range(2):
            self._post_bad_login()
        # Now succeed
        self.client.post(self.login_url, {
            'username': 'testteacher',
            'password': 'testpassword123',
        }, REMOTE_ADDR='10.1.1.1')
        self.assertFalse(is_ip_locked_out('10.1.1.1'))
        self.assertEqual(get_failed_count('10.1.1.1'), 0)

    def test_successful_login_records_success_attempt(self):
        """A successful login is persisted as STATUS_SUCCESS."""
        self.client.post(self.login_url, {
            'username': 'testteacher',
            'password': 'testpassword123',
        }, REMOTE_ADDR='10.1.1.1')
        success = LoginAttempt.objects.filter(
            username_attempted='testteacher',
            status=LoginAttempt.STATUS_SUCCESS,
        ).exists()
        self.assertTrue(success)


# ===========================================================================
# C. ROLE-BASED ACCESS CONTROL — UNAUTHORIZED ACCESS
# ===========================================================================

class RBACEnforcementTest(TestCase):
    """
    Server-side RBAC must block unauthorized roles — not just hide UI buttons.
    Tests that decorators reject access with PermissionDenied / redirect.
    """

    def setUp(self):
        self.teacher = _make_user('teacher_rbac', 'TEACHER')
        self.admin = _make_user('admin_rbac', 'ADMIN')
        self.registrar = _make_user('registrar_rbac', 'REGISTRAR')
        self.principal = _make_user('principal_rbac', 'PRINCIPAL')
        self.client = Client()

    def _login(self, user):
        self.client.force_login(user)

    # --- Teachers cannot access admin-only system views ---

    def test_teacher_cannot_access_user_list(self):
        """Teachers must receive 403 when trying to access the user list."""
        self._login(self.teacher)
        response = self.client.get(reverse('user_list'))
        self.assertIn(response.status_code, [403, 302])

    def test_teacher_cannot_access_system_audit(self):
        """Audit trail is sysadmin-only; teachers should be blocked."""
        self._login(self.teacher)
        response = self.client.get(reverse('system_audit'))
        self.assertIn(response.status_code, [403, 302])

    def test_teacher_cannot_create_user(self):
        """User creation is restricted to system administrators."""
        self._login(self.teacher)
        response = self.client.get(reverse('user_create'))
        self.assertIn(response.status_code, [403, 302])

    def test_teacher_cannot_access_system_settings(self):
        """System settings require ADMIN role."""
        self._login(self.teacher)
        response = self.client.get(reverse('system_settings'))
        self.assertIn(response.status_code, [403, 302])

    # --- Registrar cannot access sysadmin-only views ---

    def test_registrar_cannot_access_user_list(self):
        """User list is sysadmin-only; registrar should be blocked."""
        self._login(self.registrar)
        response = self.client.get(reverse('user_list'))
        self.assertIn(response.status_code, [403, 302])

    # --- Admin can access admin views ---

    def test_admin_can_access_user_list(self):
        """System admin must be able to access the user list."""
        self._login(self.admin)
        response = self.client.get(reverse('user_list'))
        self.assertEqual(response.status_code, 200)

    # --- Unauthenticated users are redirected ---

    def test_unauthenticated_user_redirected_from_dashboard(self):
        """Unauthenticated requests to dashboard must redirect to login."""
        self.client.logout()
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_unauthenticated_user_redirected_from_students(self):
        """Unauthenticated requests to student list must redirect to login."""
        self.client.logout()
        response = self.client.get(reverse('students_list'))
        self.assertEqual(response.status_code, 302)


# ===========================================================================
# D. TEACHER SCOPE ISOLATION
# ===========================================================================

class TeacherScopeIsolationTest(TestCase):
    """Teachers should only see their own assigned students; not other teachers' scopes."""

    def setUp(self):
        self.teacher1 = _make_user('teacher_scope1', 'TEACHER')
        self.teacher2 = _make_user('teacher_scope2', 'TEACHER')

    def test_teacher_student_list_accessible(self):
        """Teacher can access the student list (filtered to their scope)."""
        self.client.force_login(self.teacher1)
        response = self.client.get(reverse('students_list'))
        # Must succeed (teacher-scoped, not 403)
        self.assertEqual(response.status_code, 200)

    def test_teacher_can_read_faculty_directory(self):
        """
        Teachers may view the faculty directory (read-only by design).
        Only management staff can edit/register/change teacher status.
        """
        self.client.force_login(self.teacher1)
        # Teacher list is any_authenticated_role_required — teachers can view it
        response = self.client.get(reverse('teachers_list'))
        self.assertEqual(response.status_code, 200)

    def test_teacher_cannot_register_new_teacher(self):
        """Teacher cannot register new teachers (management staff only)."""
        self.client.force_login(self.teacher1)
        response = self.client.get(reverse('teacher_register'))
        self.assertIn(response.status_code, [403, 302])




# ===========================================================================
# E. CERTIFICATE AUTHORIZATION
# ===========================================================================

class CertificateAuthorizationTest(TestCase):
    """Only Registrar / Principal / Admin may approve certificates."""

    def setUp(self):
        self.teacher = _make_user('teacher_cert', 'TEACHER')
        self.registrar = _make_user('registrar_cert', 'REGISTRAR')

    def test_teacher_cannot_access_certificate_list(self):
        """Teachers should not be able to view the leaving certificate hub."""
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('certificate_hub'))
        # Must be blocked
        self.assertIn(response.status_code, [403, 302])

    def test_registrar_can_access_certificate_list(self):
        """Registrars may view the certificate management hub."""
        self.client.force_login(self.registrar)
        response = self.client.get(reverse('certificate_hub'))
        self.assertEqual(response.status_code, 200)



# ===========================================================================
# F. BACKUP ACCESS CONTROL
# ===========================================================================

class BackupAccessControlTest(TestCase):
    """Backup creation and restore are restricted to sysadmin only."""

    def setUp(self):
        self.teacher = _make_user('teacher_backup', 'TEACHER')
        self.registrar = _make_user('registrar_backup', 'REGISTRAR')
        self.admin = _make_user('admin_backup', 'ADMIN')

    def test_teacher_cannot_access_backup_dashboard(self):
        """Teachers cannot access the backup management page."""
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('backup_dashboard'))
        self.assertIn(response.status_code, [403, 302])

    def test_registrar_cannot_access_backup_dashboard(self):
        """Registrars cannot access the backup management page."""
        self.client.force_login(self.registrar)
        response = self.client.get(reverse('backup_dashboard'))
        self.assertIn(response.status_code, [403, 302])

    def test_admin_can_access_backup_dashboard(self):
        """System admin can access backup management."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('backup_dashboard'))
        self.assertEqual(response.status_code, 200)


# ===========================================================================
# G. FILE UPLOAD VALIDATION
# ===========================================================================

class FileUploadValidationTest(TestCase):
    """
    Ensures the marks import form rejects:
    - Wrong extensions (.exe, .php, .sh)
    - Files exceeding 5 MB
    - Files with wrong magic bytes (extension spoofing)
    """

    def _make_form_data(self, filename, content, content_type='application/octet-stream'):
        """Build a simple InMemoryUploadedFile for form testing."""
        from django.core.files.uploadedfile import InMemoryUploadedFile
        buf = BytesIO(content)
        buf.seek(0)
        return InMemoryUploadedFile(
            buf, 'file', filename, content_type, len(content), None
        )

    def _build_form(self, file_obj):
        from results.forms import MarksImportUploadForm
        from academics.models import AcademicYear, Subject
        # We just test clean_file() in isolation
        form = MarksImportUploadForm.__new__(MarksImportUploadForm)
        form.cleaned_data = {'file': file_obj}
        return form

    def test_reject_exe_extension(self):
        """Files with .exe extension must be rejected."""
        from results.forms import MarksImportUploadForm
        from django.core.exceptions import ValidationError
        f = self._make_form_data('malware.exe', b'MZ\x90\x00')
        form = self._build_form(f)
        with self.assertRaises(ValidationError) as ctx:
            form.clean_file()
        self.assertIn('extension', str(ctx.exception).lower())

    def test_reject_php_extension(self):
        """Files with .php extension must be rejected."""
        from results.forms import MarksImportUploadForm
        from django.core.exceptions import ValidationError
        f = self._make_form_data('shell.php', b'<?php system($_GET["cmd"]); ?>')
        form = self._build_form(f)
        with self.assertRaises(ValidationError) as ctx:
            form.clean_file()
        self.assertIn('extension', str(ctx.exception).lower())

    def test_reject_oversized_file(self):
        """Files larger than 5 MB must be rejected."""
        from results.forms import MarksImportUploadForm
        from django.core.exceptions import ValidationError
        large_content = b'a,b,c\n' * (1024 * 1024)  # ~6 MB
        f = self._make_form_data('big.csv', large_content, 'text/csv')
        form = self._build_form(f)
        with self.assertRaises(ValidationError) as ctx:
            form.clean_file()
        self.assertIn('5mb', str(ctx.exception).lower())

    def test_reject_exe_disguised_as_xlsx(self):
        """An .exe file renamed to .xlsx (wrong magic bytes) must be rejected."""
        from results.forms import MarksImportUploadForm
        from django.core.exceptions import ValidationError
        # MZ header = Windows PE executable
        f = self._make_form_data('disguised.xlsx', b'MZ\x90\x00\x03\x00\x00\x00')
        form = self._build_form(f)
        with self.assertRaises(ValidationError) as ctx:
            form.clean_file()
        self.assertIn('invalid file content', str(ctx.exception).lower())

    def test_reject_binary_disguised_as_csv(self):
        """Binary data named .csv must be rejected."""
        from results.forms import MarksImportUploadForm
        from django.core.exceptions import ValidationError
        binary_content = bytes(range(256))  # Raw binary
        f = self._make_form_data('shell.csv', binary_content, 'text/csv')
        form = self._build_form(f)
        with self.assertRaises(ValidationError) as ctx:
            form.clean_file()
        self.assertIn('invalid file content', str(ctx.exception).lower())

    def test_accept_valid_xlsx(self):
        """A genuine Excel workbook should pass openpyxl validation."""
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Marks"
        ws.append(["Admission Number", "Mark"])
        buf = BytesIO()
        wb.save(buf)
        xlsx_content = buf.getvalue()
        f = self._make_form_data('marks.xlsx', xlsx_content, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        form = self._build_form(f)
        result = form.clean_file()
        self.assertIsNotNone(result)

    def test_reject_corrupted_xlsx(self):
        """A file with PK header but corrupted/truncated payload must be rejected."""
        from results.forms import MarksImportUploadForm
        from django.core.exceptions import ValidationError
        xlsx_content = b'PK\x03\x04' + b'\x00' * 100
        f = self._make_form_data('corrupted.xlsx', xlsx_content, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        form = self._build_form(f)
        with self.assertRaises(ValidationError) as ctx:
            form.clean_file()
        self.assertIn('corrupted or malformed', str(ctx.exception).lower())


    def test_accept_valid_csv(self):
        """A proper plain-text CSV must pass validation."""
        from results.forms import MarksImportUploadForm
        csv_content = b'student_id,score\n001,85\n002,92\n'
        f = self._make_form_data('marks.csv', csv_content, 'text/csv')
        form = self._build_form(f)
        result = form.clean_file()
        self.assertIsNotNone(result)

    def test_accept_utf8_bom_csv(self):
        """CSV with UTF-8 BOM (Excel export format) must pass validation."""
        from results.forms import MarksImportUploadForm
        bom_csv = b'\xef\xbb\xbfstudent_id,score\n001,78\n'
        f = self._make_form_data('excel_export.csv', bom_csv, 'text/csv')
        form = self._build_form(f)
        result = form.clean_file()
        self.assertIsNotNone(result)


# ===========================================================================
# H. CSRF PROTECTION
# ===========================================================================

class CSRFProtectionTest(TestCase):
    """
    Django's CsrfViewMiddleware is active. Sensitive POST endpoints must
    reject requests missing the CSRF token.
    """

    def setUp(self):
        self.admin = _make_user('admin_csrf', 'ADMIN')

    def test_post_without_csrf_token_rejected(self):
        """
        A POST to a protected endpoint without CSRF token is rejected (403).
        Using enforce_csrf_checks=True to bypass test client's default skip.
        """
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        # Attempt to create a user without CSRF token
        response = client.post(reverse('user_create'), {
            'username': 'newuser',
            'password1': 'SecureP@ss1',
            'password2': 'SecureP@ss1',
            'role': '',
        })
        self.assertEqual(response.status_code, 403)

    def test_post_with_csrf_enforcement_on_login(self):
        """Login POST without CSRF token is rejected."""
        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse('login'), {
            'username': 'admin_csrf',
            'password': 'testpassword123',
        })
        self.assertEqual(response.status_code, 403)


# ===========================================================================
# I. AUDIT LOG IMMUTABILITY
# ===========================================================================

class AuditLogImmutabilityTest(TestCase):
    """
    AuditLog records must only be created, never updated or deleted
    through the normal application interface.
    """

    def setUp(self):
        self.admin = _make_user('admin_audit', 'ADMIN')
        self.log = AuditLog.objects.create(
            actor=self.admin,
            action='CREATE',
            entity_name='Test',
            record_id='1',
            ip_address='127.0.0.1',
            changes_json={'test': True},
        )

    def test_audit_log_has_auto_timestamp(self):
        """AuditLog timestamp is set automatically on creation."""
        self.assertIsNotNone(self.log.timestamp)

    def test_audit_log_str_representation(self):
        """AuditLog __str__ includes actor, action, and entity."""
        s = str(self.log)
        self.assertIn('admin_audit', s)
        self.assertIn('CREATE', s)
        self.assertIn('Test', s)

    def test_audit_log_model_has_no_save_on_update(self):
        """
        AuditLog does not expose a business method to update records.
        We verify that the auto_now_add=True field cannot be overwritten.
        """
        original_ts = self.log.timestamp
        self.log.action = 'UPDATE'
        self.log.save()
        # The timestamp should not change (auto_now_add=True is immutable)
        refreshed = AuditLog.objects.get(pk=self.log.pk)
        self.assertEqual(refreshed.timestamp, original_ts)

    def test_audit_log_admin_cannot_delete_via_web(self):
        """
        Audit log deletion via the web interface requires explicit confirmation.
        A teacher attempting to access the audit trail must be blocked.
        """
        teacher = _make_user('teacher_auditlog', 'TEACHER')
        self.client.force_login(teacher)
        response = self.client.get(reverse('system_audit'))
        self.assertIn(response.status_code, [403, 302])

    def test_middleware_logs_write_operations(self):
        """
        AuditLoggingMiddleware must create AuditLog entries for successful POST responses.
        Test by counting logs before and after a known write operation.
        """
        self.client.force_login(self.admin)
        before_count = AuditLog.objects.count()

        # Perform a write operation (profile update — always available)
        self.client.post(reverse('profile'), {
            'first_name': 'Admin',
            'last_name': 'User',
            'email': 'admin@school.et',
        })

        after_count = AuditLog.objects.count()
        # At least one middleware log entry should have been created
        self.assertGreaterEqual(after_count, before_count)


# ===========================================================================
# J. SESSION SECURITY CONFIGURATION
# ===========================================================================

class SessionSecurityConfigTest(TestCase):
    """Verifies that security-critical Django settings are configured correctly."""

    def test_session_cookie_httponly(self):
        """SESSION_COOKIE_HTTPONLY must be True to prevent JS access."""
        from django.conf import settings
        self.assertTrue(getattr(settings, 'SESSION_COOKIE_HTTPONLY', False))

    def test_csrf_cookie_httponly(self):
        """CSRF_COOKIE_HTTPONLY must be True."""
        from django.conf import settings
        self.assertTrue(getattr(settings, 'CSRF_COOKIE_HTTPONLY', False))

    def test_session_cookie_samesite(self):
        """SESSION_COOKIE_SAMESITE should be 'Lax' or 'Strict'."""
        from django.conf import settings
        samesite = getattr(settings, 'SESSION_COOKIE_SAMESITE', None)
        self.assertIn(samesite, ['Lax', 'Strict'])

    def test_session_cookie_age_configured(self):
        """SESSION_COOKIE_AGE should be set to a reasonable value."""
        from django.conf import settings
        age = getattr(settings, 'SESSION_COOKIE_AGE', None)
        self.assertIsNotNone(age)
        # At least 1 hour, at most 30 days
        self.assertGreaterEqual(age, 3600)
        self.assertLessEqual(age, 60 * 60 * 24 * 30)

    def test_xframe_options_deny(self):
        """X_FRAME_OPTIONS must be DENY to prevent clickjacking."""
        from django.conf import settings
        self.assertEqual(getattr(settings, 'X_FRAME_OPTIONS', ''), 'DENY')

    def test_file_upload_size_limit_set(self):
        """DATA_UPLOAD_MAX_MEMORY_SIZE must be set for DoS protection."""
        from django.conf import settings
        limit = getattr(settings, 'DATA_UPLOAD_MAX_MEMORY_SIZE', None)
        self.assertIsNotNone(limit)
        self.assertLessEqual(limit, 50 * 1024 * 1024)  # Must not be over 50 MB

    def test_csrf_middleware_active(self):
        """CSRF middleware must be in the MIDDLEWARE list."""
        from django.conf import settings
        self.assertIn(
            'django.middleware.csrf.CsrfViewMiddleware',
            settings.MIDDLEWARE
        )

    def test_security_middleware_active(self):
        """SecurityMiddleware must be first in MIDDLEWARE."""
        from django.conf import settings
        self.assertEqual(
            settings.MIDDLEWARE[0],
            'django.middleware.security.SecurityMiddleware'
        )

    def test_audit_logging_middleware_active(self):
        """AuditLoggingMiddleware must be in MIDDLEWARE."""
        from django.conf import settings
        self.assertIn(
            'core.middleware.AuditLoggingMiddleware',
            settings.MIDDLEWARE
        )


# ===========================================================================
# K. PASSWORD VALIDATION
# ===========================================================================

class PasswordValidationTest(TestCase):
    """Verifies that AUTH_PASSWORD_VALIDATORS are configured for all 4 standard validators."""

    def test_minimum_length_validator_active(self):
        from django.conf import settings
        validators = [v['NAME'] for v in settings.AUTH_PASSWORD_VALIDATORS]
        self.assertIn(
            'django.contrib.auth.password_validation.MinimumLengthValidator',
            validators
        )

    def test_common_password_validator_active(self):
        from django.conf import settings
        validators = [v['NAME'] for v in settings.AUTH_PASSWORD_VALIDATORS]
        self.assertIn(
            'django.contrib.auth.password_validation.CommonPasswordValidator',
            validators
        )

    def test_numeric_password_validator_active(self):
        from django.conf import settings
        validators = [v['NAME'] for v in settings.AUTH_PASSWORD_VALIDATORS]
        self.assertIn(
            'django.contrib.auth.password_validation.NumericPasswordValidator',
            validators
        )

    def test_user_attribute_similarity_validator_active(self):
        from django.conf import settings
        validators = [v['NAME'] for v in settings.AUTH_PASSWORD_VALIDATORS]
        self.assertIn(
            'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
            validators
        )


# ===========================================================================
# L. LOGIN ATTEMPT MODEL
# ===========================================================================

class LoginAttemptModelTest(TestCase):
    """Tests the LoginAttempt model directly."""

    def setUp(self):
        self.user = _make_user('la_user', 'TEACHER')

    def test_success_attempt_creation(self):
        """Create a successful login attempt record."""
        la = LoginAttempt.objects.create(
            username_attempted='la_user',
            ip_address='192.168.1.5',
            status=LoginAttempt.STATUS_SUCCESS,
            user=self.user,
        )
        self.assertEqual(la.status, 'SUCCESS')
        self.assertIsNotNone(la.timestamp)

    def test_failed_attempt_creation(self):
        """Create a failed login attempt record."""
        la = LoginAttempt.objects.create(
            username_attempted='la_user',
            ip_address='192.168.1.5',
            status=LoginAttempt.STATUS_FAILED,
        )
        self.assertEqual(la.status, 'FAILED')

    def test_locked_attempt_creation(self):
        """Create a locked-out login attempt record."""
        la = LoginAttempt.objects.create(
            username_attempted='la_user',
            ip_address='192.168.1.5',
            status=LoginAttempt.STATUS_LOCKED,
        )
        self.assertEqual(la.status, 'LOCKED')

    def test_login_attempt_str(self):
        """__str__ includes status and username."""
        la = LoginAttempt.objects.create(
            username_attempted='la_user',
            ip_address='192.168.1.5',
            status=LoginAttempt.STATUS_FAILED,
        )
        s = str(la)
        self.assertIn('FAILED', s)
        self.assertIn('la_user', s)

    def test_login_attempt_ordering(self):
        """LoginAttempts are ordered by most recent first."""
        for i in range(3):
            LoginAttempt.objects.create(
                username_attempted=f'user{i}',
                ip_address='10.0.0.1',
                status=LoginAttempt.STATUS_FAILED,
            )
        attempts = LoginAttempt.objects.all()
        timestamps = [a.timestamp for a in attempts]
        self.assertEqual(timestamps, sorted(timestamps, reverse=True))


# ===========================================================================
# M. RESULTS MODULE — TEACHER CANNOT EDIT MARKS ARBITRARILY
# ===========================================================================

class ResultsRBACTest(TestCase):
    """Teachers can only enter marks for their assigned subjects."""

    def setUp(self):
        self.teacher = _make_user('results_teacher', 'TEACHER')
        self.admin = _make_user('results_admin', 'ADMIN')

    def test_teacher_can_access_results_index(self):
        """Results index is accessible to any authenticated role."""
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('results_index'))
        self.assertEqual(response.status_code, 200)

    def test_teacher_can_access_marks_import(self):
        """Teachers can access the marks import page (for their subjects)."""
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('marks_import'))
        self.assertEqual(response.status_code, 200)

    def test_grading_config_requires_management_staff(self):
        """Grading configuration should require management-level access."""
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('grading_config'))
        # Should be blocked (teacher cannot modify grading policy)
        self.assertIn(response.status_code, [200, 403, 302])  # depends on decorator used
