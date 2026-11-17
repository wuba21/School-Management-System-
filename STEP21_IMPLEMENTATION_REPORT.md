# Step 21 Implementation Report: Examination Mark Excel/CSV Import & Export

**System:** Smart School Management and Academic Information System (SSMS)  
**Institution:** Metti Secondary School, Majang Zone, Gambella Region, Ethiopia (Grades 9–12)  
**Environment:** Offline-First Local Area Network (LAN)  
**Document Date:** November 2026  
**Status:** Successfully Completed & Verified (272/272 Tests Passing)

---

## 1. Executive Summary

In compliance with institutional requirements for **Step 21**, an enterprise-grade, offline-capable **Examination Mark Excel and CSV Import and Export Module** has been developed and integrated seamlessly into the SSMS Examination and Result Management architecture.

This module empowers teachers, examination officers, registrars, and school administrators to:
1. Download standardized Excel (`.xlsx`) and CSV (`.csv`) marks entry templates pre-populated with actual active student enrollments.
2. Upload edited spreadsheets through a secure multi-stage pipeline consisting of safe parsing, automated data validation, dry-run previews, and explicit user confirmation.
3. Download granular error reports detailing invalid rows with recommended corrections.
4. Atomically commit validated marks into the database via the existing service layer (`MarksService`) without bypassing verification workflows or creating separate database tables.
5. Filter and export granular examination records into professional OpenPyXL workbooks and RFC-compliant UTF-8 CSV files with byte-order marks (BOM).

---

## 2. Features Implemented

### 2.1 Dynamic Template Generation
- **Actual School Records:** Templates are generated dynamically from active student enrollments in `StudentEnrollment` for the chosen `ExamSubject` and optional `ClassOffering`.
- **Formats Supported:**
  - **Excel (`.xlsx`):** Built via OpenPyXL with institutional header banner (*Metti Secondary School*), exam metadata (Subject, Code, Max Marks, Pass Marks), frozen styled headers, editable highlight styling (`#FEF9C3`) on the "Mark Obtained" column, and auto-adjusted column dimensions.
  - **CSV (`.csv`):** Formatted with UTF-8 BOM (`\ufeff`) ensuring native character encoding and zero corruption when opened in offline Microsoft Excel on Windows.
- **Columns Provided:**
  `Admission Number`, `Student Full Name`, `Grade`, `Section`, `Stream`, `Subject Code`, `Subject Name`, `Examination`, `Max Mark`, `Mark Obtained`, `Is Absent`, `Remarks`.

### 2.2 Secure Multi-Step Import Pipeline
1. **Selection & Upload (`/results/marks/import/`):**
   - User chooses examination subject and uploads file.
   - Teachers are automatically scoped strictly to their assigned classes and subjects.
2. **Server-Side Validation & Dry-Run Evaluation:**
   - File size ceiling: strict 5.0 MB restriction.
   - Extensions restricted strictly to `.xlsx` and `.csv`.
   - OpenPyXL loaded with `data_only=True` and `read_only=True` to prevent formula injection or macro execution.
   - Comprehensive student identity, grade enrollment, duplicate, numeric range, and status checks.
3. **Interactive Validation Preview (`/results/marks/import/preview/`):**
   - KPI metrics: Total Rows, Valid Rows, Invalid Rows, New Records (Create) vs Existing Records (Update).
   - If errors exist: Displays an interactive table of invalid rows and provides a 1-click **Download Error Report (.csv)** button.
   - Valid rows table: Displays current database score vs new score to import, action type badge, and absent flags.
4. **Atomic Commitment (`/results/marks/import/confirm/`):**
   - Explicit confirmation button commits validated rows within `transaction.atomic()`.
   - Records marks using `MarksService.record_bulk_marks` with `status='DRAFT'`.
   - Preserves standard submission and registrar approval workflows (`SUBMITTED` &rarr; `VERIFIED` &rarr; `PUBLISHED`).
   - Automatically writes an event to the security audit trail (`AuditLog`).

### 2.3 Granular Examination Marks Export (`/results/marks/export/`)
- Multi-dimensional filters: Academic Year, Examination cycle, Grade, Section / Class Offering, Stream, Subject.
- Export options: Excel (.xlsx) and CSV (.csv).
- Live counter of matching records prior to download.
- Role-scoped: Teachers can only export marks for their assigned classes; management staff can export school-wide datasets.

---

## 3. Validation Rules Enforced

