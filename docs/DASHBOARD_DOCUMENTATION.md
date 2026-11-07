# Dashboard Implementation & Analytics Documentation

**Project:** Smart School Management and Academic Information System (SSMS)  
**Location:** Majang Zone, Gambella Region, Ethiopia  
**Phase:** Step 7 Implementation  

---

## 1. Executive Summary

The Admin Dashboard provides a real-time, database-grounded operational hub for secondary school leadership and instructional staff. It dynamically adjusts its KPIs, charts, quick actions, and data tables according to the logged-in user's role (**Principal, Registrar, Teacher, or System Administrator**), while maintaining zero external internet dependency for LAN environments.

---

## 2. Architecture & Service Layer

All dashboard data computation is decoupled from views into `dashboard/services.py`:

```
                       ┌────────────────────────────┐
                       │   HTTP Request (Session)   │
                       └─────────────┬──────────────┘
                                     │
                        @any_authenticated_role_required
                                     │
                       ┌─────────────▼──────────────┐
                       │   dashboard.views.dashboard │
                       └─────────────┬──────────────┘
                                     │
                 ┌───────────────────┴───────────────────┐
                 │        dashboard.services             │
                 │         DashboardService              │
                 ├───────────────────────────────────────┤
                 │ • get_overview_kpis()                 │
                 │ • get_student_analytics()             │
                 │ • get_attendance_analytics()          │
                 │ • get_academic_analytics()            │
                 │ • get_role_specific_context()         │
                 │ • get_recent_activities()             │
                 └───────────────────┬───────────────────┘
                                     │ (Aggregated Queries)
               ┌─────────────────────┼─────────────────────┐
               ▼                     ▼                     ▼
        students.Student      teachers.Teacher     academics.ClassOffering
        attendance.Record     examinations.Exam    core.AuditLog
```

---

## 3. Component Details & Database Queries

### 3.1 Overview KPI Cards (6 Metrics)

1. **Total Active Students:**
   - **Query:** `Student.objects.filter(status='ACTIVE').count()`
   - **Empty State:** Safely displays `0` and a subtitle indicating "Awaiting enrollment".
2. **Total Active Teachers:**
   - **Query:** `Teacher.objects.filter(is_active=True).count()`
3. **Active Academic Year:**
   - **Query:** `AcademicYear.objects.filter(is_current=True).first()`
   - Displays Ethiopian calendar notation and academic period.
4. **Active Classes Running:**
   - **Query:** `ClassOffering.objects.filter(academic_year=current_year).count()`
5. **Today's Attendance Rate:**
   - **Query:** Aggregates `AttendanceRecord` linked to `AttendanceSession` on `date=timezone.localdate()`.
   - **Formula:** $\text{Attendance Rate} = \frac{\text{Present} + \text{Late}}{\text{Total Sessions Today}} \times 100$
   - **Fallback:** If no roll-call occurred today, computes the 7-day rolling average or defaults cleanly to `0.0%` with an explanatory tag.
6. **Pending Examination Cycles:**
   - **Query:** `Examination.objects.filter(is_active=True, is_locked=False).count()` along with `Mark.objects.count()`.

### 3.2 Student Demographics & Analytics (Chart.js)

- **Enrollment by Grade Level:**
  - Aggregates active student enrollments grouped by grade:
    ```python
    Grade.objects.all().annotate(
        student_count=Count(
            'class_offerings__student_enrollments',
            filter=Q(class_offerings__student_enrollments__status='ACTIVE')
        )
    ).order_by('level')
    ```
- **Gender Ratio:**
  - Evaluates `Student.objects.filter(status='ACTIVE').values('gender').annotate(count=Count('id'))`.
- **Stream Distribution:**
  - Counts students enrolled across General Secondary, Natural Science, and Social Science streams.

### 3.3 Attendance Analytics

- **Trajectory:**
  - Queries the last 7 distinct session dates and calculates daily compliance percentage.
- **Categorical Breakdown:**
  - Counts cumulative status: Present, Absent, Late, and Excused.

### 3.4 Academic Offerings & Class Rosters

- Lists active class offerings with assigned Grade, Section, Stream, current enrolled count, and maximum room capacity.

### 3.5 Role-Based Dashboards & Workload Panels

| Role | Role-Specific Banner & Metrics | Quick Actions |
| :--- | :--- | :--- |
| **School Principal** | Institutional health overview, grade distributions, school-wide attendance, examination status. | Academic reports, student rosters, exam cycle review. |
| **Registrar** | Unassigned student count (students without class allocation), recent admissions, enrollment volume. | Register student, manage sections, student transcripts. |
| **Teacher** | Assigned teaching classes count, assigned subjects count, total students taught across assigned classes, recent attendance sessions submitted. | Record class attendance, enter exam marks for assigned subjects. |
| **System Administrator**| System user account breakdown by role (Active vs Inactive), security audit trail summary. | Manage accounts, view immutable audit logs, system settings. |

---

## 4. Performance & Query Optimization

1. **Elimination of N+1 Queries:**
   - Class offerings, teachers, and student counts use `.select_related()` for foreign keys and `.annotate(Count())` for child collections.
2. **Database Aggregation:**
   - Computations (averages, counts, percentages) are performed in the PostgreSQL/SQLite engine rather than in Python memory.
3. **Safe JSON Island Serialization:**
   - Chart datasets are passed using `<script id="chart-data" type="application/json">` parsed via DOM API, eliminating XSS vulnerabilities and syntax errors.
4. **Bounded Activity Queries:**
   - Recent activity lists are capped at `.order_by('-timestamp')[:8]` with role-based filtering.

---

## 5. Automated Test Suite (`dashboard/tests.py`)

The test suite verifies:
1. `test_unauthenticated_dashboard_redirects_to_login`: Verifies 302 redirect for unauthenticated access.
2. `test_empty_database_dashboard_renders_cleanly`: Verifies that an empty database does not cause division by zero or template crashes, rendering friendly empty states.
3. `test_populated_dashboard_statistics`: Validates accurate count of students, teachers, and active classes.
4. `test_attendance_rate_calculation`: Tests accurate percentage calculation with Present, Late, and Absent records.
5. `test_principal_role_dashboard`: Confirms executive presentation for Principal.
6. `test_registrar_role_dashboard`: Confirms unassigned student counter for Registrar.
7. `test_teacher_role_dashboard_with_assignments`: Confirms workload filtering to assigned classes for Teacher.
8. `test_administrator_role_dashboard`: Confirms user account statistics and system panel for Administrator.
9. `test_chart_payload_json_structure`: Verifies valid JSON serialization of chart arrays.
