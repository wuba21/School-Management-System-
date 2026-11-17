# Step 23: Student Transfer and Leaving Certificate Management Implementation Report

**Institution:** Metti Secondary School  
**Location:** Godere Woreda, Majang Zone, Gambella Region, Ethiopia  
**Target Grades:** 9–12  
**Backend:** Django & PostgreSQL / SQLite3 (Offline Local LAN Deployment)  
**Date:** November 17, 2026  
**Status:** Completed & 100% Verified (303 Automated Tests Passing, 0 Errors, 0 Failures)

---

## 1. Executive Summary

Step 23 delivers a production-grade, secure, and offline-first **Student Transfer and Leaving Certificate Management Module** for Metti Secondary School. The module supports both:
1. **Student Transfer Certificates (TC):** For students moving to another secondary school (e.g. within Gambella Region, Oromia, SNNPR, or other regions of Ethiopia), capturing the destination school name, official transfer reason, effective departure date, and preserving complete longitudinal academic standing.
2. **Student Leaving Certificates (LC):** For students officially completing Grade 12 or withdrawing from the institution, capturing verified academic standing, conduct ratings, and approved departure reasons.

The system enforces a strict multi-level approval state machine (`DRAFT` → `SUBMITTED` → `APPROVED` → `ISSUED`), prevents duplicate active requests, enforces institutional RBAC, formats dates in dual Gregorian and Ethiopian calendar notations, compiles print-ready A4 English-only PDF certificates via ReportLab, and includes an internal staff verification portal with zero unauthenticated PII leakage.

---

## 2. Architecture & Data Modeling

### 2.1 Data Modeling (`StudentCertificate` in `students/models.py`)
- **Foreign Key Integrations:** Fully integrates with existing `Student`, `StudentEnrollment`, `AcademicYear`, and `Grade` models without creating a disconnected or duplicate student database.
- **Unique Constraint:** `unique_active_certificate_per_student_type_year` ensures that a student cannot have multiple concurrent active certificates (`DRAFT`, `SUBMITTED`, `APPROVED`, `ISSUED`) for the same certificate type in a given academic year.
- **Longitudinal Record Preservation:** Issuing a certificate updates the student's master status to `TRANSFERRED`, `WITHDRAWN`, or `GRADUATED`, while strictly preserving all historical enrollments, attendance entries, examination marks, and report cards.

### 2.2 Institutional Sequential Reference Numbering
Sequential institutional reference numbers are generated per certificate type and academic year:
- **Transfer Certificates:** `MSS-TC-{YEAR}-{SEQ:04d}` (e.g. `MSS-TC-2026-0001`)
- **Leaving Certificates:** `MSS-LC-{YEAR}-{SEQ:04d}` (e.g. `MSS-LC-2026-0001`)

### 2.3 Approval Workflow State Machine
```
[DRAFT]  ──(Submit)──>  [SUBMITTED]  ──(Approve: Principal/Admin)──>  [APPROVED]  ──(Issue)──>  [ISSUED]
                           │                                              │
                           ├──(Reject: Principal/Admin)─> [REJECTED]       └──(Revoke: with reason)─> [REVOKED]
```
- **Draft Creation:** Prepared by Registrar or Management staff. Auto-populates grade, section, stream, admission date, and academic standing from active or latest student enrollment.
- **Submission:** Forwarded for principal/administrative review (`SUBMITTED`).
- **Principal Review & Approval:** Only School Principals or System Administrators can approve or reject requests. Rejection strictly requires recorded justification.
- **Official Issuance:** Only approved certificates receive sequential institutional reference numbers and official issue dates.
- **Revocation:** Issued or approved certificates can be revoked with mandatory justification, recording the revoking user, timestamp, and audit trail.

