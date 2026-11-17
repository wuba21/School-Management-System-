"""
Management command: create_default_superuser
--------------------------------------------
Creates a default superuser for the deployment environment if no superuser
exists yet. Credentials are read from environment variables so they can be
set safely in Render / any CI environment without hard-coding secrets.

Environment variables (all optional — defaults shown):
  SUPERUSER_USERNAME  default: admin
  SUPERUSER_EMAIL     default: admin@ssms.local
  SUPERUSER_PASSWORD  default: Admin@SSMS2024!

Run automatically in Render Build Command:
  python manage.py create_default_superuser
"""

import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Create a default superuser if none exists (safe to run on every deploy)'

    def handle(self, *args, **options):
        User = get_user_model()

        username = os.environ.get('SUPERUSER_USERNAME', 'admin')
        email    = os.environ.get('SUPERUSER_EMAIL',    'admin@ssms.local')
        password = os.environ.get('SUPERUSER_PASSWORD', 'Admin@SSMS2024!')

        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write(
                self.style.WARNING(
                    f'Superuser already exists — skipping creation.'
                )
            )
            return

        try:
            user = User.objects.create_superuser(
                username=username,
                email=email,
                password=password,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Superuser created: username="{username}" email="{email}"'
                )
            )
        except Exception as exc:
            self.stderr.write(
                self.style.ERROR(f'❌ Failed to create superuser: {exc}')
            )
