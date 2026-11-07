# Step 13: Student Promotion and Academic History Management
## Smart School Management and Academic Information System (SSMS)
### Majang Secondary School — Gambella Region, Ethiopia

---

## 1. Overview

The **Student Promotion and Academic History** module automates the end-to-end
promotion lifecycle — from batch preparation, committee review and approval,
atomic enrollment finalization, through graduation certification — while preserving
a permanent, immutable longitudinal academic transcript for every student.

All promotion decisions require **explicit human review and authorization**.
The system never auto-promotes or auto-retains students; it only generates
algorithmic recommendations for authorized staff to accept, adjust, or override.

---

## 2. Application Structure

```
d:/SmartSchoolManagementSystem/
└── promotion/
    ├── __init__.py
    ├── apps.py
    ├── models.py          # PromotionCriteria, PromotionBatch, PromotionRecord,
    │                      #   GraduationRecord, StudentStatusHistory
    ├── services.py        # 6 service classes (assessment, batch, approval,
    │                      #   history, graduation, reports)
    ├── forms.py           # 7 forms
    ├── views.py           # 13 views
    ├── urls.py            # All URL patterns
    ├── admin.py           # 5 admin classes with inlines
    ├── tests.py           # 13 tests (7 model/service + 6 view)
    └── migrations/
        └── 0001_initial.py
```

**Registered in** `config/settings.py` → `INSTALLED_APPS`:
```python
'promotion.apps.PromotionConfig',
```

**URL prefix** (`config/urls.py`):
```python
path('promotion/', include('promotion.urls')),
```

---

## 3. Database Models

### 3.1 `PromotionCriteria`
Configurable school promotion policy thresholds. All criteria are editable by
authorized administrators without code changes.

| Field | Type | Description |
|---|---|---|
| `name` | CharField | Policy name (e.g., "Majang Secondary Standard Policy") |
| `code` | CharField | Short unique code (e.g., "SEC-2026") |
| `minimum_average` | DecimalField | Minimum overall percentage to qualify for promotion |
| `max_failing_subjects` | IntegerField | Maximum number of subjects a student may fail |
| `minimum_attendance_percentage` | DecimalField | Minimum attendance required (nullable — optional rule) |
| `is_default` | BooleanField | Whether this is the active system default |
| `is_active` | BooleanField | Whether this policy is available for selection |
| `description` | TextField | Free-text notes |

### 3.2 `PromotionBatch`
Groups all students of a specific grade and academic year into a single
reviewable promotion cohort.

| Field | Type | Description |
|---|---|---|
| `name` | CharField | Descriptive batch name |
| `academic_year` | FK → AcademicYear | Source year (year being completed) |
| `target_academic_year` | FK → AcademicYear | Destination year |
| `grade` | FK → Grade | Grade being promoted (9, 10, 11, or 12) |
| `promotion_criteria` | FK → PromotionCriteria | Policy applied to this batch |
| `status` | CharField | `DRAFT → SUBMITTED → APPROVED → FINALIZED` (or `REJECTED`) |
| `approved_by` | FK → User | Committee member who approved |
| `approval_date` | DateTimeField | When approval was recorded |
| `approval_remarks` | TextField | Committee comments |
| `finalized_at` | DateTimeField | When finalization was executed |
| `created_by` | FK → User | Staff who prepared the batch |

**Computed properties** (on model):
- `total_candidates` — count of all records
- `promoted_count`, `repeated_count`, `graduated_count`, `pending_count`

**Status transitions:**
```
DRAFT → SUBMITTED → APPROVED → FINALIZED
  ↑                     ↓
  └───────── REJECTED ──┘
```

### 3.3 `PromotionRecord`
One record per student per batch. Stores both the algorithmic recommendation and
the human final decision.

