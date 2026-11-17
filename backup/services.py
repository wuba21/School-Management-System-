"""
System Backup, Recovery, and Disaster Resilience Service for SSMS.
Designed for offline Local Area Network (LAN) edge deployments.
"""

import os
import shutil
import hashlib
import gzip
import tarfile
import subprocess
import datetime
from pathlib import Path
from django.conf import settings
from django.utils import timezone
from django.db import connection

from backup.models import BackupRecord
from core.models import AuditLog


def validate_safe_path(target_path, allowed_base_dir):
    """
    Validates that target_path resolves strictly within allowed_base_dir.
    Mitigates path traversal attacks (e.g. ../../, directory spoofing).
    """
    base = os.path.abspath(str(allowed_base_dir))
    target = os.path.abspath(str(target_path))
    try:
        common = os.path.commonpath([base, target])
    except ValueError:
        return False
    return common == base


def compute_sha256(file_path):
    """
    Calculates SHA-256 checksum of a file in 64KB chunks to optimize memory.
    """
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


class BackupService:
    """
    Core service coordinating PostgreSQL database backups, media archives,
    integrity verification, GFS retention pruning, and disaster recovery.
    """

    @classmethod
    def get_backup_directories(cls):
        """Returns and ensures backup directories exist."""
        root = getattr(settings, 'BACKUP_ROOT', settings.BASE_DIR / 'backups')
        db_dir = getattr(settings, 'BACKUP_DB_DIR', root / 'database')
        media_dir = getattr(settings, 'BACKUP_MEDIA_DIR', root / 'media')
        os.makedirs(db_dir, exist_ok=True)
        os.makedirs(media_dir, exist_ok=True)
        return root, db_dir, media_dir

    # -------------------------------------------------------------------------
    # 1. DATABASE BACKUP
    # -------------------------------------------------------------------------
    @classmethod
    def create_database_backup(cls, user=None, compress=True, prune=False, notes=""):
        """
        Creates a timestamped database backup archive.
        - PostgreSQL: Uses pg_dump utility with custom or compressed format.
        - SQLite (Development/Test): Uses atomic sqlite3 backup API with gzip.
        """
        _, db_dir, _ = cls.get_backup_directories()
        now = timezone.now()
        timestamp_str = now.strftime('%Y%m%d_%H%M%S')

        db_settings = settings.DATABASES['default']
        engine = db_settings.get('ENGINE', '')

        if 'postgresql' in engine:
            ext = 'dump' if compress else 'sql'
            filename = f"ssms_db_backup_{timestamp_str}.{ext}"
            target_path = os.path.join(db_dir, filename)

            cls._dump_postgresql(db_settings, target_path, compress=compress)
        else:
            # SQLite atomic backup for local development and test suite
            ext = 'sqlite3.gz' if compress else 'sqlite3'
            filename = f"ssms_db_backup_{timestamp_str}.{ext}"
            target_path = os.path.join(db_dir, filename)

            cls._dump_sqlite(db_settings, target_path, compress=compress)

        # File validation and metadata calculation
        if not os.path.isfile(target_path):
            raise RuntimeError(f"Database backup failed: target file '{filename}' was not created.")

        file_size = os.path.getsize(target_path)
        checksum = compute_sha256(target_path)

        # Persist BackupRecord
        record = BackupRecord.objects.create(
            backup_type='DATABASE',
            filename=filename,
            filepath=target_path,
            file_size_bytes=file_size,
            checksum_sha256=checksum,
            is_compressed=compress,
            is_verified=True,
            status='COMPLETED',
            notes=notes or f"Automated database backup created at {now.isoformat()}",
            created_by=user,
            last_verified_at=now,
        )

        # Audit Log
        AuditLog.objects.create(
            actor=user,
            action='CREATE',
            entity_name='Backup',
            record_id=str(record.id),
            changes_json={
                'type': 'DATABASE',
                'filename': filename,
                'size_bytes': file_size,
                'sha256': checksum,
            }
        )

        # Optional retention pruning
        if prune:
            cls.prune_backups(backup_type='DATABASE')

        return record

    @classmethod
    def _dump_postgresql(cls, db_settings, target_path, compress=True):
        """
        Executes pg_dump securely without exposing database credentials in command line flags.
        """
        pg_dump_bin = getattr(settings, 'PG_DUMP_PATH', 'pg_dump')
        resolved_bin = shutil.which(pg_dump_bin)

        if not resolved_bin:
            # Check standard Windows PostgreSQL installations if not on PATH
            for version in ['18', '17', '16', '15', '14']:
                candidate = f"C:\\Program Files\\PostgreSQL\\{version}\\bin\\pg_dump.exe"
                if os.path.isfile(candidate):
                    resolved_bin = candidate
                    break

        db_name = db_settings.get('NAME')
        user = db_settings.get('USER')
        password = db_settings.get('PASSWORD', '')
        host = db_settings.get('HOST', '127.0.0.1')
        port = str(db_settings.get('PORT', '5432'))

        if resolved_bin:
            env = os.environ.copy()
            if password:
                env['PGPASSWORD'] = password

            cmd = [
                resolved_bin,
                '-h', host,
                '-p', port,
                '-U', user,
                '--no-password',
            ]

            if compress:
                # Custom format (-Fc) is natively compressed and verified
                cmd.extend(['-F', 'c', '-b', '-v', '-f', target_path, db_name])
                res = subprocess.run(cmd, env=env, capture_output=True, text=True)
                if res.returncode != 0:
                    sanitized_err = res.stderr.replace(password, '******') if password else res.stderr
                    raise RuntimeError(f"pg_dump execution failed (exit code {res.returncode}): {sanitized_err}")
            else:
                cmd.extend(['-F', 'p', '-f', target_path, db_name])
                res = subprocess.run(cmd, env=env, capture_output=True, text=True)
                if res.returncode != 0:
                    sanitized_err = res.stderr.replace(password, '******') if password else res.stderr
                    raise RuntimeError(f"pg_dump execution failed (exit code {res.returncode}): {sanitized_err}")
        else:
            # Fallback when pg_dump is not installed: Use Django data serialization
            from django.core.management import call_command
            import io
            out_str = io.StringIO()
            call_command('dumpdata', '--natural-foreign', '--natural-primary', stdout=out_str)
            raw_data = out_str.getvalue().encode('utf-8')

            if compress:
                with gzip.open(target_path, 'wb') as gz:
                    gz.write(raw_data)
            else:
                with open(target_path, 'wb') as f:
                    f.write(raw_data)

    @classmethod
    def _dump_sqlite(cls, db_settings, target_path, compress=True):
        """
        Executes atomic SQLite online backup and compresses with gzip.
        """
        import sqlite3
        source_db_path = str(db_settings.get('NAME'))
        temp_raw_path = target_path + ".raw"

        source_conn = sqlite3.connect(source_db_path)
        dest_conn = sqlite3.connect(temp_raw_path)
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
            source_conn.close()

        if compress:
            with open(temp_raw_path, 'rb') as f_in:
                with gzip.open(target_path, 'wb', compresslevel=6) as f_out:
                    shutil.copyfileobj(f_in, f_out)
            if os.path.exists(temp_raw_path):
                os.remove(temp_raw_path)
        else:
            if os.path.exists(target_path):
                os.remove(target_path)
            os.rename(temp_raw_path, target_path)

    # -------------------------------------------------------------------------
    # 2. MEDIA BACKUP
    # -------------------------------------------------------------------------
    @classmethod
    def create_media_backup(cls, user=None, prune=False, notes=""):
        """
        Creates a compressed tar.gz archive of all uploaded student photos,
        teacher credentials, and system documents in MEDIA_ROOT.
        """
        _, _, media_dir = cls.get_backup_directories()
        media_root = str(settings.MEDIA_ROOT)
        now = timezone.now()
        timestamp_str = now.strftime('%Y%m%d_%H%M%S')
        filename = f"ssms_media_backup_{timestamp_str}.tar.gz"
        target_path = os.path.join(media_dir, filename)

        os.makedirs(media_root, exist_ok=True)

        with tarfile.open(target_path, "w:gz") as tar:
            # Check if media root has files
            has_files = False
            for root, dirs, files in os.walk(media_root):
                for f in files:
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, media_root)
                    tar.add(full_p, arcname=rel_p)
                    has_files = True
            
            if not has_files:
                # Add an empty metadata marker if no media files exist yet
                temp_marker = os.path.join(media_dir, ".empty_media_manifest")
                with open(temp_marker, "w") as f:
                    f.write(f"SSMS Media Archive Manifest. Created: {now.isoformat()}\n")
                tar.add(temp_marker, arcname=".empty_media_manifest")
                if os.path.exists(temp_marker):
                    os.remove(temp_marker)

        file_size = os.path.getsize(target_path)
        checksum = compute_sha256(target_path)

        record = BackupRecord.objects.create(
            backup_type='MEDIA',
            filename=filename,
            filepath=target_path,
            file_size_bytes=file_size,
            checksum_sha256=checksum,
            is_compressed=True,
            is_verified=True,
            status='COMPLETED',
            notes=notes or f"Media backup archive created at {now.isoformat()}",
            created_by=user,
            last_verified_at=now,
        )

        AuditLog.objects.create(
            actor=user,
            action='CREATE',
            entity_name='Backup',
            record_id=str(record.id),
            changes_json={
                'type': 'MEDIA',
                'filename': filename,
                'size_bytes': file_size,
                'sha256': checksum,
            }
        )

        if prune:
            cls.prune_backups(backup_type='MEDIA')

        return record

    # -------------------------------------------------------------------------
    # 3. INTEGRITY VERIFICATION
    # -------------------------------------------------------------------------
    @classmethod
    def verify_backup_integrity(cls, backup_record):
        """
        Tests the integrity of an existing backup file on disk:
        1. Checks physical existence.
        2. Recalculates and verifies SHA-256 against recorded checksum.
        3. Tests decompression validity (gzip/tar decompression test).
        """
        if not backup_record.exists_on_disk:
            backup_record.status = 'CORRUPTED'
            backup_record.is_verified = False
            backup_record.save(update_fields=['status', 'is_verified'])
            return False, f"Archive file '{backup_record.filename}' not found on server disk."

        # Verify SHA-256
        current_hash = compute_sha256(backup_record.filepath)
        if backup_record.checksum_sha256 and current_hash != backup_record.checksum_sha256:
            backup_record.status = 'CORRUPTED'
            backup_record.is_verified = False
            backup_record.save(update_fields=['status', 'is_verified'])
            return False, f"SHA-256 hash mismatch! Recorded: {backup_record.checksum_sha256[:12]}..., Computed: {current_hash[:12]}..."

        # Test archive structure
        filepath = backup_record.filepath
        try:
            if filepath.endswith('.tar.gz') or filepath.endswith('.tgz'):
                with tarfile.open(filepath, 'r:gz') as tar:
                    tar.getmembers()
            elif filepath.endswith('.dump'):
                with open(filepath, 'rb') as f:
                    header = f.read(5)
                    if header != b'PGDMP':
                        raise ValueError(f"Invalid PostgreSQL custom dump format: expected magic bytes 'PGDMP', found {header!r}")
            elif filepath.endswith('.gz'):
                with gzip.open(filepath, 'rb') as gz:
                    # Read in chunks to verify gzip stream integrity
                    for _ in iter(lambda: gz.read(65536), b''):
                        pass
        except Exception as e:
            backup_record.status = 'CORRUPTED'
            backup_record.is_verified = False
            backup_record.save(update_fields=['status', 'is_verified'])
            return False, f"Archive decompression verification failed: {str(e)}"

        backup_record.is_verified = True
        backup_record.status = 'COMPLETED'
        backup_record.last_verified_at = timezone.now()
        backup_record.save(update_fields=['is_verified', 'status', 'last_verified_at'])
        return True, f"Integrity check passed: Valid archive with matching SHA-256 ({current_hash[:16]}...)"

    # -------------------------------------------------------------------------
    # 4. GFS RETENTION PRUNING
    # -------------------------------------------------------------------------
    @classmethod
    def prune_backups(cls, backup_type=None, dry_run=False):
        """
        Grandfather-Father-Son (GFS) retention rotation:
        - Retains 7 daily backups
        - Retains 4 weekly backups
        - Retains 12 monthly backups
        - CRITICAL RULE: Never deletes the only available valid backup.
        """
        daily_limit = getattr(settings, 'BACKUP_RETENTION_DAILY', 7)
        weekly_limit = getattr(settings, 'BACKUP_RETENTION_WEEKLY', 4)
        monthly_limit = getattr(settings, 'BACKUP_RETENTION_MONTHLY', 12)

        types_to_prune = [backup_type] if backup_type else ['DATABASE', 'MEDIA']
        pruned_records = []
        kept_records = []

        for b_type in types_to_prune:
            records = list(BackupRecord.objects.filter(
                backup_type=b_type,
                status='COMPLETED'
            ).order_by('-created_at'))

            if len(records) <= 1:
                # NEVER delete the only valid backup
                kept_records.extend(records)
                continue

            keep_ids = set()

            # 1. Always keep the absolute latest backup
            keep_ids.add(records[0].id)

            # 2. Daily backups (up to daily_limit distinct calendar days)
            seen_days = set()
            for rec in records:
                day_key = rec.created_at.date()
                if day_key not in seen_days and len(seen_days) < daily_limit:
                    seen_days.add(day_key)
                    keep_ids.add(rec.id)

            # 3. Weekly backups (up to weekly_limit distinct calendar weeks)
            seen_weeks = set()
            for rec in records:
                cal = rec.created_at.isocalendar()
                week_key = (cal[0], cal[1])  # (year, week_num)
                if week_key not in seen_weeks and len(seen_weeks) < weekly_limit:
                    seen_weeks.add(week_key)
                    keep_ids.add(rec.id)

            # 4. Monthly backups (up to monthly_limit distinct calendar months)
            seen_months = set()
            for rec in records:
                month_key = (rec.created_at.year, rec.created_at.month)
                if month_key not in seen_months and len(seen_months) < monthly_limit:
                    seen_months.add(month_key)
                    keep_ids.add(rec.id)

            for rec in records:
                if rec.id in keep_ids:
                    kept_records.append(rec)
                else:
                    pruned_records.append(rec)
                    if not dry_run:
                        # Remove file safely from disk
                        if os.path.isfile(rec.filepath):
                            try:
                                os.remove(rec.filepath)
                            except OSError:
                                pass
                        rec.status = 'PRUNED'
                        rec.save(update_fields=['status'])

                        AuditLog.objects.create(
                            actor=None,
                            action='DELETE',
                            entity_name='Backup',
                            record_id=str(rec.id),
                            changes_json={
                                'action': 'PRUNED_BY_RETENTION',
                                'filename': rec.filename,
                                'type': rec.backup_type,
                            }
                        )

        return {
            'kept_count': len(kept_records),
            'pruned_count': len(pruned_records),
            'pruned_filenames': [r.filename for r in pruned_records],
        }

    # -------------------------------------------------------------------------
    # 5. EXTERNAL USB BACKUP EXPORT
    # -------------------------------------------------------------------------
    @classmethod
    def export_backup_to_usb(cls, backup_record, destination_dir, user=None):
        """
        Exports a backup archive to an external USB or secondary storage path.
        - Validates target directory exists and is writable.
        - Preserves file metadata with shutil.copy2.
        - Verifies integrity of copied archive on USB drive.
        - Leaves the original server backup intact.
        """
        if not backup_record.exists_on_disk:
            raise FileNotFoundError(f"Source backup '{backup_record.filename}' does not exist on server storage.")

        dest_dir = os.path.abspath(str(destination_dir))
        if not os.path.isdir(dest_dir):
            raise ValueError(f"Destination path '{dest_dir}' does not exist or is not a directory.")

        if not os.access(dest_dir, os.W_OK):
            raise PermissionError(f"Destination directory '{dest_dir}' is read-only or permission is denied.")

        dest_file_path = os.path.join(dest_dir, backup_record.filename)

        # Copy archive preserving timestamps and permissions
        shutil.copy2(backup_record.filepath, dest_file_path)

        # Verify integrity of copied file on USB
        exported_checksum = compute_sha256(dest_file_path)
        if backup_record.checksum_sha256 and exported_checksum != backup_record.checksum_sha256:
            if os.path.exists(dest_file_path):
                os.remove(dest_file_path)
            raise RuntimeError("Exported file on USB failed SHA-256 checksum verification. Copy was removed.")

        AuditLog.objects.create(
            actor=user,
            action='CREATE',
            entity_name='BackupExport',
            record_id=str(backup_record.id),
            changes_json={
                'filename': backup_record.filename,
                'destination_path': dest_file_path,
                'sha256': exported_checksum,
            }
        )

        return dest_file_path, exported_checksum

    # -------------------------------------------------------------------------
    # 6. RESTORE AND RECOVERY
    # -------------------------------------------------------------------------
    @classmethod
    def restore_database(cls, backup_file_or_record, confirm=False, target_db_override=None, user=None):
        """
        Restores a database from a backup archive.
        - Requires explicit confirm=True.
        - Verifies integrity before touching database.
        - Supports PostgreSQL (pg_restore / psql) and SQLite.
        """
        if not confirm:
            raise ValueError(
                "Restoration safety guard: Explicit confirmation (confirm=True) is required "
                "to restore the database."
            )

        if isinstance(backup_file_or_record, BackupRecord):
            file_path = backup_file_or_record.filepath
            record = backup_file_or_record
        else:
            file_path = str(backup_file_or_record)
            record = BackupRecord.objects.filter(filepath=file_path).first()

        if not os.path.isfile(file_path):
            raise FileNotFoundError(f"Restore target archive '{file_path}' does not exist.")

        # Pre-restoration integrity test
        try:
            if file_path.endswith('.gz'):
                with gzip.open(file_path, 'rb') as gz:
                    gz.read(1024)
        except Exception as e:
            raise RuntimeError(f"Restore aborted: Archive failed decompression check: {str(e)}")

        db_settings = settings.DATABASES['default']
        engine = db_settings.get('ENGINE', '')
        target_db = target_db_override or db_settings.get('NAME')

        if 'postgresql' in engine:
            cls._restore_postgresql(db_settings, file_path, target_db=target_db)
        else:
            cls._restore_sqlite(file_path, target_db=target_db)

        # Audit Log
        AuditLog.objects.create(
            actor=user,
            action='OVERRIDE',
            entity_name='DatabaseRestore',
            record_id=str(record.id) if record else file_path,
            changes_json={
                'restored_file': os.path.basename(file_path),
                'target_database': str(target_db),
                'timestamp': timezone.now().isoformat(),
            }
        )

        return True, f"Successfully restored database from '{os.path.basename(file_path)}' to '{target_db}'."

    @classmethod
    def _restore_postgresql(cls, db_settings, file_path, target_db=None):
        """Executes pg_restore or psql with safe credential passing."""
        pg_restore_bin = getattr(settings, 'PG_RESTORE_PATH', 'pg_restore')
        psql_bin = getattr(settings, 'PSQL_PATH', 'psql')
        resolved_restore = shutil.which(pg_restore_bin)
        if not resolved_restore:
            for version in ['18', '17', '16', '15', '14']:
                candidate = f"C:\\Program Files\\PostgreSQL\\{version}\\bin\\pg_restore.exe"
                if os.path.isfile(candidate):
                    resolved_restore = candidate
                    break

        resolved_psql = shutil.which(psql_bin)
        if not resolved_psql:
            for version in ['18', '17', '16', '15', '14']:
                candidate = f"C:\\Program Files\\PostgreSQL\\{version}\\bin\\psql.exe"
                if os.path.isfile(candidate):
                    resolved_psql = candidate
                    break

        user = db_settings.get('USER')
        password = db_settings.get('PASSWORD', '')
        host = db_settings.get('HOST', '127.0.0.1')
        port = str(db_settings.get('PORT', '5432'))
        dbname = target_db or db_settings.get('NAME')

        env = os.environ.copy()
        if password:
            env['PGPASSWORD'] = password

        if file_path.endswith('.dump') and resolved_restore:
            cmd = [
                resolved_restore,
                '-h', host,
                '-p', port,
                '-U', user,
                '-d', dbname,
                '--clean',
                '--if-exists',
                file_path
            ]
            res = subprocess.run(cmd, env=env, capture_output=True, text=True)
            if res.returncode not in (0, 1):  # pg_restore exit code 1 represents warnings
                sanitized_err = res.stderr.replace(password, '******') if password else res.stderr
                raise RuntimeError(f"pg_restore failed (exit code {res.returncode}): {sanitized_err}")
        else:
            # SQL / SQL.GZ file restoration
            # Decompress and load
            if file_path.endswith('.gz'):
                with gzip.open(file_path, 'rb') as gz:
                    sql_bytes = gz.read()
            else:
                with open(file_path, 'rb') as f:
                    sql_bytes = f.read()

            if resolved_psql:
                cmd = [resolved_psql, '-h', host, '-p', port, '-U', user, '-d', dbname]
                res = subprocess.run(cmd, input=sql_bytes, env=env, capture_output=True)
                if res.returncode != 0:
                    err_msg = res.stderr.decode('utf-8', errors='replace')
                    sanitized_err = err_msg.replace(password, '******') if password else err_msg
                    raise RuntimeError(f"psql restore failed (exit code {res.returncode}): {sanitized_err}")
            else:
                # If neither binary is present, try loading serialized data if json/sql
                try:
                    from django.core.management import call_command
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as tf:
                        tf.write(sql_bytes)
                        tf_name = tf.name
                    try:
                        call_command('loaddata', tf_name)
                    finally:
                        if os.path.exists(tf_name):
                            os.remove(tf_name)
                except Exception as e:
                    raise RuntimeError(f"Restore failed: PostgreSQL utilities not found on system: {str(e)}")

    @classmethod
    def _restore_sqlite(cls, file_path, target_db=None):
        """Decompresses and replaces SQLite database file."""
        import sqlite3
        dest_db_path = str(target_db)

        if file_path.endswith('.gz'):
            with gzip.open(file_path, 'rb') as f_in:
                with open(dest_db_path, 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
        else:
            shutil.copy2(file_path, dest_db_path)
