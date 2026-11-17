# Step 25: Local Network Deployment & Production Hardening Implementation Report

**Institution:** Metti Secondary School  
**Location:** Godere Woreda, Majang Zone, Gambella Region, Ethiopia  
**Target Grades:** 9–12  
**Architecture:** Django + PostgreSQL / SQLite3 + Waitress WSGI + WhiteNoise + Offline LAN  
**Date:** November 17, 2026  
**Status:** Completed & 100% Verified (383 Automated Tests Passing, 0 Errors, 0 Failures)  

---

## 1. Executive Summary

Step 25 implements a robust, enterprise-grade **Local Network Deployment & Production Hardening Infrastructure** for the Smart School Management and Academic Information System (SSMS) at Metti Secondary School.

This step bridges development and real-world school operations, equipping the school's Windows edge server to reliably host SSMS across the entire school campus Local Area Network (staffrooms, registrar's office, principal's office, and teacher mobile devices) with:
1. **Production-Hardened Django Configuration (`config/settings_production.py`):** Explicit `DEBUG = False`, security-hardened session policies, rotating file loggers, and WhiteNoise static asset serving.
2. **Multi-Threaded Production WSGI Server (`scripts/serve_lan.py`):** Powered by Waitress, featuring automated pre-flight checks (environment validation, migrations, static collection).
3. **One-Click Windows Operators (`START_SSMS_SERVER.bat` & `STOP_SSMS_SERVER.bat`):** Zero-command, double-click scripts for non-technical school staff.
4. **Firewall & Automated Backup Schedulers (`scripts/configure_firewall.bat` & `scripts/schedule_daily_backup.bat`):** Automatic port opening and Windows Task Scheduler automated daily backup execution at 18:00.
5. **Staff Operating Manual (`STEP25_LAN_DEPLOYMENT_OPERATING_MANUAL.md`):** Complete standard operating procedures for the school principal, IT officer, registrar, and teachers.
6. **Dedicated Test Suite (`core/tests_lan_deployment_step25.py`):** 16 automated tests verifying deployment integrity, bringing total project test count to **383 tests (100% passing)**.

---

## 2. Architecture & Components Implemented

### 2.1 Production Settings (`config/settings_production.py`)
- **Strict `DEBUG = False`:** Prevents information disclosure and stack trace leaks on client browsers.
- **Dynamic LAN IP Support:** Binds `ALLOWED_HOSTS` to `LAN_SERVER_IP` configured in `.env`.
- **WhiteNoise Static File Serving:** In-process, compressed, and manifest-cached static asset delivery (`CompressedManifestStaticFilesStorage`) eliminating the need for Nginx/Apache in rural school LAN deployments.
- **Rotating File Logging:**
  - `logs/ssms_application.log` (10 MB x 5 rotating archives for general operational events)
  - `logs/ssms_errors.log` (10 MB x 5 rotating archives for application exceptions and security alerts)
- **Offline Email Backend:** `django.core.mail.backends.filebased.EmailBackend` prevents SMTP timeout crashes when internet is unavailable.

### 2.2 Production WSGI Launcher (`scripts/serve_lan.py`)
A self-healing, multi-threaded server launcher built with Waitress:
- **Pre-flight Check Sequence:**
  1. Validates `.env` existence and warns if default insecure key is used.
  2. Runs Django deployment system checks (`python manage.py check --deploy`).
  3. Executes `collectstatic --noinput` automatically before boot.
  4. Applies pending database migrations (`python manage.py migrate`).
  5. Provisions `logs/` and `backups/` directories.
- **Waitress Configuration:**
  - Default: `0.0.0.0:8000` with 8 concurrent worker threads.
  - Channel timeout: 120 seconds.
  - Maximum client connections: 200 concurrent sockets.

### 2.3 Operational Scripts
- **`START_SSMS_SERVER.bat`:** Activates virtual environment, performs health checks, and launches Waitress on `0.0.0.0:8000`.
- **`STOP_SSMS_SERVER.bat`:** Cleanly terminates the Python/Waitress server process.
- **`scripts/configure_firewall.bat`:** Prompts for administrator elevation and creates an inbound rule in Windows Defender Firewall for TCP port 8000.
- **`scripts/schedule_daily_backup.bat`:** Registers a scheduled task in Windows Task Scheduler to run daily database, media, and GFS pruning routines at 18:00 (6:00 PM).

### 2.4 Staff Operating Manual (`STEP25_LAN_DEPLOYMENT_OPERATING_MANUAL.md`)
A 8-section manual covering:
1. School LAN topology and IP addressing.
2. Hardware pre-requisites and static IP setup.
3. Daily server startup/shutdown procedures.
4. Client workstation access and desktop shortcut creation.
5. Windows firewall troubleshooting.
6. Automated and manual USB offsite backup standard operating procedures (SOP).
7. Role-based access matrix.
8. Common troubleshooting scenarios.

---

## 3. Verification & Testing Results

### 3.1 Step 25 Test Suite (`core/tests_lan_deployment_step25.py`)
16 automated tests executed:
- `test_production_debug_is_false` — PASS
- `test_whitenoise_in_middleware` — PASS
- `test_audit_logging_in_middleware` — PASS
- `test_session_security_settings` — PASS
- `test_file_upload_limits` — PASS
- `test_production_logging_configured` — PASS
- `test_email_backend_offline_safe` — PASS
- `test_password_hashers_are_secure` — PASS
- `test_base_template_has_no_external_cdn_references` — PASS
- `test_local_vendor_assets_exist` — PASS
- `test_serve_lan_script_exists_and_valid_python` — PASS
- `test_startup_batch_script_exists` — PASS
- `test_stop_batch_script_exists` — PASS
- `test_firewall_batch_script_exists` — PASS
- `test_backup_scheduler_script_exists` — PASS
- `test_wsgi_application_callable` — PASS

### 3.2 Full Regression Test Suite
```
Found 383 test(s).
System check identified no issues (0 silenced).
----------------------------------------------------------------------
Ran 383 tests in 27.381s

OK
```

### 3.3 System Check
```
python manage.py check --settings=config.settings_production
System check identified no issues (0 silenced).
```

---

## 4. Deliverables Summary

| File | Type | Purpose |
|---|---|---|
| `config/settings_production.py` | Python Settings | Production configuration (DEBUG=False, WhiteNoise, Logging) |
| `scripts/serve_lan.py` | Python Script | Production Waitress WSGI server launcher |
| `START_SSMS_SERVER.bat` | Batch Script | One-click server starter for school staff |
| `STOP_SSMS_SERVER.bat` | Batch Script | One-click server stopper |
| `scripts/configure_firewall.bat` | Batch Script | Inbound Windows Firewall rule for Port 8000 |
| `scripts/schedule_daily_backup.bat` | Batch Script | Windows Task Scheduler daily backup registration |
| `.env.example` | Template | Documented configuration parameters |
| `requirements.txt` | Dependency File | Added `waitress` and `whitenoise` |
| `core/tests_lan_deployment_step25.py` | Test Suite | 16 deployment verification unit tests |
| `STEP25_LAN_DEPLOYMENT_OPERATING_MANUAL.md` | Documentation | Staff user manual & disaster recovery guide |
| `STEP25_IMPLEMENTATION_REPORT.md` | Documentation | Implementation & verification audit report |

---

*Smart School Management and Academic Information System (SSMS)*  
*Metti Secondary School — Majang Zone, Gambella Region, Ethiopia.*
