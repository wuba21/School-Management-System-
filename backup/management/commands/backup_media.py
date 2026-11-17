"""
Management command to create a timestamped media and uploads backup archive.
Usage:
    python manage.py backup_media [--prune] [--notes "Optional note"]
"""

from django.core.management.base import BaseCommand, CommandError
from backup.services import BackupService


class Command(BaseCommand):
    help = "Creates a secure, compressed tar.gz archive of all uploaded student photos and documents."

    def add_arguments(self, parser):
        parser.add_argument(
            '--prune',
            action='store_true',
            dest='prune',
            default=False,
            help="Automatically prune expired media backups according to the GFS retention policy after creation."
        )
        parser.add_argument(
            '--notes',
            type=str,
            default="",
            help="Optional administration notes for this media backup record."
        )

    def handle(self, *args, **options):
        prune = options['prune']
        notes = options['notes']

        self.stdout.write(self.style.NOTICE("Initiating SSMS media & documents archive backup..."))

        try:
            record = BackupService.create_media_backup(
                user=None,
                prune=prune,
                notes=notes or "CLI media management command execution"
            )
            self.stdout.write(self.style.SUCCESS(
                f"[SUCCESS] Media backup created successfully.\n"
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
            self.stderr.write(self.style.ERROR(f"[FAILED] Media backup archive creation failed: {str(e)}"))
            raise CommandError(str(e))
