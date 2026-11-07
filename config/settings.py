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
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

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
LANGUAGE_CODE = 'en-us'

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

# Media files (User uploads, student photos, generated PDF report cards)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

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

# CSRF cookie also restricted to HTTP (not readable by JS)
CSRF_COOKIE_HTTPONLY = True

# Message storage — use session-based messages (requires session middleware)
MESSAGE_STORAGE = 'django.contrib.messages.storage.session.SessionStorage'

# Fast password hasher during test execution to accelerate test suite runs
import sys
if 'test' in sys.argv:
    PASSWORD_HASHERS = [
        'django.contrib.auth.hashers.MD5PasswordHasher',
    ]


