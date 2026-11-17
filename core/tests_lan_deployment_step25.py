"""
core/tests_lan_deployment_step25.py
====================================
Step 25: LAN Deployment & Production Hardening Test Suite
Smart School Management and Academic Information System (SSMS)
Metti Secondary School - Majang Zone, Gambella, Ethiopia

Tests cover:
  A. Production Settings Configuration (`config.settings_production`)
  B. Static Asset Self-Containment (Zero external CDN links in core templates)
  C. LAN Deployment Scripts & Operational Helpers Verification
  D. WSGI Callable & Middleware Stack Integrity
  E. Logging Architecture & Directory Provisioning
"""

import ast
import os
from pathlib import Path
from django.test import TestCase


BASE_DIR = Path(__file__).resolve().parent.parent


class ProductionSettingsTest(TestCase):
    """Verifies that config/settings_production.py enforces production constraints."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Dynamically import production settings module without polluting global state
        import importlib
        import config.settings_production as prod_settings
        cls.prod = prod_settings

    def test_production_debug_is_false(self):
        """DEBUG must be explicitly False in production."""
        self.assertFalse(self.prod.DEBUG, "Production DEBUG must be set to False.")

    def test_whitenoise_in_middleware(self):
        """WhiteNoiseMiddleware must be enabled and positioned after SecurityMiddleware."""
        middleware = self.prod.MIDDLEWARE
        self.assertIn(
            'whitenoise.middleware.WhiteNoiseMiddleware',
            middleware,
            "WhiteNoiseMiddleware must be in production MIDDLEWARE.",
        )
        sec_idx = middleware.index('django.middleware.security.SecurityMiddleware')
        wn_idx = middleware.index('whitenoise.middleware.WhiteNoiseMiddleware')
        self.assertEqual(
            wn_idx, sec_idx + 1,
            "WhiteNoiseMiddleware must immediately follow SecurityMiddleware."
        )

    def test_audit_logging_in_middleware(self):
        """AuditLoggingMiddleware must be present in production MIDDLEWARE."""
        self.assertIn(
            'core.middleware.AuditLoggingMiddleware',
            self.prod.MIDDLEWARE,
            "AuditLoggingMiddleware must be present in production MIDDLEWARE."
        )

    def test_session_security_settings(self):
        """Cookie security settings must adhere to hardened LAN requirements."""
        self.assertTrue(self.prod.SESSION_COOKIE_HTTPONLY)
        self.assertTrue(self.prod.CSRF_COOKIE_HTTPONLY)
        self.assertIn(self.prod.SESSION_COOKIE_SAMESITE, ['Lax', 'Strict'])
        self.assertIn(self.prod.CSRF_COOKIE_SAMESITE, ['Lax', 'Strict'])
        self.assertEqual(self.prod.X_FRAME_OPTIONS, 'DENY')
        self.assertGreaterEqual(self.prod.SESSION_COOKIE_AGE, 3600)

    def test_file_upload_limits(self):
        """File upload limits must prevent memory exhaustion attacks on the LAN server."""
        self.assertLessEqual(self.prod.DATA_UPLOAD_MAX_MEMORY_SIZE, 50 * 1024 * 1024)
        self.assertLessEqual(self.prod.FILE_UPLOAD_MAX_MEMORY_SIZE, 50 * 1024 * 1024)

    def test_production_logging_configured(self):
        """Logging must define rotating file handlers for application and error logs."""
        logging_config = getattr(self.prod, 'LOGGING', {})
        handlers = logging_config.get('handlers', {})
        self.assertIn('file_app', handlers)
        self.assertIn('file_errors', handlers)
        self.assertIn('console', handlers)

    def test_email_backend_offline_safe(self):
        """Email backend must be offline-safe (file-based or dummy) so missing SMTP never crashes."""
        backend = getattr(self.prod, 'EMAIL_BACKEND', '')
        self.assertIn('filebased', backend.lower())

    def test_password_hashers_are_secure(self):
        """Production must use secure PBKDF2 hashers, never MD5."""
        hashers = getattr(self.prod, 'PASSWORD_HASHERS', [])
        for hasher in hashers:
            self.assertNotIn('MD5', hasher, "MD5 hasher must never be active in production.")


class StaticAssetsOfflineIntegrityTest(TestCase):
    """
    Validates that the system is 100% offline-first.
    No core templates or layouts may link to external CDNs or online font services.
    """

    FORBIDDEN_DOMAINS = [
        'cdn.jsdelivr.net',
        'cdnjs.cloudflare.com',
        'fonts.googleapis.com',
        'fonts.gstatic.com',
        'stackpath.bootstrapcdn.com',
        'code.jquery.com',
        'unpkg.com',
    ]

    def test_base_template_has_no_external_cdn_references(self):
        """templates/base.html must only reference local static assets."""
        base_html_path = BASE_DIR / 'templates' / 'base.html'
        self.assertTrue(base_html_path.exists(), "templates/base.html must exist.")

        content = base_html_path.read_text(encoding='utf-8')
        for domain in self.FORBIDDEN_DOMAINS:
            self.assertNotIn(
                domain, content,
                f"templates/base.html contains external CDN reference to {domain}. Must be bundled locally."
            )

    def test_local_vendor_assets_exist(self):
        """Crucial vendor assets (Bootstrap 5, Bootstrap Icons, Chart.js) must exist on disk."""
        static_dir = BASE_DIR / 'static'
        required_assets = [
            static_dir / 'vendor' / 'bootstrap' / 'css' / 'bootstrap.min.css',
            static_dir / 'vendor' / 'bootstrap' / 'js' / 'bootstrap.bundle.min.js',
            static_dir / 'vendor' / 'bootstrap-icons' / 'bootstrap-icons.css',
            static_dir / 'vendor' / 'chartjs' / 'chart.umd.min.js',
            static_dir / 'css' / 'styles.css',
        ]
        for asset in required_assets:
            self.assertTrue(asset.exists(), f"Required offline static asset missing: {asset}")


class DeploymentScriptsIntegrityTest(TestCase):
    """Verifies that all operational scripts exist, are non-empty, and are syntactically valid."""

    def test_serve_lan_script_exists_and_valid_python(self):
        """scripts/serve_lan.py must exist and parse as valid Python code."""
        script_path = BASE_DIR / 'scripts' / 'serve_lan.py'
        self.assertTrue(script_path.exists(), "scripts/serve_lan.py must exist.")
        code = script_path.read_text(encoding='utf-8')
        try:
            ast.parse(code)
        except SyntaxError as e:
            self.fail(f"scripts/serve_lan.py contains syntax errors: {e}")

    def test_startup_batch_script_exists(self):
        """START_SSMS_SERVER.bat must exist in project root."""
        bat_path = BASE_DIR / 'START_SSMS_SERVER.bat'
        self.assertTrue(bat_path.exists(), "START_SSMS_SERVER.bat must exist in project root.")
        content = bat_path.read_text(encoding='utf-8', errors='ignore')
        self.assertIn('serve_lan.py', content)

    def test_stop_batch_script_exists(self):
        """STOP_SSMS_SERVER.bat must exist in project root."""
        bat_path = BASE_DIR / 'STOP_SSMS_SERVER.bat'
        self.assertTrue(bat_path.exists(), "STOP_SSMS_SERVER.bat must exist in project root.")

    def test_firewall_batch_script_exists(self):
        """scripts/configure_firewall.bat must exist and reference port 8000."""
        bat_path = BASE_DIR / 'scripts' / 'configure_firewall.bat'
        self.assertTrue(bat_path.exists(), "scripts/configure_firewall.bat must exist.")
        content = bat_path.read_text(encoding='utf-8', errors='ignore')
        self.assertIn('8000', content)

    def test_backup_scheduler_script_exists(self):
        """scripts/schedule_daily_backup.bat must exist and register a scheduled task."""
        bat_path = BASE_DIR / 'scripts' / 'schedule_daily_backup.bat'
        self.assertTrue(bat_path.exists(), "scripts/schedule_daily_backup.bat must exist.")
        content = bat_path.read_text(encoding='utf-8', errors='ignore')
        self.assertIn('schtasks', content.lower())

    def test_wsgi_application_callable(self):
        """config.wsgi.application must be a callable WSGI application."""
        from config.wsgi import application
        self.assertTrue(callable(application), "config.wsgi.application must be callable.")
