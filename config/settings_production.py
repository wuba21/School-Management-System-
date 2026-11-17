"""
config/settings_production.py
==============================
Step 25: Production-grade settings for LAN deployment.

This module EXTENDS base settings.py for the production LAN environment.
It is loaded by setting:
  DJANGO_SETTINGS_MODULE=config.settings_production

USAGE:
  - Used by: scripts/serve_lan.py (Waitress WSGI server)
  - DO NOT use DEBUG=True in this file.
  - All sensitive values are read from the .env file.

Metti Secondary School LAN Deployment
Godere Woreda, Majang Zone, Gambella Region, Ethiopia
"""

# Import all base settings first
from config.settings import *  # noqa: F401, F403
import os

# ---------------------------------------------------------------------------
# PRODUCTION OVERRIDES
# ---------------------------------------------------------------------------

# SECURITY WARNING: Never run production with DEBUG=True
DEBUG = False

# LAN Server IP address(es) — add the school server's static IP
# Example: '192.168.1.100' for a typical school LAN
_lan_ip = os.getenv('LAN_SERVER_IP', '192.168.1.100')
_custom_hosts = [h.strip() for h in os.getenv('ALLOWED_HOSTS', '').split(',') if h.strip()]
ALLOWED_HOSTS = list(set([
    '127.0.0.1',
    'localhost',
    '0.0.0.0',
    'ssms.local',
    'metti.school.local',
    _lan_ip,
    # Allow all IPs on the local network if specified, or specific custom hosts
    *_custom_hosts
]))

# Production secret key — MUST be set in .env file for production
SECRET_KEY = os.getenv('SECRET_KEY')
if not SECRET_KEY:
    raise ValueError(
        "SSMS PRODUCTION ERROR: SECRET_KEY is not set in the .env file. "
        "Generate one with: python -c \"from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())\""
    )

# ---------------------------------------------------------------------------
# STATIC FILES — WhiteNoise serves static files from STATIC_ROOT
# This eliminates the need for a separate nginx/Apache in a LAN environment
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',       # WhiteNoise: must be second
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.AuditLoggingMiddleware',
]

# WhiteNoise configuration — compresses and caches static files
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# ---------------------------------------------------------------------------
# SESSION SECURITY — Production-grade settings
# ---------------------------------------------------------------------------
SESSION_COOKIE_SECURE = False   # Leave False for HTTP-only LAN (no HTTPS)
CSRF_COOKIE_SECURE = False      # Same: HTTP LAN does not use TLS
SESSION_COOKIE_AGE = 60 * 60 * 8   # 8 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = 'Lax'

# ---------------------------------------------------------------------------
# LOGGING — Production logging to rotating files
# ---------------------------------------------------------------------------
LOG_DIR = BASE_DIR / 'logs'  # noqa: F405
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {asctime} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'file_app': {
            'level': 'INFO',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'ssms_application.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'file_errors': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': str(LOG_DIR / 'ssms_errors.log'),
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
        },
        'console': {
            'level': 'WARNING',
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
        },
    },
    'root': {
        'handlers': ['file_app', 'file_errors', 'console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['file_app', 'file_errors'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['file_errors'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
}

# ---------------------------------------------------------------------------
# EMAIL — Offline LAN: disabled (no SMTP server available)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = 'django.core.mail.backends.filebased.EmailBackend'
EMAIL_FILE_PATH = str(LOG_DIR / 'email_outbox')

# ---------------------------------------------------------------------------
# PRODUCTION PASSWORD HASHERS — Use PBKDF2 (not test-mode MD5)
# ---------------------------------------------------------------------------
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.PBKDF2PasswordHasher',
    'django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher',
]
