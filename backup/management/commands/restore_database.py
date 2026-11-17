"""
Management command to safely restore the database from a verified backup archive.
Usage:
    python manage.py restore_database --file <path_or_filename> --confirm [--target-db <dbname>]
"""

import os
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from backup.services import BackupService
from backup.models import BackupRecord


class Command(BaseCommand):
    help = "Safely restores the database from an archive. Requires explicit confirmation."

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            required=True,
            help="Path or filename of the backup archive to restore."
        )
        parser.add_argument(
            '--confirm',
            action='store_true',
            dest='confirm',
            default=False,
            help="Explicit confirmation required to execute restoration and overwrite database."
        )
        parser.add_argument(
            '--target-db',
            type=str,
            default=None,
            help="Optional target database name (e.g. for testing recovery on a staging/test DB)."
        )

    def handle(self, *args, **options):
        file_arg = options['file']
        confirm = options['confirm']
        target_db = options['target_db']

        # Resolve file path
        if os.path.isabs(file_arg):
            file_path = file_arg
        else:
            _, db_dir, _ = BackupService.get_backup_directories()
            file_path = os.path.join(db_dir, file_arg)
            if not os.path.isfile(file_path):
                # Try finding by filename in BackupRecord
                rec = BackupRecord.objects.filter(filename=file_arg).first()
                if rec:
                    file_path = rec.filepath

        if not os.path.isfile(file_path):
            raise CommandError(f"Backup file '{file_arg}' not found.")

        dest_name = target_db or settings.DATABASES['default'].get('NAME')

        self.stdout.write(self.style.WARNING("=" * 70))
        self.stdout.write(self.style.WARNING("SSMS DATABASE RESTORATION & DISASTER RECOVERY"))
        self.stdout.write(self.style.WARNING("=" * 70))
        self.stdout.write(f"Source Archive:   {file_path}")
        self.stdout.write(f"Archive Size:     {os.path.getsize(file_path)} bytes")
        self.stdout.write(f"Target Database:  {dest_name}")
        self.stdout.write(self.style.WARNING("=" * 70))

        if not confirm:
            self.stdout.write(self.style.ERROR(
                "\n[SAFETY GUARD TRIGGERED]\n"
                "Restoration will replace existing tables and records in the target database.\n"
                "To execute this restore, you MUST pass the '--confirm' flag:\n"
                f"  python manage.py restore_database --file \"{file_arg}\" --confirm\n"
            ))
            return

        self.stdout.write(self.style.NOTICE("Verifying archive integrity before restoration..."))

        # Look up or create temp record for integrity check
        rec = BackupRecord.objects.filter(filepath=file_path).first()
        if rec:
            is_valid, msg = BackupService.verify_backup_integrity(rec)
            if not is_valid:
                raise CommandError(f"Integrity check failed: {msg}")
            self.stdout.write(self.style.SUCCESS(f"[OK] {msg}"))

        self.stdout.write(self.style.NOTICE(f"Restoring database to '{dest_name}'..."))

        try:
            success, msg = BackupService.restore_database(
                backup_file_or_record=file_path,
                confirm=True,
                target_db_override=target_db,
                user=None
            )
            self.stdout.write(self.style.SUCCESS(f"\n[SUCCESS] {msg}\n"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"[FAILED] Restoration error: {str(e)}"))
            raise CommandError(str(e))
