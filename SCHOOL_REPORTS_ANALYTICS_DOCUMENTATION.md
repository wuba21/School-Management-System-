# SCHOOL REPORTS AND ANALYTICS DASHBOARD DOCUMENTATION
## Smart School Management and Academic Information System (SSMS)
**Target Environment:** Secondary School (Grades 9–12, 1,000–2,000 students), Majang Zone, Gambella Region, Ethiopia  
**Deployment Profile:** Local School Area Network (LAN), Offline-First Architecture (zero cloud/internet dependencies)  
**Technology Stack:** Python 3.10+, Django 4.2+, PostgreSQL / SQLite, Bootstrap 5, Chart.js (Local UMD), ReportLab, OpenPyXL  

---

## 1. Executive Summary & Module Overview

The **School Reports and Analytics Dashboard** (Step 15) provides high-performance, real-time reporting, institutional analytics, and business intelligence for school leaders, department heads, and academic registries. Designed specifically for the operational reality of secondary education in Majang Zone, Gambella Region, Ethiopia, the module functions entirely offline within a local school network (LAN).

### Core Objectives Delivered:
1. **Centralized Executive Intelligence:** A unified, real-time analytics dashboard aggregating vital institutional metrics across all active school domains: Students, Faculty, Attendance, Examinations, and Academic Promotions.
2. **Offline-Capable Interactive Visualizations:** 8 responsive Chart.js visual models powered by a locally hosted UMD vendor script (`static/vendor/chartjs/chart.umd.min.js`), requiring no external CDN or web connectivity.
3. **Multi-Dimensional Query Engine:** Dynamic filtering by Academic Year, Grade Level, Class Offering, Section, Stream (Natural / Social Sciences), Subject, Examination, Teacher, Date Ranges, and Search Terms.
4. **Domain-Specific Analytical Portals:**
   - **Student Nominal Rolls & 360° Academic Portfolio:** Longitudinal multi-year records spanning enrollment history, term marks, attendance percentages, and historical promotion status.
   - **Teacher Workload & Allocation Reports:** Analysis of staff active status, subject specializations, class assignments, and active weekly period loads sourced from the timetable engine.
   - **Attendance & Chronic Absenteeism Monitoring:** Daily presence percentages, session audits, and an early-warning chronic absence roster ($\ge 3$ unexcused absences).
   - **Examination Broadsheets & Performance Analysis:** Grade- and subject-level statistical distributions (mean, minimum, maximum, pass percentages, and submission/approval statuses).
   - **Promotion Outcomes & Graduation Registry:** Cohort progression matrices and Grade 12 completion rosters.
5. **Dual Vector & Tabular Document Exports:** High-fidelity, print-ready PDF reports generated dynamically via ReportLab (including institutional headers, Ministry of Education metadata, and validation signature blocks) alongside formatted Microsoft Excel (`.xlsx`) workbooks powered by OpenPyXL.
6. **Strict Role-Based Access Control (RBAC):** Tiered privilege separation protecting student privacy while empowering Principals, Registrars, and Department Heads with administrative oversight, and restricting Teachers strictly to their assigned classes.

---

## 2. Architecture & Data Integrity Principles

### Zero Schema Redundancy
In compliance with project architecture rules, the `reports` application introduces **no duplicate tables, redundant models, or denormalized data silos**. All statistics and metrics are computed dynamically from real database records across existing subsystems:
- `students.Student` & `students.Enrollment`
- `teachers.Teacher`
- `academics.AcademicYear`, `academics.Grade`, `academics.ClassOffering`, `academics.Subject`, and `academics.TeacherAssignment`
- `attendance.AttendanceSession` & `attendance.AttendanceRecord`
- `examinations.Examination` & `results.StudentResult`
- `promotion.PromotionRecord` & `promotion.GraduationRecord`
- `timetable.Timetable` & `timetable.TimetableEntry`