### 2.4 English-Only A4 PDF Generation (`CertificateService.export_certificate_pdf`)
- **Format:** Standard A4 Portrait (595.27pt x 841.89pt) matching Ethiopian Ministry of Education institutional standards.
- **Security Watermark:** Unissued or draft certificates display an oblique `"DRAFT / UNAPPROVED RECORD"` watermark to prevent fraudulent physical printing.
- **Visual Design:**
  - Double ornate borders (Navy `#1E3A8A` and Gold `#D97706`).
  - Institutional crest/logo with school name and Ministry of Education header.
  - Distinctive certificate title badge.
  - Official reference number, issue date, and security UUID.
  - Comprehensive particulars table: Full Name, Admission Number, Date of Birth (Dual Calendar), Gender, Admission Date (Dual Calendar), Effective Departure Date (Dual Calendar), Academic Year, Last Attended Grade, Section, Curriculum Stream, Destination School (for transfers), Academic Standing, Conduct, and Institutional Remarks.
  - Formal institutional certification text.
  - Three-column authentication block: Registrar Signature Line, Principal Signature Line, and Official School Stamp Box.

### 2.5 Dual Calendar Date Presentation
All dates on both web previews and PDF certificates are rendered in dual calendar format:
- Example: `Oct 15, 2023 (Tikimt 05, 2016 E.C.)`
- Powered by `core.utils.ethiopian_calendar.EthiopianDate`.

### 2.6 Internal Staff Verification Portal (`/students/certificates/verify/`)
- Accessible only to authenticated staff (`@any_authenticated_role_required`).
- Supports search by Institutional Reference Number (`MSS-TC-...`, `MSS-LC-...`) or Certificate UUID.
- Displays real-time status banner:
  - **Valid & Authentic:** Green banner with full verified student particulars and PDF download shortcut.
  - **Revoked:** Red banner detailing revocation timestamp, reason, and revoking official.
  - **Pending / Unissued:** Warning banner indicating non-final status.
  - **Not Found:** Alert indicating record not found.
- Zero public PII leakage across school LAN.

---

## 3. Route Map & Views

| URL Route | View Name | Permissions | Purpose |
|---|---|---|---|
| `/students/certificates/` | `certificate_hub` | Principal, Registrar, Admin | Management hub with KPI summary cards, filter form, and certificate roster |
| `/students/certificates/create/` | `certificate_create_general` | Principal, Registrar, Admin | Create request with student selector |
| `/students/certificates/create/<student_id>/` | `certificate_create` | Principal, Registrar, Admin | Create request pre-loaded for specific student |
| `/students/certificates/preview/<cert_id>/` | `certificate_preview` | Principal, Registrar, Admin | High-fidelity certificate preview & action workflow modals |
| `/students/certificates/<cert_id>/submit/` | `certificate_submit` | Principal, Registrar, Admin | Transition DRAFT → SUBMITTED |
| `/students/certificates/<cert_id>/approve/` | `certificate_approve` | Principal, Admin Only | Principal approval transition |
| `/students/certificates/<cert_id>/reject/` | `certificate_reject` | Principal, Admin Only | Principal rejection with justification |
| `/students/certificates/<cert_id>/issue/` | `certificate_issue` | Principal, Registrar, Admin | Official issuance and number assignment |
| `/students/certificates/<cert_id>/revoke/` | `certificate_revoke` | Principal, Registrar, Admin | Revocation with mandatory reason |
| `/students/certificates/<cert_id>/pdf/` | `certificate_pdf` | Any Authenticated Staff | A4 English-only PDF download |
| `/students/certificates/verify/` | `certificate_verify` | Any Authenticated Staff | Internal search & verification portal |

---

## 4. School-Specific Information Awaiting Principal Confirmation

In accordance with institutional guidelines, unverified school data has not been hardcoded into the system. The following items are designed with configurable fallbacks and require confirmation by the School Principal:

1. **Official School Stamp & Seal Design:** The dimensions and physical placement of the rubber stamp area on physical certificates. (Currently configured as standard 120pt x 90pt rectangular box).
2. **Authorized Signatories:** Exact designation of certificate signatories (e.g. "School Principal" vs. "Academic Vice Principal" / "Record Officer" vs. "Head Registrar").
3. **Institutional Contact Details on Certificates:** Official postal box, telephone number, and institutional email for Metti Secondary School.
4. **Approval Delegation Rules:** Confirmation whether Registrars may issue approved certificates independently or whether the Principal must authorize both approval and physical release.
5. **Leaving Certificate Eligibility Criteria:** Formal school policy on whether Grade 9–11 withdrawing students receive a Leaving Certificate or an Official Transfer Certificate.

