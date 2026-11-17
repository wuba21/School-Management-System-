"""
Management command to enforce the GFS (Grandfather-Father-Son) backup retention policy.
Usage:
    python manage.py prune_backups [--type DATABASE|MEDIA] [--dry-run]
"""

from django.core.management.base import BaseCommand
from backup.services import BackupService


class Command(BaseCommand):
    help = "Prunes expired backups based on the GFS retention policy (7 daily, 4 weekly, 12 monthly)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--type',
            type=str,
            choices=['DATABASE', 'MEDIA'],
            default=None,
            help="Prune only a specific backup type (DATABASE or MEDIA)."
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            dest='dry_run',
            default=False,
            help="Simulate pruning without deleting files or updating records."
        )

    def handle(self, *args, **options):
        b_type = options['type']
        dry_run = options['dry_run']

        mode = "SIMULATION (Dry-Run)" if dry_run else "LIVE PRUNING"
        self.stdout.write(self.style.NOTICE(f"Executing Backup Retention Policy - Mode: {mode}"))

        res = BackupService.prune_backups(backup_type=b_type, dry_run=dry_run)

        self.stdout.write(self.style.SUCCESS(
            f"Retention Pruning Summary:\n"
            f"  - Backups Retained: {res['kept_count']}\n"
            f"  - Backups Pruned:   {res['pruned_count']}"
        ))

        if res['pruned_filenames']:
            self.stdout.write("Pruned archives:")
            for fn in res['pruned_filenames']:
                self.stdout.write(f"  * {fn}")
