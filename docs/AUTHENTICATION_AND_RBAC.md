# Authentication and Role-Based Access Control (RBAC) Documentation

**Project:** Smart School Management and Academic Information System (SSMS)  
**Location:** Majang Zone, Gambella Region, Ethiopia  
**Phase:** Step 6 Implementation  

---

## 1. Overview & Architecture

The system utilizes Django's native authentication framework (`django.contrib.auth`), anchored by the custom `accounts.User` model (inheriting from `AbstractUser`) and the `accounts.Role` model.

### Key Tenets
1. **No External Internet Dependency:** Authentication, password hashing, and session management are entirely local to the school's LAN server.
2. **Server-Side Security:** URL routing and HTTP methods are secured via custom decorators (`accounts/decorators.py`). Bypassing client UI does not permit access.
3. **Principle of Least Privilege:** Users only access modules necessary for their institutional role.

---

## 2. User Roles & Permission Matrix

| Role Code | Role Name | Permitted Capabilities | Restricted Capabilities |
| :--- | :--- | :--- | :--- |
| **`PRINCIPAL`** | School Principal | View school-wide dashboard, student/teacher rosters, academic reports, attendance reports, review exam results, review promotions. | Cannot edit mark entries directly, cannot alter system settings, cannot create system users. |
| **`REGISTRAR`** | Registrar | Manage student registrations, enrollments, sections, records, and generate report cards and transcripts. | Cannot alter system users/roles, cannot override final principal promotions. |
| **`TEACHER`** | Teacher | View assigned classes & subjects, record attendance for assigned classes, input examination marks for assigned subjects. | Cannot view registrar records of all students, cannot access system settings, cannot manage users. |
| **`ADMIN`** | System Administrator | Create and manage user accounts, assign roles, activate/deactivate accounts, reset staff passwords, inspect security audit logs. | Cannot manipulate academic grades without audit trail. |

---

## 3. Authentication Workflows

### 3.1 Login Workflow
- Form accepts **Username** and **Password** (PBKDF2 SHA-256).
- Checks whether `is_active` is True and `is_approved` is True.
- Logs successful and failed attempts to `core.models.AuditLog`.
- Supports "Remember this terminal" for staff workstations (14 days session vs session-close).

### 3.2 Logout Workflow
- Clears session state and auth tokens.
- Records logout timestamp in `AuditLog`.
- Safely redirects to `/login/`.

### 3.3 Password Change & LAN Password Reset
- **Self-Service:** Authenticated staff can change their own password via `/profile/password/` (requires current password).
- **Offline Administrative Reset:** Because internet/SMTP is unavailable on the local LAN, System Administrators can reset a staff member's password securely via `/users/<id>/reset-password/` and convey it in person.

---

## 4. Security Controls & Decorators

Decorators defined in `accounts/decorators.py`:
- `@any_authenticated_role_required`: Requires active user with an assigned role.
- `@principal_required`: Restricts to School Principal.
- `@registrar_required`: Restricts to Registrar.
- `@teacher_required`: Restricts to Teacher.
- `@sysadmin_required`: Restricts to System Administrator.
- `@management_staff_required`: Permitted for Principal, Registrar, or Administrator.
- `@principal_or_registrar_required`: Permitted for Principal or Registrar.

Unauthorized access raises `django.core.exceptions.PermissionDenied` which triggers the custom `403 Access Denied` view (`templates/accounts/403.html`).

---

## 5. Automated Test Verification

Automated test suite in `accounts/tests.py` verifies:
1. Valid login with session initialization.
2. Invalid login rejection with security error.
3. Logout clearing session.
4. Protected view redirection.
5. Principal access and boundary restrictions.
6. Registrar access and boundary restrictions.
7. Teacher access and boundary restrictions.
8. System administrator access.
9. Unauthorized access 403 handling.
10. Deactivated user rejection.
