# Development Roadmap

This document outlines the phased, step-by-step development roadmap for the **Smart School Management and Academic Information System (SSMS)**. 

To ensure stability, code quality, and structured learning, development proceeds in **one step at a time**, with each step concluding with testing, verification, and explicit confirmation before moving forward.

---

## Roadmap Overview

```
Phase 1: Foundations & Architecture  ──►  Phase 2: Academic Core & People  ──►  Phase 3: Daily Operations
(Requirements, Setup, Auth, UI)          (Structure, Teachers, Students)        (Timetable, Attendance)
                                                                                            │
                                                                                            ▼
Phase 6: Final Hardening & Deployment ◄── Phase 5: Intelligence & Analytics ◄── Phase 4: Assessment & Results
(Audit, Backups, Testing, LAN Setup)     (ML Performance, Attendance, AI Bot)   (Exams, Marks, Report Cards)
```

---

## Phase 1: Foundations and Architecture

### Step 1: Project Planning and Requirements Analysis *(Current Step)*
* **Objective:** Define project scope, functional and non-functional requirements, user roles, system architecture, offline LAN design, and development roadmap.
* **Deliverables:** `PROJECT_OVERVIEW.md`, `FUNCTIONAL_REQUIREMENTS.md`, `NON_FUNCTIONAL_REQUIREMENTS.md`, `USER_ROLES.md`, `SYSTEM_ARCHITECTURE.md`, `DEVELOPMENT_ROADMAP.md`.
* **Verification Checkpoint:** Formal approval of requirements and architectural principles by the user.

### Step 2: Environment Setup and Project Scaffolding
* **Objective:** Initialize Python virtual environment, install core dependencies (Django, psycopg2, pandas, scikit-learn), configure PostgreSQL database connection, and scaffold the modular Django project layout.
* **Deliverables:** `requirements.txt`, `.env.example`, `settings/` configuration, database connection verification script.
* **Verification Checkpoint:** Successful execution of `python manage.py runserver` and successful database ping.

### Step 3: Custom User Model, Authentication & RBAC
* **Objective:** Implement the custom user model (`CustomUser`), role definitions (Principal, Registrar, Teacher, SysAdmin), login/logout views, password change views, and role-based access decorators.
* **Deliverables:** `apps.accounts` models, migrations, authentication forms, templates, unit tests.
* **Verification Checkpoint:** Login as different user roles and verify that unauthorized routes are blocked.

### Step 4: UI Framework and Offline Layout Architecture
* **Objective:** Bundle Bootstrap 5, Bootstrap Icons, and custom CSS locally. Create base templates, responsive sidebar navigation, breadcrumbs, and flash alert messaging.
* **Deliverables:** `templates/base.html`, `static/vendor/` local asset bundling, `static/css/styles.css`, sample dashboard layout.
* **Verification Checkpoint:** Interface loads fully offline in a browser with no missing fonts, scripts, or broken CSS links.

---

## Phase 2: Academic Core and Stakeholder Management

### Step 5: Academic Structure (Years, Semesters, Grades, Sections, Streams, Subjects)
* **Objective:** Build models and management interfaces for Academic Years, Semesters, Grades 9–12, Sections, Curriculum Streams (Natural/Social Science), and the Master Subject catalog.
* **Deliverables:** `apps.academics` models, admin interfaces, CRUD views, validation logic.
* **Verification Checkpoint:** Create a full academic year with 2 semesters, Grades 9–12, sections A–C, and core subjects.

### Step 6: Teacher Management and Subject Allocations
* **Objective:** Implement teacher profiles, qualifications, and teaching workload allocation mapping (Teacher ↔ Subject ↔ Section).
* **Deliverables:** `apps.teachers` models, allocation interface, teacher directory, workload summary view.
* **Verification Checkpoint:** Allocate a teacher to Grade 10-A Mathematics and verify they can view only their assigned class.

### Step 7: Student Information Management and Class Enrollment
* **Objective:** Implement student registration with Ethiopian three-part naming, profile details, guardian contacts, unique Student ID generation, and class section enrollment.
* **Deliverables:** `apps.students` models, registration forms, student search/filter view, enrollment history tracker.
* **Verification Checkpoint:** Register synthetic students, enroll them into Grade 9-A, and verify uniqueness constraints.

---

## Phase 3: Daily School Operations

### Step 8: Timetable Management
* **Objective:** Build weekly class scheduling grids by section and teacher, with automated collision detection to prevent double-booking teachers or classrooms.
* **Deliverables:** `apps.timetable` models, timetable builder view, conflict validation logic, printable schedule views.
* **Verification Checkpoint:** Schedule classes and confirm the system blocks scheduling two classes for one teacher at the same period.

### Step 9: Attendance Management
* **Objective:** Create a high-speed daily/period attendance entry grid for teachers (Present, Absent, Late, Excused), with automatic chronic absenteeism detection.
* **Deliverables:** `apps.attendance` models, rapid-entry attendance sheet, monthly attendance summary, absence alert dashboard.
* **Verification Checkpoint:** Take attendance for a section, modify an entry, and verify percentage calculations.

---

## Phase 4: Assessment, Examinations, and Results