| Field | Type | Description |
|---|---|---|
| `batch` | FK → PromotionBatch | Parent batch |
| `student_enrollment` | FK → StudentEnrollment | Source enrollment |
| `student` | FK → Student | The student |
| `previous_academic_year` | FK → AcademicYear | Source year |
| `next_academic_year` | FK → AcademicYear | Target year |
| `previous_grade` | FK → Grade | Current grade |
| `next_grade` | FK → Grade | Destination grade (null if graduating) |
| `previous_class_offering` | FK → ClassOffering | Current class |
| `next_class_offering` | FK → ClassOffering | Assigned next class (nullable) |
| `recommended_outcome` | CharField | System recommendation |
| `final_outcome` | CharField | Human-confirmed decision |
| `decision_status` | CharField | `PENDING / APPROVED / REJECTED / FINALIZED` |
| `academic_average` | DecimalField | Overall average percentage |
| `total_failing_subjects` | IntegerField | Number of subjects below pass mark |
| `attendance_percentage` | DecimalField | Attendance rate |
| `has_incomplete_results` | BooleanField | Whether results are still missing |
| `remarks` | TextField | Staff notes |
| `new_enrollment` | FK → StudentEnrollment | Created enrollment in target year |
| `is_enrolled_in_next_year` | BooleanField | Whether finalization created a new enrollment |

**Outcome choices:**
`PROMOTED` · `REPEATED` · `GRADUATED` · `TRANSFERRED` · `WITHDRAWN` · `PENDING`

### 3.4 `GraduationRecord`
Official Grade 12 graduation record. Created during batch finalization for
students with `final_outcome == 'GRADUATED'`.

| Field | Type | Description |
|---|---|---|
| `student` | FK → Student | Graduate |
| `academic_year` | FK → AcademicYear | Year of graduation |
| `grade` | FK → Grade | Grade 12 |
| `stream` | FK → Stream | Natural Science / Social Science / etc. |
| `graduation_date` | DateField | Official ceremony date |
| `certificate_number` | CharField | Official certificate number |
| `cumulative_average` | DecimalField | Final cumulative average |
| `status` | CharField | `PENDING / APPROVED / GRADUATED / REVOKED` |
| `approved_by` | FK → User | Principal or authorized official |
| `remarks` | TextField | Any notes |

### 3.5 `StudentStatusHistory`
Permanent audit trail for any student status change outside regular promotion
(transfers, withdrawals, readmissions, suspensions, etc.).

| Field | Type | Description |
|---|---|---|
| `student` | FK → Student | The student |
| `status_type` | CharField | `TRANSFER_OUT / WITHDRAWAL / DROPOUT / SUSPENSION / READMISSION / GRADUATION` |
| `effective_date` | DateField | Date the change took effect |
| `reason` | TextField | Reason for status change |
| `destination_school` | CharField | For transfers — receiving institution |
| `documents_issued` | CharField | e.g., "Clearance Slip #104" |
| `authorized_by` | FK → User | Authorizing staff member |
| `previous_status` | CharField | Student status before |
| `new_status` | CharField | Student status after |

---

## 4. Service Layer

### 4.1 `PromotionAssessmentService`
Evaluates each student's eligibility by analysing:
- Overall average from `StudentResultSummary`
- Number of failing subjects from `Mark` records
- Attendance percentage from `AttendanceRecord` linked via `student_enrollment`

**Method:** `assess_student_eligibility(student_enrollment, criteria=None)`

Returns a dict with:
```python
{
    'academic_average': Decimal,
    'failing_subjects_count': int,
    'attendance_percentage': Decimal,
    'has_incomplete': bool,
    'recommended_outcome': str,  # 'PROMOTED'|'REPEATED'|'GRADUATED'|'PENDING'
    'criteria': PromotionCriteria,
}
```

**Grade 12 rule:** If average ≥ minimum and no failing subjects and no
incomplete results → `GRADUATED`. Otherwise `REPEATED` or `PENDING`.

### 4.2 `PromotionBatchService`
**`create_batch(name, academic_year, target_academic_year, grade, criteria, user, request)`**
- Validates source ≠ target year and target starts after source
- Queries all `ACTIVE` enrollments in the grade
- Calls `assess_student_eligibility` for each student
- Creates `PromotionRecord` entries with recommendations
- Attempts to auto-match class offerings in target year
- Logs the action in `AuditLog`

