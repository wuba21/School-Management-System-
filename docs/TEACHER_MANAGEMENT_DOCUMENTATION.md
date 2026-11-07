# Teacher Management System Documentation
**Project:** Smart School Management and Academic Information System (SSMS)  
**Location:** Majang Zone Secondary School, Gambella Region, Ethiopia  
**Module:** Step 9 — Teacher Management System  
**Date:** November 2026  

---

## 1. Module Overview
The Teacher Management System provides a secure, role-restricted, and comprehensive faculty administration module for secondary schools (Grades 9–12). It manages the full lifecycle of teachers—from onboarding and atomic ID generation, to classroom and subject allocations, workload analytics, soft-delete status transitions, and granular audit trail logging.

---

## 2. Architecture & Data Model

### 2.1 Teacher Entity (`teachers.Teacher`)
The `Teacher` model maintains complete demographic, professional, and employment state:
- **`employee_id`**: Unique employee / payroll identification number (e.g. `EMP/2026/0001`).
- **Ethiopian Naming Convention**: Three-part naming (`first_name`, `father_name`, `grandfather_name`).
- **Demographics**: `gender` (`M`/`F`), optional `date_of_birth` (validated $\ge 18$ years of age).
- **Contact Details**: `phone_number`, `email`, `address`.
- **Professional Details**: `qualification` (e.g. B.Ed in Mathematics, M.Sc in Physics), `specialization` (e.g. Mathematics).
- **Employment State**: `joining_date`, `employment_status` (`ACTIVE`, `INACTIVE`, `ON_LEAVE`, `TRANSFERRED`, `RETIRED`), `is_active` boolean flag.
- **User Account Linkage**: `user` field links `OneToOne` with `accounts.User` (`on_delete=models.SET_NULL, null=True, blank=True`). Removing a user login never deletes the teacher's historical academic records.
- **Photograph**: `photo` stored via cryptographically randomized UUID filenames in `media/teachers/photos/`.

### 2.2 Teacher Assignment Entity (`teachers.TeacherAssignment`)
Allocates a teacher to teach a specific Subject in a specific Class Offering:
- **`teacher`**: Foreign key to `Teacher`.
- **`class_offering`**: Foreign key to `academics.ClassOffering` (links Grade, Section, Stream, Academic Year).
- **`subject`**: Foreign key to `academics.Subject`.
- **`academic_year`**: Foreign key to `academics.AcademicYear` (auto-synchronized with class offering).
- **`is_primary`**: Boolean flag indicating primary course instructor vs laboratory/assistant instructor.
- **`assigned_at`**: Timestamp of allocation.
- **`notes`**: Optional schedule details (e.g. "Mon/Wed Period 2").
- **Constraints**: `UniqueConstraint(fields=['teacher', 'class_offering', 'subject'], name='unique_teacher_class_subject')` prevents duplicate assignment of the same teacher to the same subject in the same class.

---

## 3. Key Services & Features

### 3.1 Teacher ID Generation (`TeacherIDService`)
- **Format:** `EMP/{YEAR}/{SEQUENCE}` (e.g. `EMP/2026/0001`), configurable via `settings.TEACHER_ID_PREFIX`.
- **Race Condition Prevention:** Wrapped in database transactions (`transaction.atomic()`). Inspects existing sequence numbers for the current year and safely increments next sequence.
- **Manual Override:** Authorizing staff can enter existing regional payroll numbers (e.g. `EMP-1001` or `EMP-GOV-8821`), with format and uniqueness validation.

### 3.2 Secure Photo Uploads (`FileUploadSecurityService`)
- Maximum file size: 2 Megabytes.
- Allowed file extensions: `.jpg`, `.jpeg`, `.png`, `.webp`.
- **Pillow Binary Header Inspection**: Files are inspected with `Image.open().verify()` to prevent spoofed scripts or executable payloads from being uploaded under image extensions.
- Storage uses UUID4 filenames to eliminate path traversal and directory tampering.