### Service-Layer Separation of Concerns
The business logic is organized into specialized domain services inside `reports/services.py`:
- `AnalyticsService`: Master KPI compilation and JSON serialization for Chart.js rendering.
- `StudentReportService`: Roster querying, multi-criteria filtering, and student 360° dossier synthesis.
- `TeacherReportService`: Faculty roster calculation, class counts, and weekly scheduled period aggregation.
- `AttendanceReportService`: Institutional attendance tracking, day-by-day aggregates, and chronic absenteeism detection.
- `ExaminationPerformanceReportService`: Exam-level completion tracking and subject broadsheet generation with passing metrics.
- `PromotionReportService`: Academic progression analytics and Grade 12 graduation registries.
- `ReportExportService`: Streaming binary document rendering for PDF and Excel formats.

---

## 3. Real-Time Dashboard Statistics & Formulas

The **Main Analytics Dashboard** (`/reports/dashboard/`) computes actual statistics with safe zero-division fallbacks:

### A. Student Metrics
- **Total Registered Students:** Count of all non-deleted `Student` records in the database.
- **Active Students:** Count of students with `status='ACTIVE'`.
- **Gender Distribution:** Discrete counts of `MALE` vs. `FEMALE` students (accessible to authorized staff).
- **Grade-Level Distribution:** Aggregated student counts across Grades 9, 10, 11, and 12.
- **Class-Wise Distribution:** Active student counts mapped per `ClassOffering`.
- **New Registrations:** Students whose `admission_date` falls within the past 30 days.
- **Graduated Students:** Count of students with `status='GRADUATED'`.

### B. Teacher Workload Metrics
- **Total Faculty:** Total count of registered teachers.
- **Active Teachers:** Teachers with `status='ACTIVE'`.
- **Specialization Breakdown:** Faculty counts grouped by primary teaching subject.
- **Weekly Scheduled Periods:** Real-time count of periods scheduled across active published timetables.

### C. Attendance Metrics & Calculation
- **Presence Rate (%):**
  $$\text{Presence Rate} = \left( \frac{\text{Present Count} + \text{Late Count}}{\text{Total Records}} \right) \times 100$$
- **Excused Rate (%):** Calculated separately; excused absences are never marked as unexcused truancy.
- **Chronic Absenteeism Flag:** Identifies students accumulating $\ge 3$ unexcused absences within the queried scope for early academic intervention.

### D. Examination & Assessment Metrics
- **Completed Examinations:** Count of exams where `status='COMPLETED'`.
- **Pending Mark Submissions:** Exams in `DRAFT` or `SCHEDULED` status awaiting teacher input.
- **Pending Approvals:** Results awaiting departmental or administrative sign-off (`is_approved=False`).
- **Subject Average Score:** Arithmetic mean ($\bar{x}$) of scores attained per subject.
- **Subject Pass Rate (%):**
  $$\text{Pass Rate} = \left( \frac{\text{Count of Scores } \ge \text{Pass Mark}}{\text{Total Graded Scores}} \right) \times 100$$
  *(Default passing benchmark: 50.0%)*

### E. Academic & Promotion Metrics
- **Promoted Rate (%):** Proportion of evaluated students awarded `PROMOTED` status in promotion batches.
- **Detained / Conditional Rates (%):** Proportion of students requiring academic remediation or repeating the grade.
- **Graduation Registry:** Verified count of Grade 12 students completing secondary school requirements.

---

## 4. Interactive Chart.js Visualizations (Offline LAN)

The dashboard renders 8 interactive, responsive charts using the pre-bundled local script:
`static/vendor/chartjs/chart.umd.min.js`.

| # | Visualization Title | Chart Type | Data Dimensions | Educational Objective |
|---|---------------------|------------|-----------------|-----------------------|
| 1 | **Student Distribution by Grade** | Bar Chart | Grade 9, 10, 11, 12 | Visualizes enrollment parity and school capacity across grade tiers. |
| 2 | **Enrollment Trends Over Academic Years** | Line Chart | Multi-year historical cohorts | Monitors longitudinal school growth and drop-out rates. |
| 3 | **Attendance Presence Rate Trend** | Line Chart | Daily presence % across past 14 days | Detects weekday absenteeism patterns, market days, or regional disruptions. |
| 4 | **Class Attendance Rate Comparison** | Horizontal Bar | Top class offerings by presence % | Identifies classes with exceptional or lagging attendance rates. |
| 5 | **Subject Average Performance** | Bar Chart | Mean scores across academic subjects | Benchmarks curriculum delivery across STEM and Humanities. |
| 6 | **Examination Performance Trends** | Line Chart | Average scores across chronological exam events | Tracks pupil score trajectory from Mid-Terms to Final National prep exams. |
| 7 | **Teacher Distribution by Subject** | Bar Chart | Faculty count per teaching discipline | Highlights teaching surpluses or staffing shortages in critical subjects. |
| 8 | **Promotion Outcome Distribution** | Doughnut Chart | Promoted, Detained, Conditional, Repeat | Summarizes annual academic throughput for regional education bureau reporting. |