**`update_record_outcome(record_id, final_outcome, next_class_offering_id, remarks, user, request)`**
- Allows staff to override a student's proposed outcome
- Blocked if batch is already `APPROVED` or `FINALIZED`

### 4.3 `PromotionApprovalService`
**`submit_for_review(batch, user, request)`**  
Moves batch from `DRAFT`/`REJECTED` → `SUBMITTED`.

**`review_batch(batch, decision, reviewer_user, comments, request)`**  
Records `APPROVED` or `REJECTED` committee decision; updates all records.

**`finalize_promotions(batch, user, request)`**  
Atomically executes the batch inside a **single database transaction**:

| Outcome | Old enrollment | New enrollment | Student status |
|---|---|---|---|
| `PROMOTED` | → `PROMOTED` | Created in target year | unchanged |
| `REPEATED` | → `RETAINED` | Created in target year (same grade) | unchanged |
| `GRADUATED` | → `PROMOTED` | None | → `GRADUATED` |
| `TRANSFERRED` | → `WITHDRAWN` | None | → `TRANSFERRED` |
| `WITHDRAWN` | → `WITHDRAWN` | None | → `WITHDRAWN` |

> **Safety:** Duplicate enrollment prevention — raises `ValidationError` if a
> student already has an enrollment in the target year. The entire transaction
> rolls back on any failure.

### 4.4 `StudentAcademicHistoryService`
**`get_student_academic_history(student)`**  
Returns a structured chronological transcript dict:
```python
{
    'student': Student,
    'history_rows': [
        {
            'enrollment': StudentEnrollment,
            'academic_year': AcademicYear,
            'grade': Grade,
            'section': Section,
            'stream': Stream,
            'is_repeating': bool,  # True if enrollment status is 'RETAINED'
            'status': str,
            'summaries': QuerySet[StudentResultSummary],
            'attendance_total': int,
            'attendance_present': int,
            'attendance_percentage': Decimal|None,
            'promotion_record': PromotionRecord|None,
        }, ...
    ],
    'status_changes': QuerySet[StudentStatusHistory],
    'graduation': GraduationRecord|None,
}
```

### 4.5 `GraduationService`
**`get_graduation_candidates(academic_year=None)`**  
Returns list of Grade 12 students with their academic averages and graduation
record status for the graduation registry view.

### 4.6 `PromotionReportService`
**`export_promotion_batch_pdf(batch, filename)`**  
Generates a landscape A4/Letter PDF using **ReportLab** with:
- School header and batch metadata
- Full candidate roster with averages, failing counts, attendance,
  recommended and final outcomes

**`export_promotion_batch_excel(batch, filename)`**  
Generates an `.xlsx` workbook using **OpenPyXL** with formatted headers,
conditional row styling, and auto-column widths.

---

## 5. URL Routes

| Name | Path | View | Access |
|---|---|---|---|
| `promotion_index` | `/promotion/` | `promotion_dashboard_view` | Any authenticated |
| `promotion_prepare` | `/promotion/prepare/` | `promotion_prepare_view` | Management staff |
| `promotion_batch_detail` | `/promotion/batch/<id>/` | `promotion_batch_detail_view` | Any authenticated |
| `promotion_record_update` | `/promotion/record/<id>/update/` | `promotion_record_update_view` | Management staff |
| `promotion_batch_submit` | `/promotion/batch/<id>/submit/` | `promotion_batch_submit_view` | Management staff |
| `promotion_preview` | `/promotion/batch/<id>/preview/` | `promotion_preview_view` | Management staff |
| `promotion_approval` | `/promotion/batch/<id>/approve/` | `promotion_approval_view` | Principal/Registrar |
| `promotion_finalize` | `/promotion/batch/<id>/finalize/` | `promotion_finalize_view` | Management staff |
| `student_academic_history` | `/promotion/history/<student_id>/` | `student_academic_history_view` | Any authenticated |
| `graduation_management` | `/promotion/graduation/` | `graduation_management_view` | Management staff |
| `student_status_change` | `/promotion/status-change/` | `student_status_change_view` | Management staff |
| `student_status_history` | `/promotion/transfers/` | `student_status_history_view` | Any authenticated |
| `promotion_reports` | `/promotion/reports/` | `promotion_reports_view` | Any authenticated |
| `export_promotion_pdf` | `/promotion/batch/<id>/export/pdf/` | `export_promotion_pdf_view` | Any authenticated |
| `export_promotion_excel` | `/promotion/batch/<id>/export/excel/` | `export_promotion_excel_view` | Any authenticated |
| `promotion_criteria` | `/promotion/criteria/` | `promotion_criteria_view` | Management staff |

