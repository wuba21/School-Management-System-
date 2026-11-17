# SYSTEM BACKUP, RESTORE, AND DISASTER RECOVERY MANUAL
**Project:** Smart School Management and Academic Information System (SSMS)  
**Deployment Context:** Offline-first Local Area Network (LAN) Edge Server, Majang Zone, Gambella Region, Ethiopia  
**Target Institution:** Secondary School (Grades 9–12, 1,000–2,000 Students)  
**Security & Operational Clearance:** System Administrators (IT Personnel & School Director)  

---

## 1. ARCHITECTURAL OVERVIEW

The SSMS Backup and Disaster Recovery subsystem is designed specifically for schools operating in remote environments with unstable electrical grids and zero reliance on cloud services.

### Core Architectural Guarantees:
* **Zero Cloud Dependency:** Backups are created, verified, compressed, and retained 100% locally on the school server and exported to external offline USB media.
* **Isolated File System Hierarchy:** Backup archives are stored in `backups/` outside the web-accessible `static/` and `media/` directories, preventing any direct HTTP access.
* **Cryptographic Integrity Verification:** Every backup archive is automatically hashed using SHA-256 upon creation. Archive headers and checksums are verified before any restoration or export.
* **Grandfather-Father-Son (GFS) Rotation:** Prevents local storage exhaustion by keeping a balanced timeline of daily, weekly, and monthly snapshots while strictly enforcing the safety invariant: **Never delete the only valid backup**.
* **Role-Based Isolation:** Non-administrative accounts (teachers, registrars, students) are completely barred (`HTTP 403 Forbidden`) from viewing, triggering, or downloading backup archives.
* **Production Guardrails:** Overwriting the active production database cannot be triggered with a single accidental web click; restoration requires authenticated CLI execution with explicit confirmation (`--confirm`).

---

## 2. DIRECTORY STRUCTURE AND STORAGE LAYOUT

```
d:\SmartSchoolManagementSystem\
├── backups\                      <-- Root backup directory (Restricted, Git-ignored)
│   ├── database\                 <-- PostgreSQL & SQLite compressed dumps (.sql.gz / .dump)
│   │   └── ssms_db_backup_YYYYMMDD_HHMMSS.sql.gz
│   └── media\                    <-- Student photos, documents tar.gz archives
│       └── ssms_media_backup_YYYYMMDD_HHMMSS.tar.gz
├── media\                        <-- Active user uploads (student portraits, report cards)
├── static\                       <-- Self-contained offline assets
└── config\settings.py            <-- Backup parameters and retention policies
```

### Environment Settings (`config/settings.py` / `.env`):
* `BACKUP_ROOT = BASE_DIR / 'backups'`
* `BACKUP_DB_DIR = BACKUP_ROOT / 'database'`
* `BACKUP_MEDIA_DIR = BACKUP_ROOT / 'media'`
* `BACKUP_RETENTION_DAILY = 7` (Retains the latest snapshot for 7 distinct calendar days)
* `BACKUP_RETENTION_WEEKLY = 4` (Retains the latest snapshot for 4 distinct calendar weeks)
* `BACKUP_RETENTION_MONTHLY = 12` (Retains the latest snapshot for 12 distinct calendar months)
* `PG_DUMP_PATH = 'pg_dump'` (Path to PostgreSQL dump binary)
* `PG_RESTORE_PATH = 'pg_restore'` (Path to PostgreSQL restore binary)
* `PSQL_PATH = 'psql'` (Path to psql command-line client)

---

## 3. COMMAND LINE INTERFACE (CLI) OPERATIONS

### 3.1 Database Backup
Generates a timestamped, gzip-compressed snapshot of the database.
```bash
# Standard compressed backup
python manage.py backup_database

# Backup with administrative notes
python manage.py backup_database --notes "Pre-term examination results backup"

# Backup and automatically prune expired archives in one command
python manage.py backup_database --prune

# Uncompressed backup (for immediate SQL inspection)
python manage.py backup_database --no-compress
```

### 3.2 Media & Document Archive Backup
Compresses all student portraits, teacher documents, and generated transcripts in `media/` preserving folder hierarchy:
```bash
python manage.py backup_media

# Media backup with automatic retention pruning
python manage.py backup_media --prune
```

### 3.3 Retention Pruning (GFS Rotation)
Safely prunes old archives according to the 7-day / 4-week / 12-month policy:
```bash
# Preview what would be pruned without deleting files
python manage.py prune_backups --dry-run

# Live pruning for both database and media backups
python manage.py prune_backups

# Prune only database backups
python manage.py prune_backups --type DATABASE
```

### 3.4 External USB Export
Exports a verified archive to an attached USB flash drive:
```bash
# By database record ID
python manage.py export_backup --file 1 --destination "E:\SchoolBackups"

# By exact filename
python manage.py export_backup --file "ssms_db_backup_20261108_150247.sqlite3.gz" --destination "/media/usb/backups"
```

---

## 4. ADMINISTRATIVE WEB DASHBOARD

The backup system provides a dedicated web interface at `/backups/` for IT Administrators and School Leadership (`@sysadmin_required`):

1. **KPI Status Cards:**
   * Total Database Backups and timestamp of the latest backup.
   * Total Media Backups and timestamp of the latest archive.
   * Total disk storage consumed in the `backups/` directory.
   * Active GFS retention status badges.
2. **One-Click Actions:**
   * `Backup Database Now`: Triggers instant compressed backup.
   * `Backup Media & Documents`: Triggers instant media directory archiving.
   * `Prune Expired`: Safely applies GFS cleanup with confirmation modal.
