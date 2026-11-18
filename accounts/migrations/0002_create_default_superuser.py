"""
Data migration: create default superuser for initial deployment (secure provisioning).

Runs automatically as part of `python manage.py migrate`.
Only creates a superuser if SUPERUSER_PASSWORD is explicitly set in the environment.
Skips silently if a superuser already exists or if no password is provided in environment variables.
Never creates predictable or hardcoded administrator credentials.

Credentials can be provided via environment variables:
  SUPERUSER_USERNAME  (default: admin)
  SUPERUSER_EMAIL     (default: admin@ssms.local)
  SUPERUSER_PASSWORD  (required to auto-provision; if omitted, migration skips safely)
"""

import os
from django.db import migrations


def create_default_superuser(apps, schema_editor):
    """Create a superuser if none exists and explicit password is provided."""
    # Use get_model() — safe inside migrations (no circular imports)
    User = apps.get_model('accounts', 'User')

    # Skip if any superuser already exists
    if User.objects.filter(is_superuser=True).exists():
        return

    password = os.environ.get('SUPERUSER_PASSWORD')
    if not password:
        # Secure default: Do NOT create any superuser with a hardcoded or predictable password!
        print('\n  ℹ️  Automatic superuser creation skipped: SUPERUSER_PASSWORD environment variable not set.')
        print('      Run "python manage.py createsuperuser" to provision an administrator account.')
        return

    username = os.environ.get('SUPERUSER_USERNAME', 'admin')
    email    = os.environ.get('SUPERUSER_EMAIL',    'admin@ssms.local')

    # Hash the password correctly
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
    print(f'\n  ✅ Superuser provisioned from environment: username="{username}"')



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