---

## 6. Templates

All templates are in `templates/promotion/` and extend `base.html`:

| Template | Purpose |
|---|---|
| `dashboard.html` | KPI cards, active batches, recent transfers |
| `prepare.html` | Batch creation form |
| `batch_detail.html` | Candidate roster with inline outcome editing |
| `preview.html` | Formal pre-finalization review screen |
| `approval.html` | Committee approval/rejection form |
| `academic_history.html` | Longitudinal student transcript |
| `graduation.html` | Grade 12 graduation registry |
| `status_change.html` | Transfer/withdrawal recording form |
| `status_history.html` | School-wide audit registry |
| `reports.html` | PDF/Excel export directory |
| `criteria.html` | Promotion policy management |

---

## 7. Promotion Workflow

```
Staff (Registrar)              System                    Principal
      │                          │                           │
      ├── Create Batch ─────────►│                           │
      │   (select year,          │  Assess all students      │
      │    grade, criteria)      │  Generate recommendations │
      │                          │  Create PromotionRecords  │
      │◄─────────────────────────┤                           │
      │                          │                           │
      ├── Review/Adjust ────────►│                           │
      │   (override outcomes,    │  Update PromotionRecords  │
      │    assign next classes)  │                           │
      │                          │                           │
      ├── Submit for Review ────►│                           │
      │                          ├──── Notify Principal ────►│
      │                          │                           │
      │                          │◄─── APPROVED/REJECTED ───┤
      │                          │                           │
      ├── Finalize ─────────────►│                           │
      │   (if APPROVED)          │  Atomic transaction:      │
      │                          │  - Close old enrollments  │
      │                          │  - Create new enrollments │
      │                          │  - Record graduations     │
      │                          │  - Log status changes     │
      │◄─── Done ────────────────┤                           │
```

---

## 8. Configurable Promotion Criteria

All thresholds are stored in the `PromotionCriteria` model and are editable
via the Django admin or the `/promotion/criteria/` management page.

**Default policy (auto-created if none exists):**
- Minimum average: **50%**
- Maximum failing subjects: **2**
- Minimum attendance: **75%**

School administrators can create multiple named policies (e.g., one for
regular students, one for repeating students) and select the appropriate
policy when creating each promotion batch.

---

## 9. Permissions

| Role | Can Create Batch | Can Edit Records | Can Submit | Can Approve | Can Finalize |
|---|:---:|:---:|:---:|:---:|:---:|
| Admin | ✅ | ✅ | ✅ | ✅ | ✅ |
| Principal | ❌ | ❌ | ❌ | ✅ | ✅ |
| Registrar | ✅ | ✅ | ✅ | ✅ | ✅ |
| Teacher | View only | ❌ | ❌ | ❌ | ❌ |

Permissions are enforced by the `accounts.decorators` used in every view.

---

## 10. Django Admin Registration

All 5 models are registered in `promotion/admin.py`:

- **`PromotionCriteriaAdmin`** — list display, search, filters
- **`PromotionBatchAdmin`** — with inline `PromotionRecordInline`
- **`PromotionRecordAdmin`** — searchable, filterable by outcome and batch
- **`GraduationRecordAdmin`** — Grade 12 registry management
- **`StudentStatusHistoryAdmin`** — full audit trail browser

---

## 11. Integration with Other Modules

| Module | Integration |
|---|---|
| **Student Management** | Reads `Student`, `StudentEnrollment`; updates `student.status` |
| **Academic Management** | Reads `AcademicYear`, `Grade`, `Section`, `Stream`, `ClassOffering` |
| **Examination & Results** | Reads `StudentResultSummary`, `Mark`, `ExamSubject` for assessment |
| **Attendance** | Reads `AttendanceRecord` via `student_enrollment` FK for attendance percentage |
| **Core** | Writes `AuditLog` for every significant action |