### 3.3 Teaching Allocation Workflow (`TeacherService`)
- **Subject & Class Assignment**: Assigns faculty to classroom sections for active academic years.
- **Academic Year Guard**: Assignments are strictly rejected if attempted for closed academic years (`is_closed=True`).
- **Duplicate Prevention**: Cross-checks existing assignments to ensure duplicate instructor allocations are prevented.

### 3.4 Soft Status Lifecycle Management
- Supports statuses: `ACTIVE`, `INACTIVE`, `ON_LEAVE`, `TRANSFERRED`, `RETIRED`.
- Mandatory administrative remarks required for every status change.
- **Zero Data Loss Guarantee**: Inactive or departed teachers are soft-deactivated; historical teaching assignments, attendance records, and student grades are permanently preserved.

---

## 4. Role-Based Access Control (RBAC)

| Action / View | URL | Principal | Registrar | Teacher | System Admin |
|---|---|:---:|:---:|:---:|:---:|
| Faculty Directory | `/teachers/` | View Only | View & Manage | View Only | View & Manage |
| Register Teacher | `/teachers/register/` | 403 Forbidden | **Allowed** | 403 Forbidden | **Allowed** |
| Teacher Profile | `/teachers/<id>/` | View All | View All | **Own Profile Only** | View All |
| My Profile Shortcut | `/teachers/my-profile/` | — | — | **Allowed** | — |
| Edit Teacher | `/teachers/<id>/edit/` | 403 Forbidden | **Allowed** | 403 Forbidden | **Allowed** |
| Update Status | `/teachers/<id>/status/` | 403 Forbidden | **Allowed** | 403 Forbidden | **Allowed** |
| Assign Class & Subject | `/teachers/<id>/assign/` | 403 Forbidden | **Allowed** | 403 Forbidden | **Allowed** |
| Remove Assignment | `/teachers/assignment/<id>/delete/` | 403 Forbidden | **Allowed** | 403 Forbidden | **Allowed** |

---

## 5. Audit Logging Trail
All teacher management actions record structured immutable logs to `core.AuditLog`:
- **Action types**: `CREATE`, `UPDATE`, `DELETE`.
- **Captured fields**: Actor username, client IP address, timestamp, record ID (Teacher Employee ID), and JSON diff containing changed values.

---

## 6. Automated Test Suite Results
Run command: `python manage.py test teachers`

```text
Ran 13 tests in 347.850s

OK
Destroying test database for alias 'default' ('file:memorydb_default?mode=memory&cache=shared')...
System check identified no issues (0 silenced).
```

### Verified Test Cases:
1. `test_teacher_registration_by_registrar`: Auto ID generation, model creation, and audit logging.
2. `test_custom_teacher_id_accepted`: Registration with manual legacy/government payroll ID.
3. `test_duplicate_teacher_id_rejected`: Server-side rejection of duplicate employee IDs.
4. `test_teacher_profile_view`: Complete rendering of personal, professional, and demographic info.
5. `test_teacher_update_by_registrar`: Profile updates and structured audit log diff recording.
6. `test_class_and_subject_assignment`: Teaching allocation linking class offering, subject, and academic year.
7. `test_duplicate_assignment_prevented`: Rejection of duplicate subject/class allocations.
8. `test_assignment_to_closed_academic_year_rejected`: Business constraint enforcement preventing assignments in closed years.
9. `test_teacher_search_and_filter`: Search by name/ID and filtering by specialization and employment status.
10. `test_file_upload_security`: Validates genuine photos and rejects spoofed executable files.
11. `test_teacher_status_lifecycle_preserves_records`: Transitions to `ON_LEAVE` while preserving assignments.
12. `test_role_based_permissions`: Enforces boundaries between Principal, Registrar, Teacher, and Guest.
13. `test_teacher_my_profile_redirect`: Dedicated view for logged-in teachers to inspect their own workload.
