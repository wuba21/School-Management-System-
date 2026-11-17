"""
Management command to create a timestamped database backup.
Usage:
    python manage.py backup_database [--no-compress] [--prune] [--notes "Optional note"]
"""

from django.core.management.base import BaseCommand, CommandError
from backup.services import BackupService


class Command(BaseCommand):
    help = "Creates a secure, timestamped, compressed database backup archive."

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-compress',
            action='store_true',
            dest='no_compress',
            default=False,
            help="Do not compress the backup archive (generate plain SQL or uncompressed dump)."
        )
        parser.add_argument(
            '--prune',
            action='store_true',
            dest='prune',
            default=False,
            help="Automatically prune expired backups according to the GFS retention policy after creation."
        )
        parser.add_argument(
            '--notes',
            type=str,
            default="",
            help="Optional administration notes for this backup record."
        )

    def handle(self, *args, **options):
        compress = not options['no_compress']
        prune = options['prune']
        notes = options['notes']

        self.stdout.write(self.style.NOTICE("Initiating SSMS database backup..."))

        try:
            record = BackupService.create_database_backup(
                user=None,
                compress=compress,
                prune=prune,
                notes=notes or "CLI management command execution"
            )
            self.stdout.write(self.style.SUCCESS(
                f"[SUCCESS] Database backup created successfully.\n"
                f"  - Filename:    {record.filename}\n"
                f"  - Path:        {record.filepath}\n"
                f"  - Size:        {record.file_size_human} ({record.file_size_bytes} bytes)\n"
                f"  - SHA-256:     {record.checksum_sha256}\n"
                f"  - Verified:    {record.is_verified}\n"
                f"  - Timestamp:   {record.created_at.strftime('%Y-%m-%d %H:%M:%S')}"
            ))
            if prune:
                self.stdout.write(self.style.NOTICE("Retention pruning executed."))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"[FAILED] Database backup creation failed: {str(e)}"))
            raise CommandError(str(e))