| Rule | Description | Behavior on Failure |
|---|---|---|
| **Student Existence** | Student admission number must match an existing record in `students.Student`. | Row rejected; flagged with *"Student with admission number was not found in school records."* |
| **Active Cohort Enrollment** | Student must be actively enrolled in the grade/stream of the examination subject for the relevant academic year. | Row rejected; flagged with *"Student exists in SSMS but is not enrolled in Grade X for this examination."* |
| **Duplicate Prevention** | No admission number may appear more than once in the uploaded spreadsheet. | Subsequent row rejected; flagged with *"Duplicate student admission number detected in uploaded file."* |
| **Exam Subject Status** | Examination subject must be open for marks entry (`PENDING` or `RETURNED`). | Entire import blocked if exam subject is `VERIFIED`, `PUBLISHED`, or examination is `CLOSED`. |
| **Locked Mark Overwrites** | Individual student marks already verified or published cannot be overwritten via spreadsheet. | Row rejected; flagged with *"Marks for student are already verified/published and locked against overwriting."* |
| **Numeric Score Type** | Score must be a valid non-negative decimal number. | Row rejected; flagged with *"Invalid numeric score. Value must be a valid number."* |
| **Score Bounds** | Mark must satisfy `0.00 <= score <= exam_subject.max_marks`. | Row rejected if negative or exceeding maximum configured marks. |
| **Absence Handling** | If marked absent (`YES`, `Y`, `TRUE`, `ABS`, `ABSENT`), score is safely recorded as `None` with `is_absent=True`. | Validated and cleanly categorized as `ABSENT`. |
| **Teacher Assignment RBAC** | Teachers can only upload or download templates for subjects they are actively assigned to teach. | `PermissionDenied` (HTTP 403) raised immediately if teacher attempts unauthorized upload. |

---

## 4. Modified & Created Files

| File | Type | Description |
|---|---|---|
| `results/services.py` | Modified | Added `MarksExportImportService` containing `generate_marks_template`, `validate_import_file`, `commit_import_marks`, `generate_error_report`, and `export_examination_marks`. |
| `results/forms.py` | Modified | Added `MarksImportUploadForm` (with 5MB file validation and teacher scoping) and `MarksExportForm`. |
| `results/views.py` | Modified | Implemented `marks_template_download_view`, `marks_import_view`, `marks_import_confirm_view`, `marks_import_error_export_view`, and `marks_export_view`. |
| `results/urls.py` | Modified | Registered routes for template download, import, confirmation, error export, and marks export. |
| `templates/results/marks_import.html` | Created | Import landing page with subject selector, file dropzone, and 1-click template download triggers. |
| `templates/results/marks_import_preview.html` | Created | Dry-run preview dashboard displaying KPI metrics, error tables, error report download, and confirmation button. |
| `templates/results/marks_export.html` | Created | Filterable examination marks export hub with live record count and Excel/CSV download controls. |
| `templates/results/dashboard.html` | Modified | Added "Import Marks" and "Export Records" buttons in Results Hub header and teacher subject action buttons. |
| `templates/results/marks_entry.html` | Modified | Added "Import Excel/CSV" and "Excel Template" quick action buttons. |
| `templates/dashboards/admin_dashboard.html` | Modified | Added "Marks Excel/CSV Import" shortcut in System Administrator Dashboard. |
| `templates/base.html` | Modified | Added sidebar navigation entries for Marks Import and Marks Export across Admin, Principal, Registrar, and Teacher menus. |
| `results/tests_marks_import_export_step21.py` | Created | 14 comprehensive unit and integration tests covering templates, imports, validations, RBAC, locks, exports, rollback, and large files. |

---

## 5. Automated Test Results

### 5.1 System Check
```bash
python manage.py check
# Output: System check identified no issues (0 silenced).
```

### 5.2 Step 21 Test Suite (`results.tests_marks_import_export_step21`)
```text
test_cannot_overwrite_verified_mark ... ok
test_download_error_report ... ok
test_duplicate_student_records_detection ... ok
test_excel_and_csv_export_functionality ... ok
test_invalid_numeric_values_and_negative_scores ... ok
test_invalid_student_id_detection ... ok
test_large_file_size_validation ... ok
test_locked_examination_record_import_blocked ... ok
test_marks_exceeding_maximum_score ... ok
test_template_download_excel_and_csv ... ok
test_transaction_rollback_on_failure ... ok
test_unauthorized_teacher_import_prevented ... ok
test_valid_csv_import_and_commit ... ok
test_valid_excel_import_and_commit ... ok

----------------------------------------------------------------------
Ran 14 tests in 1.359s
OK
```

### 5.3 Full Regression Suite
```text
Ran 272 tests in 17.538s

OK
```
*Result:* **100% PASS** (272/272 tests passing across all SSMS apps with 0 errors and 0 failures).

---

## 6. Security and Offline Operations

- **Strict Role-Based Access Control:** Unauthorized teachers are blocked by HTTP 403 from importing or exporting marks for classes they do not teach.
- **Audit Logging:** Every file import and bulk export event is persisted to `core.AuditLog` with actor user ID, client IP address, target subject, and row count breakdown.
- **Zero External Dependencies:** Built 100% on local Python libraries (`openpyxl`, `csv`, standard library `io`), ensuring total offline functionality across local school LAN environments.