---

## 5. Multi-Dimensional Filtering Engine

The filtering engine (`ReportFilterForm` in `reports/forms.py`) provides cascading query filters:

- **Academic Year (`academic_year`):** Filters all dataset calculations by school calendar year.
- **Grade Level (`grade`):** Isolates data for Grades 9, 10, 11, or 12.
- **Class Offering (`class_offering`):** Targets specific section groups (e.g., Grade 9 Section A).
- **Stream (`stream`):** Differentiates between Natural Sciences and Social Sciences tracks in Grades 11–12.
- **Subject (`subject`):** Filters marks and teaching allocations to a specific curriculum course.
- **Examination (`examination`):** Isolates results for a specific assessment milestone.
- **Teacher (`teacher`):** Audits allocations and class timetables for a specific instructor.
- **Date Range (`date_from` & `date_to`):** Bounds attendance and registration queries within exact date windows.
- **Full-Text Search (`search`):** Search bar resolving student names, admission numbers, teacher names, or national ID cards.

---

## 6. Report Modules & Navigation Architecture

The reports app is registered under the `/reports/` namespace and integrated into the global sidebar (`templates/base.html`):

| Route Path | View Controller | Template | Description |
|------------|-----------------|----------|-------------|
| `/reports/dashboard/` | `analytics_dashboard_view` | `reports/dashboard.html` | Centralized executive metrics & 8 Chart.js visualizations. |
| `/reports/students/` | `student_reports_view` | `reports/student_reports.html` | Paginated student nominal roll with filters and direct exports. |
| `/reports/students/<id>/` | `student_report_detail_view` | `reports/student_detail_report.html` | 360° student portfolio (multi-year marks, attendance, promotions). |
| `/reports/teachers/` | `teacher_reports_view` | `reports/teacher_reports.html` | Staffing allocations, assigned classes, and weekly period counts. |
| `/reports/teachers/<id>/` | `teacher_report_detail_view` | `reports/teacher_detail_report.html` | Individual instructor teaching dossier and schedule summary. |
| `/reports/attendance/` | `attendance_reports_view` | `reports/attendance_reports.html` | Daily institutional aggregates and chronic absenteeism alert roster. |
| `/reports/examinations/` | `examination_reports_view` | `reports/examination_reports.html` | Assessment completion metrics, score bounds, and approval tracking. |
| `/reports/academic/` | `academic_performance_reports_view` | `reports/academic_performance.html` | Subject performance broadsheets, pass rates, and class averages. |
| `/reports/promotion/` | `promotion_reports_view` | `reports/promotion_reports.html` | Annual cohort progression statistics and Grade 12 graduation registry. |
| `/reports/exports/` | `export_center_view` | `reports/export_center.html` | Dedicated download center for pre-formatted PDF and Excel rosters. |
| `/reports/exports/pdf/` | `export_report_pdf_view` | Streaming Binary Response | Vector PDF generator using ReportLab with MoE formatting. |
| `/reports/exports/excel/` | `export_report_excel_view` | Streaming Binary Response | Excel `.xlsx` generator using OpenPyXL with column auto-sizing. |

---

## 7. Report Export Center & Document Standards

Both export streams are generated dynamically in-memory (`io.BytesIO`) without temporary disk clutter:

### PDF Export Specifications (ReportLab)
- **Geometry:** Standard A4 portrait/landscape layout with 36pt margins.
- **Header:** Includes Regional Education Bureau / Majang Zone Secondary School title, generated timestamp, active filters, and report subtitle.
- **Table Formatting:** Alternating row striping (`#F8FAFC` vs `#FFFFFF`), bold dark headers (`#1E3A8A`), bordered grid lines, and automatic cell text wrapping.
- **Footer & Signatures:** Automated page numbering ("Page X of Y") and formal signature placeholders for the **Prepared By (Registrar)** and **Approved By (School Principal)**.