3. **Archive Catalog Table:**
   * Lists all archives with status badge, file size in human-readable units (KB/MB/GB), SHA-256 preview, and creator.
   * **Direct Secure Download:** Streams the archive file over HTTPS/HTTP with path traversal verification.
   * **Verify Integrity:** Tests archive decompression and validates SHA-256 on demand.
   * **Export to USB Modal:** Allows the administrator to enter an external drive directory (e.g. `E:\SchoolBackups` or `F:\`) and copy the file with automated post-copy verification.

---

## 5. DISASTER RECOVERY & RESTORATION PROCEDURE

> [!WARNING]
> Database restoration replaces existing database tables with historical records. To protect school data, never run a restoration without verifying the backup file on a secondary/test database first.

### Step-by-Step Recovery Workflow:

#### Step 1: Secure the Server & Obtain Verified Archive
If the server encountered a power cut, disk error, or operating system failure:
1. Locate the latest verified backup from the server's `backups/database/` directory or insert the primary USB backup flash drive into the server.
2. Verify archive integrity using SHA-256:
   ```bash
   # Windows PowerShell
   Get-FileHash -Algorithm SHA256 "D:\SmartSchoolManagementSystem\backups\database\ssms_db_backup_YYYYMMDD_HHMMSS.sql.gz"
   ```

#### Step 2: Test Restoration on a Staging/Test Database (Mandatory)
Before touching the live database, restore the archive into a test database to confirm that the file is not truncated or corrupted:
```bash
# PostgreSQL
createdb -U postgres smart_school_test_restore
python manage.py restore_database --file "ssms_db_backup_YYYYMMDD_HHMMSS.sql.gz" --target-db "smart_school_test_restore" --confirm

# SQLite (Development/Edge Test)
python manage.py restore_database --file "ssms_db_backup_YYYYMMDD_HHMMSS.sqlite3.gz" --target-db "test_restore.sqlite3" --confirm
```

#### Step 3: Execute Production Database Restoration
Once verified, execute production recovery:
```bash
python manage.py restore_database --file "ssms_db_backup_YYYYMMDD_HHMMSS.sql.gz" --confirm
```

#### Step 4: Restore Media & Document Attachments
To restore student portraits and documents from a media archive:
```bash
# Windows PowerShell
tar -xzf "backups/media/ssms_media_backup_YYYYMMDD_HHMMSS.tar.gz" -C "media/"

# Linux Bash
tar -xzf backups/media/ssms_media_backup_YYYYMMDD_HHMMSS.tar.gz -C media/
```

#### Step 5: System Verification
1. Run `python manage.py check`.
2. Inspect the dashboard at `http://<SERVER_LAN_IP>:8000/dashboard/`.
3. Check student enrollment counts, teacher assignments, and recent exam results.
4. Review `/audit/` to confirm the restoration event was logged.

---

## 6. EXTERNAL USB BACKUP PROTOCOL (DAILY SOP)

In a rural environment like Majang Zone, edge servers face significant hardware risks (lightning surges, dust, physical theft). A daily physical USB routine is vital:

### Recommended Hardware Setup:
* Two high-durability USB 3.0 flash drives (labeled **USB-A (Even Days)** and **USB-B (Odd Days)**).
* Size: 32 GB or 64 GB each (sufficient for multiple years of compressed school data).

### Daily Routine (End of School Day - 4:30 PM):
1. Insert **USB-A** into the school server.
2. Log into the SSMS administrative panel at `http://192.168.1.100:8000/backups/`.
3. Click **Backup Database Now**, then **Backup Media Now**.
4. In the table, click the **Export to USB** button next to each new archive.
5. Enter the USB drive letter (e.g. `E:\SchoolBackups`).
6. Click **Confirm & Export Copy**.
7. Confirm that the success alert indicates `SHA-256 integrity verified`.
8. Safely eject the USB drive.
9. Hand the drive to the School Principal or IT Lead to lock in the school's fireproof safe.

---

## 7. SECURITY & THREAT MITIGATION

1. **Path Traversal Protection:** All download and export endpoints validate paths using `os.path.commonpath([BACKUP_ROOT, requested_path]) == BACKUP_ROOT`. Injections like `../../Windows/System32` or `../../etc/shadow` are rejected immediately.
2. **Credential Masking:** Database passwords are never passed as command-line arguments (where they would be visible via `ps aux` or Task Manager). Instead, `PGPASSWORD` is injected into isolated subprocess environments. Any error traces scrub password strings before writing to logs.
3. **Immutable Audit Trail:** All backup operations (`CREATE`, `DELETE/PRUNE`, `DOWNLOAD`, `EXPORT`, `RESTORE`) generate timestamped entries in `core_auditlog` capturing actor username, client LAN IP, and affected archive hashes.

---

## 8. KNOWN LIMITATIONS & CONTINGENCY MEASURES

* **Power Surges during `pg_dump`:** If the server loses power midway through a backup, the incomplete `.sql.gz` file will fail gzip validation. The SSMS service automatically flags incomplete files as `CORRUPTED` and refuses to restore them.
* **Storage Exhaustion:** If the server runs out of disk space, `pg_dump` or `tarfile` will raise an `OSError`. Administrators must run `python manage.py prune_backups` or attach an external drive to free up space.
* **USB Drive Formatting:** USB drives must be formatted with **NTFS** or **exFAT** (FAT32 has a 4 GB single-file size limit which could truncate large future media archives).
