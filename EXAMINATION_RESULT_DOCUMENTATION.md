# Step 12: Examination and Result Management System Documentation

## 1. System Overview
The **Examination and Result Management Module** for the Smart School Management and Academic Information System (SSMS) replaces paper-based examination processing at Majang Secondary School (Grades 9–12, Gambella Region, Ethiopia) with a robust, offline-capable electronic workflow deployed on the school's local area network (LAN).

The module supports continuous assessment, midterm, and final examinations, teacher marks recording with draft and submission modes, strict registrar/administrative review workflows, decimal-safe aggregated calculations with ranking and configurable grading scales, official printable PDF report cards, and master gradebook Excel exports.

---

## 2. Key Architecture & Features

### A. Examination Management (`examinations`)
- **Configurable Assessment Categories (`ExamType`)**: Quizzes, Tests, Midterm Examinations, Final Examinations, Continuous Assessment with default weight percentages.
- **Formal Examination Cycles (`Examination`)**: Scoped to Academic Year, Semester, and optionally specific Grade levels or Class Offerings. Enforces strict date ordering (`start_date <= end_date`) and lifecycle states (`DRAFT`, `ACTIVE`, `SUBMITTED`, `PUBLISHED`, `CLOSED`).
- **Subject Scheduling & Thresholds (`ExamSubject`)**: Sets individual Maximum Marks, Passing Thresholds, and Weight Percentages for each subject. Supports 1-click auto-population from the official secondary curriculum (`CurriculumSubject`).

### B. Marks & Results Management (`results`)
- **Missing Marks Preservation**: Missing/unrecorded marks remain `None`/null and are explicitly distinguished from an actual zero score or absence.
- **Bulk Teacher Marks Entry Grid**: Individual and batch score recording with client-side and server-side range validation (`0 <= marks_obtained <= max_marks`), absent/excused toggling, and draft preservation.
- **Multi-Tier Verification & Approval**:
  1. *Teacher*: Enters scores in Draft mode and clicks **Save & Submit for Review** (locks teacher edits, advances status to `SUBMITTED`).
  2. *Registrar / Exam Officer*: Reviews scores, statistical summaries (mean, min, max, pass rate), and enters approval decision (`APPROVED` or `RETURNED` with correction notes).
  3. *Principal / Management*: Computes aggregated results and officially publishes the examination.
- **Decimal-Safe Aggregation & Ranking (`ResultCalculationService`)**:
  - Uses `Decimal` arithmetic for marks, percentages, and averages.
  - Computes weighted totals, percentages, and overall letter grade mappings.
  - Automatically calculates competitive class ranking (`rank = 1, 2, ...`).
- **Configurable Grading Policies (`GradingScale` & `GradingRange`)**:
  - Configurable master grading policy (default: Ethiopian Secondary Standard Scale: A: 90–100%, B: 80–89.99%, C: 60–79.99%, D: 50–59.99%, F: 0–49.99%).
  - Fully customizable score intervals, GPA points (0.0 to 4.0), and passing flags.
- **Official Report Cards & Document Generation**:
  - Web report card view with printable CSS styling.
  - 1-click **ReportLab PDF generation** (`ReportCardService.export_report_card_pdf`) with Ethiopian secondary school letterhead, signature lines, and mark breakdowns.
  - Master classroom gradebook export to **Microsoft Excel (.xlsx)** via `openpyxl`.
- **Longitudinal Student Transcripts**:
  - Student academic history transcript tracking cumulative examination performance across terms and grades.

---

## 3. Database Schema

### `examinations`
1. `ExamType`: `name`, `code`, `description`, `default_weight`, `is_active`.
2. `Examination`: `name`, `exam_type` (FK), `academic_year` (FK), `semester`, `grade` (FK, nullable), `class_offering` (FK, nullable), `start_date`, `end_date`, `status`, `is_locked`, `created_by` (FK), `created_at`, `updated_at`.
3. `ExamSubject`: `examination` (FK), `grade` (FK), `stream` (FK, nullable), `subject` (FK), `max_marks`, `pass_marks`, `weight_percentage`, `exam_date`, `start_time`, `end_time`, `status`, `submitted_by` (FK Teacher), `submitted_at`, `verified_by` (FK User), `verified_at`, `verification_remarks`. Unique constraint on `['examination', 'grade', 'stream', 'subject']`.

### `results`
1. `GradingScale`: `name`, `code`, `description`, `is_default`, `created_at`.
2. `GradingRange`: `grading_scale` (FK), `grade_label`, `min_score`, `max_score`, `gpa_point`, `description`, `is_passing`.
3. `Mark`: `student_enrollment` (FK), `exam_subject` (FK), `marks_obtained` (nullable Decimal), `is_absent` (bool), `is_excused` (bool), `status`, `remarks`, `entered_by` (FK), `entered_at`, `updated_at`. Check constraint `marks_non_negative: marks_obtained >= 0`. Unique constraint on `['student_enrollment', 'exam_subject']`.
4. `ResultApproval`: `exam_subject` (FK), `reviewed_by` (FK), `decision` (`APPROVED`, `RETURNED`), `comments`, `reviewed_at`.
5. `StudentResultSummary`: `student_enrollment` (FK), `examination` (FK), `total_obtained`, `total_max`, `average_mark`, `percentage`, `overall_grade`, `grade_description`, `subjects_passed`, `subjects_failed`, `total_subjects`, `is_complete`, `rank`, `status`, `calculated_at`. Unique constraint on `['student_enrollment', 'examination']`.

---

## 4. Verification & Testing
All 22 unit and integration tests passed:
- `python manage.py test examinations results`
- Model validations: Date logic, negative mark blocking, max mark overflow prevention, absent marks null preservation.
- Service workflows: Curriculum auto-population, lock/reopen lifecycle, teacher submission, registrar verification, calculation engine, ranking, PDF report card generation, and Excel gradebook generation.