### Excel Export Specifications (OpenPyXL)
- **Workbook Format:** Native `.xlsx` with styled sheet headers.
- **Header Row:** Bold dark navy background with white text and centered alignment.
- **Cell Styling:** Grid borders on all data cells, proper date/number formatting, and automatic column width calculation (preventing text truncation).

---

## 8. Role-Based Access Control (RBAC) & Security Policies

Access control is enforced at both view level (decorators) and service level (data query scoping):

| User Role | Dashboard Access | Student Roster | Teacher Reports | Attendance | Exams & Academic | Promotion & Graduation | Export Center |
|-----------|------------------|----------------|-----------------|------------|------------------|------------------------|---------------|
| **Principal** | Full Access | Full Access | Full Access | Full Access | Full Access | Full Access | Full Access |
| **Registrar** | Full Access | Full Access | Full Access | Full Access | Full Access | Full Access | Full Access |
| **Administrator** | Full Access | Full Access | Full Access | Full Access | Full Access | Full Access | Full Access |
| **Teacher** | Restricted | Assigned Classes Only | Self Profile Only | Assigned Classes Only | Assigned Subjects Only | View Only | Restricted |
| **Student / Parent** | Denied | Denied | Denied | Denied | Denied | Denied | Denied |

---

## 9. Verification & Automated Test Suite

A complete test suite was developed in `reports/tests.py` containing **16 automated test cases**:

1. `test_analytics_dashboard_statistics`: Verifies accurate KPI calculations across populated models.
2. `test_analytics_dashboard_safe_with_empty_database`: Verifies zero-division protection when no records exist.
3. `test_chart_data_structure`: Validates JSON structure of all 8 Chart.js datasets.
4. `test_student_reports_filtering`: Confirms multi-criteria filtering by grade, class, and search terms.
5. `test_student_detail_report_aggregation`: Verifies 360° academic portfolio generation.
6. `test_teacher_reports_workload`: Tests teacher weekly period aggregation from timetables.
7. `test_attendance_daily_summary`: Tests daily presence percentage calculations.
8. `test_attendance_chronic_absenteeism`: Tests detection of students with $\ge 3$ absences.
9. `test_examination_reports_metrics`: Tests pass rate and average calculations for exams.
10. `test_academic_performance_subject_broadsheet`: Validates subject score broadsheet generation.
11. `test_promotion_reports_outcomes`: Tests promotion outcome counters and graduation rosters.
12. `test_export_pdf_generation`: Validates generation of valid binary PDF files (`%PDF` header).
13. `test_export_excel_generation`: Validates generation of valid binary Excel files (`PK` ZIP container).
14. `test_rbac_principal_access`: Verifies authorized access for school administrative leadership.
15. `test_rbac_teacher_restricted_access`: Verifies query scoping and access limits for teaching staff.
16. `test_rbac_unauthenticated_redirect`: Confirms unauthenticated users are safely redirected to `/login/`.

### Verification Commands & Results:
```powershell
# 1. Django System Checks
python manage.py check
# Result: System check identified no issues (0 silenced).

# 2. Database Migrations Validation
python manage.py makemigrations --check --dry-run
# Result: No changes detected in apps.

# 3. Reports Test Execution
python manage.py test reports --verbosity=2
# Result: Ran 16 tests in 130.330s - OK
```

---

## 10. Operational Guidelines for LAN Deployment

1. **Zero External Requests:** All static assets (Bootstrap 5, Bootstrap Icons, Chart.js) are resolved locally from `/static/vendor/`. No internet access is required.
2. **Server Startup:** The system runs on the local school server or master PC:
   ```powershell
   python manage.py runserver 0.0.0.0:8000
   ```
   Client workstations on the school LAN access the dashboard via `http://<server-ip>:8000/reports/dashboard/`.
3. **Printing Reports:** All detail reports and broadsheets feature standard CSS `@media print` rules to ensure instant, clean printing directly from standard web browsers.
