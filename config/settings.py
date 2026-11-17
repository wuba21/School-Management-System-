"""
Django settings for Smart School Management and Academic Information System (SSMS).
Project configuration module: config.settings
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Load environment variables from .env file
load_dotenv(BASE_DIR / '.env')

# Quick-start development settings - unsuitable for production
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv(
    'SECRET_KEY',
    'django-insecure-6^*!tk4plyau6o6s&l!u_%3o(yd!2ye7rl3y9-iv%q$))=x2o^'
)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv('DEBUG', 'True').lower() in ('true', '1', 'yes')

ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv('ALLOWED_HOSTS', '127.0.0.1,localhost,0.0.0.0').split(',')
    if host.strip()
]
# Ensure test runners and local development are always permitted in debug mode
if DEBUG:
    ALLOWED_HOSTS.extend(['testserver', 'localhost', '127.0.0.1'])
    ALLOWED_HOSTS = list(set(ALLOWED_HOSTS))


# Application definition
INSTALLED_APPS = [
    # Built-in Django Apps
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # School Management Core Applications
    'core.apps.CoreConfig',
    'accounts.apps.AccountsConfig',
    'students.apps.StudentsConfig',
    'teachers.apps.TeachersConfig',
    'academics.apps.AcademicsConfig',
    'attendance.apps.AttendanceConfig',
    'examinations.apps.ExaminationsConfig',
    'results.apps.ResultsConfig',
    'promotion.apps.PromotionConfig',
    'timetable.apps.TimetableConfig',
    'reports.apps.ReportsConfig',
    'dashboard.apps.DashboardConfig',
    'ai_assistant.apps.AiAssistantConfig',
    'backup.apps.BackupConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Static files in production (Render/WSGI)
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'core.middleware.AuditLoggingMiddleware',  # Step 24: Automatic write-operation audit logging
]

# ---------------------------------------------------------------------------
# Cache — LocMemCache (in-process, no external service required for LAN)
# Used by the login brute-force protection module (Step 24).
# ---------------------------------------------------------------------------
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'ssms-security-cache',
    }
}

# Login brute-force protection thresholds
LOGIN_MAX_ATTEMPTS = int(os.getenv('LOGIN_MAX_ATTEMPTS', '5'))      # failures before lockout
LOGIN_LOCKOUT_DURATION = int(os.getenv('LOGIN_LOCKOUT_DURATION', '900'))  # seconds (15 min)


ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.template.context_processors.i18n',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Custom Authentication User Model
AUTH_USER_MODEL = 'accounts.User'

# Database Configuration
# Uses environment variables to prevent hard-coding credentials.
# Supports both PostgreSQL (production/LAN standard) and SQLite (initial local fallback).
DB_ENGINE = os.getenv('DB_ENGINE', 'postgresql').lower()

if DB_ENGINE == 'postgresql':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.getenv('DB_NAME', 'smart_school_db'),
            'USER': os.getenv('DB_USER', 'postgres'),
            'PASSWORD': os.getenv('DB_PASSWORD', ''),
            'HOST': os.getenv('DB_HOST', '127.0.0.1'),
            'PORT': os.getenv('DB_PORT', '5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
            'OPTIONS': {
                # Increase SQLite timeout to 30 seconds to prevent "database is locked" errors under multi-user concurrency
                'timeout': 30,
            },
        }
    }


# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization & Regionalization for Ethiopia
LANGUAGE_CODE = 'en'

LANGUAGES = [
    ('en', 'English'),
    ('am', 'አማርኛ'),
]

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

# Time zone configured for Majang Zone, Gambella Region, Ethiopia
TIME_ZONE = 'Africa/Addis_Ababa'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# Configured for self-contained, offline-first LAN deployment
STATIC_URL = '/static/'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]
STATIC_ROOT = BASE_DIR / 'staticfiles'

# WhiteNoise: serve compressed, cached static files in production
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Media files (User uploads, student photos, generated PDF report cards)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# ---------------------------------------------------------------------------
# System Backup & Disaster Recovery (Step 17)
# ---------------------------------------------------------------------------
# Backup directory is located outside publicly accessible static/media trees
BACKUP_ROOT = BASE_DIR / 'backups'
BACKUP_DB_DIR = BACKUP_ROOT / 'database'
BACKUP_MEDIA_DIR = BACKUP_ROOT / 'media'

# Configurable GFS (Grandfather-Father-Son) Retention Policy
BACKUP_RETENTION_DAILY = int(os.getenv('BACKUP_RETENTION_DAILY', '7'))
BACKUP_RETENTION_WEEKLY = int(os.getenv('BACKUP_RETENTION_WEEKLY', '4'))
BACKUP_RETENTION_MONTHLY = int(os.getenv('BACKUP_RETENTION_MONTHLY', '12'))

# PostgreSQL Utility Executable Paths
PG_DUMP_PATH = os.getenv('PG_DUMP_PATH', 'pg_dump')
PG_RESTORE_PATH = os.getenv('PG_RESTORE_PATH', 'pg_restore')
PSQL_PATH = os.getenv('PSQL_PATH', 'psql')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ---------------------------------------------------------------------------
# Authentication & Session Configuration
# ---------------------------------------------------------------------------

# Where unauthenticated users are redirected when @login_required is applied
LOGIN_URL = '/login/'

# Where users land after a successful login (if no 'next' param exists)
LOGIN_REDIRECT_URL = '/dashboard/'

# Where users go after logout
LOGOUT_REDIRECT_URL = '/login/'

# Session expires when the browser is closed (unless "remember me" is checked)
SESSION_EXPIRE_AT_BROWSER_CLOSE = True

# Prevent JavaScript from reading the session cookie (XSS mitigation)
SESSION_COOKIE_HTTPONLY = True

# Session cookie SameSite policy (CSRF mitigation for cross-site requests)
SESSION_COOKIE_SAMESITE = 'Lax'

# CSRF cookie also restricted to HTTP (not readable by JS)
CSRF_COOKIE_HTTPONLY = True

# CSRF cookie SameSite policy
CSRF_COOKIE_SAMESITE = 'Lax'

# Maximum session age in seconds (8 hours for school LAN — overridden by remember_me)
SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 hours

# File upload security limits
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB max POST body
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB before temp file

# Content Security Policy header (served by X-Frame-Options middleware)
# Clickjacking protection: deny all iframe embedding of SSMS pages
X_FRAME_OPTIONS = 'DENY'

# Message storage — use session-based messages (requires session middleware)
MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'

# Fast password hasher during test execution to accelerate test suite runs
import sys
if 'test' in sys.argv:
    PASSWORD_HASHERS = [
        'django.contrib.auth.hashers.MD5PasswordHasher',
    ]


