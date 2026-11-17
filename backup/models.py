import os
from django.db import models
from django.conf import settings


class BackupRecord(models.Model):
    """
    Immutable tracking record for database and media backups.
    Stored inside the database for auditing and operational management.
    """
    BACKUP_TYPE_CHOICES = [
        ('DATABASE', 'PostgreSQL Database Backup'),
        ('MEDIA', 'Media & Document Backup'),
    ]

    STATUS_CHOICES = [
        ('COMPLETED', 'Completed Successfully'),
        ('FAILED', 'Failed'),
        ('CORRUPTED', 'Integrity Verification Failed'),
        ('PRUNED', 'Pruned by Retention Policy'),
    ]

    backup_type = models.CharField(max_length=20, choices=BACKUP_TYPE_CHOICES, db_index=True)
    filename = models.CharField(max_length=255, unique=True, help_text="Timestamped filename of backup archive")
    filepath = models.CharField(max_length=500, help_text="Absolute filesystem path outside public directories")
    file_size_bytes = models.BigIntegerField(default=0, help_text="Size of backup file in bytes")
    checksum_sha256 = models.CharField(max_length=64, blank=True, help_text="SHA-256 checksum for tamper & integrity verification")
    is_compressed = models.BooleanField(default=True, help_text="Whether backup archive is gzip/tar compressed")
    is_verified = models.BooleanField(default=False, help_text="Whether archive integrity was tested and verified")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='COMPLETED', db_index=True)
    notes = models.TextField(blank=True, help_text="Optional administration or audit notes")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='backups_created',
        help_text="Administrator who initiated this backup (null if automated system schedule)"
    )
    last_verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Backup Record'
        verbose_name_plural = 'Backup Records'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_backup_type_display()}] {self.filename} ({self.status})"

    @property
    def file_size_human(self):
        """Format byte size into human-readable string (KB, MB, GB)."""
        size = float(self.file_size_bytes)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"

    @property
    def exists_on_disk(self):
        """Check if backup archive file exists on disk."""
        return os.path.isfile(self.filepath)