### Step 10: Examination Configuration and Continuous Assessment
* **Objective:** Configure assessment weighting (Continuous Assessment, Midterm, Final Exam), exam schedules, and grading scale definitions.
* **Deliverables:** `apps.examinations` models, assessment configuration interface, exam session manager.
* **Verification Checkpoint:** Define assessment categories totaling 100% and test validation bounds.

### Step 11: Mark Entry and Result Processing
* **Objective:** Build secure mark entry grids for teachers with numerical range validation (0–100), automated total calculation, and term lock mechanisms.
* **Deliverables:** Mark entry views, draft saving, submission workflow, automated letter grade and pass/fail determination.
* **Verification Checkpoint:** Enter marks for a class, confirm out-of-bounds numbers are rejected, and verify average calculation.

### Step 12: Rank Computation and Official Report Cards
* **Objective:** Implement algorithms for calculating student averages, section ranks, and grade ranks. Generate clean, printable PDF report cards and section broadsheets.
* **Deliverables:** `apps.reports` PDF generator, print stylesheets, report card view, master score sheet.
* **Verification Checkpoint:** Generate a printable report card for a student and verify that rank and subject marks format cleanly for A4 printing.

---

## Phase 5: Student Progression and Academic History

### Step 13: Student Promotion and Repetition Engine
* **Objective:** Build an automated promotion evaluation engine that evaluates students against passing criteria, presenting candidates for Principal review and override.
* **Deliverables:** Promotion rules processor, Principal review interface, promotion transition executor.
* **Verification Checkpoint:** Run promotion on synthetic test data; confirm passed students advance to the next grade and failed students are retained.

### Step 14: Longitudinal Academic History and Transcripts
* **Objective:** Archive completed academic years, preserving immutable historical snapshots of student grades, and generate multi-year official academic transcripts.
* **Deliverables:** Academic history snapshots, official transcript generator.
* **Verification Checkpoint:** View a multi-year transcript for a student across Grades 9, 10, and 11.

---

## Phase 6: Administration, Security, and Auditing

### Step 15: Role-Specific Dashboards
* **Objective:** Create tailored dashboards with actionable metrics and KPIs for the Principal, Registrar, Teacher, and System Administrator.
* **Deliverables:** Dashboard views, Chart.js local widgets, KPI summary cards.
* **Verification Checkpoint:** Log in as each of the 4 roles and verify that each dashboard presents the appropriate role-specific metrics.

### Step 16: Audit Logging and Activity Tracking
* **Objective:** Build an automatic audit trail capturing sensitive actions (score changes, user logins, promotion overrides) with timestamps, actor IDs, and IP addresses.
* **Deliverables:** `apps.audit` middleware and models, audit log viewer for Administrator and Principal.
* **Verification Checkpoint:** Edit a student mark and verify that an audit entry is created showing old vs. new values.

### Step 17: Database Backup and Disaster Recovery
* **Objective:** Implement a reliable database backup and restore system with one-click export and scheduled dumps to local storage and external USB drives.
* **Deliverables:** `apps.backup` management commands, backup trigger UI, restore verification documentation.
* **Verification Checkpoint:** Trigger a database backup, verify the created `.sql` archive, and test restoration on a fresh database.

---

## Phase 7: Artificial Intelligence and Analytics

### Step 18: AI Attendance Pattern Analysis
* **Objective:** Implement machine learning algorithms using Pandas and Scikit-learn to identify hidden absenteeism patterns, day-of-week correlations, and high-risk absence trajectories.
* **Deliverables:** `apps.ai_engine` attendance models, visual trend graphs, early intervention alerts.
* **Verification Checkpoint:** Run the model on synthetic attendance data and verify that chronic absentees are flagged correctly.

### Step 19: AI Academic Performance Prediction and Recommendations
* **Objective:** Develop predictive models that forecast final student performance based on continuous assessments, identifying students needing remedial support and generating teacher recommendations.
* **Deliverables:** Predictive regression/classification pipeline, early-warning indicator widget, recommendation generator.
* **Verification Checkpoint:** Train model on mock grade data and confirm accuracy of risk classification.

### Step 20: Offline AI School Assistant
* **Objective:** Build an offline conversational assistant capable of answering user inquiries regarding school rules, examination schedules, timetables, and academic policies.
* **Deliverables:** Conversational interface, structured rule/retrieval knowledge engine.
* **Verification Checkpoint:** Query the assistant regarding class schedules and graduation requirements without internet access.

---

## Phase 8: Final Testing, Optimization, and LAN Deployment

### Step 21: Comprehensive System Testing and Synthetic Data Seeding
* **Objective:** Populate the database with realistic synthetic data (1,500 students, 60 teachers, full academic year of attendance and marks) and execute automated test suites.
* **Deliverables:** Data generation management commands, end-to-end integration tests.
* **Verification Checkpoint:** 100% passing test suite and smooth UI rendering with 1,500+ records.

### Step 22: Local Network Deployment and Production Hardening
* **Objective:** Configure the application for production LAN use using Waitress WSGI on Windows, set static IP binding, configure Windows Firewall, and create a user manual for school staff.
* **Deliverables:** Production configuration files, startup scripts, administrative operating manual.
* **Verification Checkpoint:** Access the application successfully from a second computer over the local network.