---

## 5. Files Created & Modified

### Files Modified:
- `students/models.py`: Added `StudentCertificate` model with UUID, workflow status choices, dual calendar dates, and unique active certificate constraint.
- `students/services.py`: Implemented `CertificateService` with sequential reference numbering, approval/rejection state transitions, audit logging, and ReportLab A4 PDF generator.
- `students/views.py`: Added `certificate_hub_view`, `certificate_create_view`, `certificate_preview_view`, `certificate_submit_view`, `certificate_approve_view`, `certificate_reject_view`, `certificate_issue_view`, `certificate_revoke_view`, `certificate_pdf_view`, and `certificate_verify_view`.
- `students/urls.py`: Wired certificate routes into the `students` namespace.
- `templates/base.html`: Added "Certificates (TC/LC)" navigation destination under Management for Admin and Principal.

### Files Created:
- `students/migrations/0004_studentcertificate_and_more.py`: Database migration for `StudentCertificate`.
- `templates/students/certificate_hub.html`: Management hub with KPI cards, search filters, and certificate table.
- `templates/students/certificate_form.html`: Certificate request registration form.
- `templates/students/certificate_preview.html`: Certificate preview with approval, rejection, issuance, and revocation modals.
- `templates/students/certificate_verify.html`: Internal staff verification search portal.
- `students/tests_certificates_step23.py`: Automated test suite with 18 comprehensive tests.
- `STEP23_IMPLEMENTATION_REPORT.md`: This comprehensive implementation report.

---

## 6. Automated Verification Results

### Dedicated Step 23 Test Suite:
```
python manage.py test students.tests_certificates_step23 --verbosity=1
```
**Results:**
```
Found 18 test(s).
..................
----------------------------------------------------------------------
Ran 18 tests in 1.340s

OK
```
- `test_cannot_issue_unapproved_certificate`: PASSED ✅
- `test_certificate_hub_view`: PASSED ✅
- `test_certificate_preview_view`: PASSED ✅
- `test_create_leaving_certificate_request`: PASSED ✅
- `test_create_transfer_certificate_request_auto_population`: PASSED ✅
- `test_destination_school_required_for_transfer_certificate`: PASSED ✅
- `test_dual_calendar_date_formatting`: PASSED ✅
- `test_duplicate_active_certificate_prevention`: PASSED ✅
- `test_full_approval_workflow_lifecycle`: PASSED ✅
- `test_pdf_generation_for_draft_and_issued_certificates`: PASSED ✅
- `test_principal_can_approve_via_http`: PASSED ✅
- `test_rejection_workflow_with_mandatory_justification`: PASSED ✅
- `test_revocation_workflow_with_mandatory_justification`: PASSED ✅
- `test_sequential_reference_number_generation`: PASSED ✅
- `test_teacher_cannot_approve_or_reject_certificates`: PASSED ✅
- `test_verification_portal_displays_revocation_notice`: PASSED ✅
- `test_verification_portal_requires_authentication`: PASSED ✅
- `test_verification_portal_search_by_reference_number_and_uuid`: PASSED ✅

### Full Project Regression Suite:
```
python manage.py test --verbosity=1
```
**Results:**
```
Found 303 test(s).
....................................................................
----------------------------------------------------------------------
Ran 303 tests in 37.436s

OK (0 failures, 0 errors across all 303 unit tests)
```

### System Configuration & Migration Checks:
- `python manage.py check`: Identified 0 issues. ✅
- `python manage.py makemigrations --check --dry-run`: No changes detected. ✅

---

## 7. Conclusion

Step 23: Student Transfer and Leaving Certificate Management is complete, fully verified, secure, and operational on the local LAN. All previous modules and existing dashboards remain completely intact.
