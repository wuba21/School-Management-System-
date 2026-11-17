"""
Management command to securely export a backup archive to an external USB drive.
Usage:
    python manage.py export_backup --file <filename_or_id> --destination <usb_mount_path>
"""

import os
from django.core.management.base import BaseCommand, CommandError
from backup.services import BackupService
from backup.models import BackupRecord


class Command(BaseCommand):
    help = "Exports a verified backup archive to an external USB flash drive or secondary storage."

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            required=True,
            help="Filename or database ID of the backup record to export."
        )
        parser.add_argument(
            '--destination',
            type=str,
            required=True,
            help="Target USB folder path (e.g., E:\\SchoolBackups, /media/usb/backups)."
        )

    def handle(self, *args, **options):
        file_arg = options['file']
        dest_dir = options['destination']

        # Find record by ID or filename
        record = None
        if file_arg.isdigit():
            record = BackupRecord.objects.filter(id=int(file_arg)).first()
        if not record:
            record = BackupRecord.objects.filter(filename=file_arg).first()

        if not record:
            raise CommandError(f"Backup record matching '{file_arg}' not found.")

        self.stdout.write(self.style.NOTICE(
            f"Exporting backup '{record.filename}' to external destination '{dest_dir}'..."
        ))

        try:
            dest_file, checksum = BackupService.export_backup_to_usb(
                backup_record=record,
                destination_dir=dest_dir,
                user=None
            )
            self.stdout.write(self.style.SUCCESS(
                f"[SUCCESS] Backup successfully exported to external drive.\n"
                f"  - Source:      {record.filepath}\n"
                f"  - Destination: {dest_file}\n"
                f"  - Size:        {record.file_size_human}\n"
                f"  - SHA-256:     {checksum}\n"
                f"  - Verification: Copy integrity matched original checksum.\n"
                f"  - Server file:  Retained intact."
            ))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"[FAILED] USB export failed: {str(e)}"))
            raise CommandError(str(e))
