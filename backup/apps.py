import os
from django.apps import AppConfig
from django.conf import settings


class BackupConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'backup'
    verbose_name = 'System Backup & Recovery'

    def ready(self):
        # Ensure backup directories exist outside web-accessible roots
        try:
            db_dir = getattr(settings, 'BACKUP_DB_DIR', None)
            media_dir = getattr(settings, 'BACKUP_MEDIA_DIR', None)
            if db_dir:
                os.makedirs(db_dir, exist_ok=True)
            if media_dir:
                os.makedirs(media_dir, exist_ok=True)
        except Exception:
            pass
