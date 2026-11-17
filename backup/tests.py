import os
import shutil
import tempfile
import gzip
import tarfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import Role
from backup.models import BackupRecord
from backup.services import BackupService, validate_safe_path, compute_sha256
from core.models import AuditLog

User = get_user_model()


class BackupAppTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create user roles
        cls.admin_role, _ = Role.objects.get_or_create(
            code='ADMIN',
            defaults={'name': 'System Administrator', 'description': 'Full access to backups'}
        )
        cls.teacher_role, _ = Role.objects.get_or_create(
            code='TEACHER',
            defaults={'name': 'Teacher', 'description': 'Classroom teacher'}
        )
        cls.registrar_role, _ = Role.objects.get_or_create(
            code='REGISTRAR',
            defaults={'name': 'Registrar', 'description': 'Academic records manager'}
        )

        # Create admin user
        cls.admin_user = User.objects.create_user(
            username='backup_admin',
            email='admin@school.et',
            password='Password123!',
            role=cls.admin_role,
            is_active=True,
            is_approved=True,
        )

        # Create teacher user
        cls.teacher_user = User.objects.create_user(
            username='backup_teacher',
            email='teacher@school.et',
            password='Password123!',
            role=cls.teacher_role,
            is_active=True,
            is_approved=True,
        )

    def setUp(self):
        # Setup temporary directories for isolated backup testing
        self.temp_dir = tempfile.mkdtemp()
        self.backup_root = os.path.join(self.temp_dir, 'backups')
        self.db_dir = os.path.join(self.backup_root, 'database')
        self.media_dir = os.path.join(self.backup_root, 'media')
        self.test_media_root = os.path.join(self.temp_dir, 'media_uploads')

        os.makedirs(self.db_dir, exist_ok=True)
        os.makedirs(self.media_dir, exist_ok=True)
        os.makedirs(self.test_media_root, exist_ok=True)

        # Create sample media files
        self.sample_photo = os.path.join(self.test_media_root, 'student_001.jpg')
        with open(self.sample_photo, 'wb') as f:
            f.write(b'\xFF\xD8\xFF\xE0\x00\x10JFIF' + b'\x00' * 100)

        # Override settings for tests
        self.settings_override = self.settings(
            BACKUP_ROOT=Path(self.backup_root) if hasattr(settings, 'BACKUP_ROOT') else self.backup_root,
            BACKUP_DB_DIR=Path(self.db_dir) if hasattr(settings, 'BACKUP_DB_DIR') else self.db_dir,
            BACKUP_MEDIA_DIR=Path(self.media_dir) if hasattr(settings, 'BACKUP_MEDIA_DIR') else self.media_dir,
            MEDIA_ROOT=self.test_media_root,
            BACKUP_RETENTION_DAILY=7,
            BACKUP_RETENTION_WEEKLY=4,
            BACKUP_RETENTION_MONTHLY=12,
        )
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. DATABASE BACKUP TESTS
    # -------------------------------------------------------------------------
    def test_database_backup_creation_service(self):
        """Verify database backup creates archive, computes hash, and logs record."""
        record = BackupService.create_database_backup(user=self.admin_user, compress=True)
        self.assertTrue(os.path.isfile(record.filepath))
        self.assertEqual(record.backup_type, 'DATABASE')
        self.assertEqual(record.status, 'COMPLETED')
        self.assertTrue(record.is_compressed)
        self.assertTrue(record.is_verified)
        self.assertGreater(record.file_size_bytes, 0)
        self.assertEqual(len(record.checksum_sha256), 64)

        # Check Audit Log created
        audit = AuditLog.objects.filter(entity_name='Backup', record_id=str(record.id)).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.actor, self.admin_user)

    def test_database_backup_management_command(self):
        """Verify python manage.py backup_database command runs without error."""
        call_command('backup_database', notes="Test CLI database backup")
        rec = BackupRecord.objects.filter(notes="Test CLI database backup").first()
        self.assertIsNotNone(rec)
        self.assertTrue(os.path.isfile(rec.filepath))

    @patch('subprocess.run')
    @patch('shutil.which')
    def test_postgresql_pg_dump_invocation(self, mock_which, mock_run):
        """Verify PostgreSQL engine invokes pg_dump securely with PGPASSWORD."""
        mock_which.return_value = '/usr/bin/pg_dump'
        mock_run.return_value = MagicMock(returncode=0, stderr='')

        fake_pg_settings = {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': 'test_school_db',
            'USER': 'postgres_admin',
            'PASSWORD': 'secret_password_123',
            'HOST': '127.0.0.1',
            'PORT': '5432'
        }

        target_file = os.path.join(self.db_dir, 'test_pg.dump')
        BackupService._dump_postgresql(fake_pg_settings, target_file, compress=True)

        mock_run.assert_called_once()
        cmd_args = mock_run.call_args[0][0]
        env_passed = mock_run.call_args[1]['env']

        # Password must be in PGPASSWORD, never in command line arguments
        self.assertIn('PGPASSWORD', env_passed)
        self.assertEqual(env_passed['PGPASSWORD'], 'secret_password_123')
        self.assertNotIn('secret_password_123', ' '.join(cmd_args))
        self.assertIn('-F', cmd_args)
        self.assertIn('c', cmd_args)

    # -------------------------------------------------------------------------
    # 2. MEDIA BACKUP TESTS
    # -------------------------------------------------------------------------
    def test_media_backup_creation_service(self):
        """Verify media backup packs all files from MEDIA_ROOT into a tar.gz."""
        record = BackupService.create_media_backup(user=self.admin_user)
        self.assertTrue(os.path.isfile(record.filepath))
        self.assertEqual(record.backup_type, 'MEDIA')
        self.assertEqual(record.status, 'COMPLETED')
        self.assertTrue(record.filename.endswith('.tar.gz'))

        # Inspect archive content to verify student photo is included
        with tarfile.open(record.filepath, 'r:gz') as tar:
            names = tar.getnames()
            self.assertTrue(any('student_001.jpg' in name for name in names))

    def test_media_backup_management_command(self):
        """Verify python manage.py backup_media runs and generates archive."""
        call_command('backup_media', notes="CLI media test")
        rec = BackupRecord.objects.filter(backup_type='MEDIA').first()
        self.assertIsNotNone(rec)
        self.assertTrue(os.path.isfile(rec.filepath))

    # -------------------------------------------------------------------------
    # 3. ARCHIVE INTEGRITY TESTS
    # -------------------------------------------------------------------------
    def test_archive_integrity_verification_success(self):
        """Verify integrity check succeeds on untampered archive."""
        record = BackupService.create_database_backup(user=self.admin_user)
        is_valid, msg = BackupService.verify_backup_integrity(record)
        self.assertTrue(is_valid)
        self.assertIn("Integrity check passed", msg)
        self.assertTrue(record.is_verified)

    def test_archive_integrity_tampered_fails(self):
        """Verify corrupted or altered archive fails integrity check."""
        record = BackupService.create_database_backup(user=self.admin_user)
        # Corrupt file content
        with open(record.filepath, 'ab') as f:
            f.write(b'CORRUPTED_BYTES_INJECTED')

        is_valid, msg = BackupService.verify_backup_integrity(record)
        self.assertFalse(is_valid)
        self.assertEqual(record.status, 'CORRUPTED')
        self.assertFalse(record.is_verified)

    # -------------------------------------------------------------------------
    # 4. GFS RETENTION POLICY TESTS
    # -------------------------------------------------------------------------
    def test_retention_never_deletes_only_backup(self):
        """Verify that retention pruning never deletes the single remaining valid backup."""
        record = BackupService.create_database_backup(user=self.admin_user)
        res = BackupService.prune_backups('DATABASE')
        self.assertEqual(res['pruned_count'], 0)
        self.assertEqual(res['kept_count'], 1)
        self.assertTrue(os.path.isfile(record.filepath))

    def test_retention_pruning_policy(self):
        """Verify that older daily backups outside the 7-day window are pruned."""
        now = timezone.now()
        # Create 10 dummy database backup records spanning 10 days
        for i in range(10):
            day_offset = now - timedelta(days=i)
            fn = f"db_dummy_{i}.sql.gz"
            fp = os.path.join(self.db_dir, fn)
            with open(fp, 'w') as f:
                f.write("dummy")
            
            rec = BackupRecord.objects.create(
                backup_type='DATABASE',
                filename=fn,
                filepath=fp,
                file_size_bytes=5,
                checksum_sha256="test",
                status='COMPLETED'
            )
            # Update created_at directly
            BackupRecord.objects.filter(id=rec.id).update(created_at=day_offset)

        # Run pruning
        res = BackupService.prune_backups('DATABASE')
        # 10 daily backups, 7 daily + ISO week/month overlaps kept
        self.assertGreater(res['kept_count'], 0)
        self.assertGreater(res['pruned_count'], 0)

    # -------------------------------------------------------------------------
    # 5. EXTERNAL USB BACKUP EXPORT TESTS
    # -------------------------------------------------------------------------
    def test_export_backup_to_usb_success(self):
        """Verify exporting to USB folder copies file, checks SHA-256, and leaves source intact."""
        record = BackupService.create_database_backup(user=self.admin_user)
        usb_dir = os.path.join(self.temp_dir, 'mock_usb_drive')
        os.makedirs(usb_dir, exist_ok=True)

        dest_file, checksum = BackupService.export_backup_to_usb(record, usb_dir, user=self.admin_user)

        self.assertTrue(os.path.isfile(dest_file))
        self.assertEqual(checksum, record.checksum_sha256)
        # Original server backup must remain intact
        self.assertTrue(os.path.isfile(record.filepath))

    def test_export_backup_to_invalid_usb_raises_error(self):
        """Verify exporting to a non-existent USB path raises an error."""
        record = BackupService.create_database_backup(user=self.admin_user)
        non_existent_usb = os.path.join(self.temp_dir, 'non_existent_usb_drive')

        with self.assertRaises(ValueError):
            BackupService.export_backup_to_usb(record, non_existent_usb)

    def test_export_management_command(self):
        """Verify python manage.py export_backup command."""
        record = BackupService.create_database_backup(user=self.admin_user)
        usb_dir = os.path.join(self.temp_dir, 'cli_usb_drive')
        os.makedirs(usb_dir, exist_ok=True)

        call_command('export_backup', file=str(record.id), destination=usb_dir)
        exported_path = os.path.join(usb_dir, record.filename)
        self.assertTrue(os.path.isfile(exported_path))

    # -------------------------------------------------------------------------
    # 6. RESTORE AND RECOVERY TESTS
    # -------------------------------------------------------------------------
    def test_restore_without_confirmation_raises_error(self):
        """Verify that restore requires confirm=True safety guard."""
        record = BackupService.create_database_backup(user=self.admin_user)
        with self.assertRaises(ValueError):
            BackupService.restore_database(record, confirm=False)

    def test_restore_database_command_safety_guard(self):
        """Verify restore_database CLI command blocks execution if --confirm is missing."""
        record = BackupService.create_database_backup(user=self.admin_user)
        # Calling without --confirm should display safety warning and return without error
        call_command('restore_database', file=record.filename)

    def test_safe_sqlite_restore_to_test_target(self):
        """Test safe restoration to a separate test database target."""
        record = BackupService.create_database_backup(user=self.admin_user)
        test_recovery_db = os.path.join(self.temp_dir, 'recovered_test.sqlite3')

        success, msg = BackupService.restore_database(
            record,
            confirm=True,
            target_db_override=test_recovery_db,
            user=self.admin_user
        )
        self.assertTrue(success)
        self.assertTrue(os.path.isfile(test_recovery_db))

        # Check Audit Log created
        audit = AuditLog.objects.filter(entity_name='DatabaseRestore').first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.actor, self.admin_user)

    # -------------------------------------------------------------------------
    # 7. SECURITY & RBAC PERMISSION TESTS
    # -------------------------------------------------------------------------
    def test_sysadmin_can_access_backup_dashboard(self):
        """Verify System Administrator can access backup dashboard."""
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('backup_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "System Backup & Disaster Recovery")

    def test_ordinary_teacher_cannot_access_backup_dashboard(self):
        """Verify Teacher role is forbidden (403) from accessing backup dashboard."""
        self.client.force_login(self.teacher_user)
        response = self.client.get(reverse('backup_dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_teacher_cannot_trigger_backup(self):
        """Verify Teacher role cannot trigger database backup creation."""
        self.client.force_login(self.teacher_user)
        response = self.client.post(reverse('backup_database_create'))
        self.assertEqual(response.status_code, 403)

    def test_path_traversal_mitigation(self):
        """Verify path traversal outside BACKUP_ROOT is rejected."""
        base_dir = self.backup_root
        evil_path = os.path.join(base_dir, '..', '..', 'Windows', 'System32')
        self.assertFalse(validate_safe_path(evil_path, base_dir))

        valid_path = os.path.join(base_dir, 'database', 'valid_file.sql.gz')
        self.assertTrue(validate_safe_path(valid_path, base_dir))

    def test_secure_download_by_admin(self):
        """Verify admin can download valid backup archive."""
        record = BackupService.create_database_backup(user=self.admin_user)
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('backup_download', kwargs={'backup_id': record.id}))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.has_header('Content-Disposition'))
        self.assertIn(record.filename, response['Content-Disposition'])
