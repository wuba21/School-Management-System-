"""
Data migration: create default superuser for initial deployment.

Runs automatically as part of `python manage.py migrate`.
Safe to run on every fresh SQLite deploy (Render free tier).
Skips silently if a superuser already exists (PostgreSQL / persistent DB).

Credentials can be overridden via environment variables:
  SUPERUSER_USERNAME  (default: admin)
  SUPERUSER_EMAIL     (default: admin@ssms.local)
  SUPERUSER_PASSWORD  (default: Admin@SSMS2024!)
"""

import os
from django.db import migrations


def create_default_superuser(apps, schema_editor):
    """Create a superuser if none exists."""
    # Use get_model() — safe inside migrations (no circular imports)
    User = apps.get_model('accounts', 'User')

    # Skip if any superuser already exists
    if User.objects.filter(is_superuser=True).exists():
        return

    username = os.environ.get('SUPERUSER_USERNAME', 'admin')
    email    = os.environ.get('SUPERUSER_EMAIL',    'admin@ssms.local')
    password = os.environ.get('SUPERUSER_PASSWORD', 'Admin@SSMS2024!')

    # create_superuser hashes the password correctly
    from django.contrib.auth.hashers import make_password
    User.objects.create(
        username=username,
        email=email,
        password=make_password(password),
        is_superuser=True,
        is_staff=True,
        is_active=True,
        is_approved=True,
    )
    print(f'\n  ✅ Default superuser created: username="{username}"')


def delete_default_superuser(apps, schema_editor):
    """Reverse: remove the auto-created superuser (only used in reverse migration)."""
    User = apps.get_model('accounts', 'User')
    username = os.environ.get('SUPERUSER_USERNAME', 'admin')
    User.objects.filter(username=username, is_superuser=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            create_default_superuser,
            reverse_code=delete_default_superuser,
        ),
    ]