---

## 12. Database Relationships

```
PromotionCriteria ──────────────────────────────────────┐
                                                        │ (FK)
AcademicYear (source) ─────────────────────────────┐   │
AcademicYear (target) ─────────────────────────┐   │   │
Grade ─────────────────────────────────────┐   │   │   │
User (created_by) ─────────────────────┐   │   │   │   │
                                       │   │   │   │   │
                              PromotionBatch◄──┘───┘───┘
                                       │
                              PromotionRecord (1..*)
                              ├── student (FK → Student)
                              ├── student_enrollment (FK)
                              ├── previous_grade (FK → Grade)
                              ├── next_grade (FK → Grade)
                              ├── previous_class_offering (FK)
                              ├── next_class_offering (FK)
                              └── new_enrollment (FK → StudentEnrollment)

Student ─────────────┬──── GraduationRecord (0..1 per academic year)
                     └──── StudentStatusHistory (0..*)
```

---

## 13. Bugs Fixed During Implementation

| Bug | Root Cause | Fix Applied |
|---|---|---|
| `CheckConstraint(condition=...)` TypeError | Django 4.2 uses `check=`, not `condition=`; `condition=` is Django 5.1+ | Changed `condition=` → `check=` in both `results/models.py` and migrations |
| `AttributeError: 'super' object has no attribute 'dicts'` | Python 3.14 broke Django 4.2's `BaseContext.__copy__` | Patched `django/template/context.py` `__copy__` to use `__new__` + `__dict__.update` |
| `enr.is_repeating` AttributeError | `StudentEnrollment` has no `is_repeating` field | Changed to `enr.status == 'RETAINED'` |
| Old enrollment status set to `'COMPLETED'` | No such status choice in `StudentEnrollment.STATUS_CHOICES` | Changed to `'PROMOTED'` (promoted students) / `'RETAINED'` (repeated students) |
| `active_enr.completion_date` AttributeError | `StudentEnrollment` has no `completion_date` field | Removed from view's `status_change_view` |

---

## 14. Running Tests

```bash
python manage.py test promotion --verbosity=2
```

**Expected output:**
```
Ran 13 tests in ~72s
OK
```

### Test Coverage

| Test | Class | What it verifies |
|---|---|---|
| `test_promotion_assessment_recommendation` | Service | Pass student → PROMOTED, Fail student → REPEATED |
| `test_grade_12_graduation_recommendation` | Service | Grade 12 pass → GRADUATED recommendation |
| `test_batch_creation_and_candidate_population` | Service | Batch creates correct PromotionRecords with right next grades |
| `test_promotion_approval_and_atomic_finalization` | Service | Full workflow: prepare→submit→approve→finalize, status changes |
| `test_duplicate_target_enrollment_prevention` | Service | ValidationError + rollback if already enrolled in target year |
| `test_student_status_history_transfer_and_withdrawal` | Service | Transfer history recorded; transcript includes it |
| `test_pdf_and_excel_export_generation` | Service | PDF (ReportLab) and Excel (OpenPyXL) export returns valid bytes |
| `test_promotion_dashboard_view` | View | Dashboard loads with HTTP 200 |
| `test_promotion_prepare_view` | View | Batch creation form loads |
| `test_promotion_batch_detail_view` | View | Batch detail/roster renders |
| `test_student_academic_history_view` | View | Student transcript renders with correct name/admission |
| `test_graduation_management_view` | View | Graduation registry renders |
| `test_promotion_criteria_view` | View | Criteria management page renders |

---

## 15. Final Verification Results

```
python manage.py check               → System check identified no issues (0 silenced)
python manage.py makemigrations --check --dry-run → No changes detected
python manage.py test promotion      → Ran 13 tests in 72.387s — OK
```

---

*Documentation generated: Step 13 — Student Promotion and Academic History*  
*Project: Smart School Management and Academic Information System*  
*School: Majang Secondary School, Gambella Region, Ethiopia*
