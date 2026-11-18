"""
Management command: create_default_superuser
--------------------------------------------
Creates a superuser for deployment or automated provisioning if no superuser
exists yet. Credentials must be supplied via CLI arguments or environment
variables. Never falls back to a predictable or hardcoded password.

Environment variables:
  SUPERUSER_USERNAME  default: admin
  SUPERUSER_EMAIL     default: admin@ssms.local
  SUPERUSER_PASSWORD  (required; skips safely if absent)

Usage:
  python manage.py create_default_superuser
  python manage.py create_default_superuser --username admin --email admin@example.com --password "SecureSecretPass123!"
"""

import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Create a default superuser securely if none exists (requires password via argument or env var)'

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, help='Administrator username')
        parser.add_argument('--email', type=str, help='Administrator email')
        parser.add_argument('--password', type=str, help='Administrator password')

    def handle(self, *args, **options):
        User = get_user_model()

        username = options.get('username') or os.environ.get('SUPERUSER_USERNAME', 'admin')
        email    = options.get('email') or os.environ.get('SUPERUSER_EMAIL', 'admin@ssms.local')
        password = options.get('password') or os.environ.get('SUPERUSER_PASSWORD')

        if User.objects.filter(is_superuser=True).exists():
            self.stdout.write(
                self.style.WARNING(
                    'Superuser already exists — skipping creation.'
                )
            )
            return

        if not password:
            self.stdout.write(
                self.style.WARNING(
                    'No password provided via --password or SUPERUSER_PASSWORD environment variable.\n'
                    'Skipping automatic superuser creation for security.\n'
                    'To manually create an administrator, run:\n'
                    '    python manage.py createsuperuser'
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

