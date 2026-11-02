# Functional Requirements Specification

This document details the complete functional requirements of the **Smart School Management and Academic Information System (SSMS)**. Each requirement is assigned a unique identifier (`FR-XX`) for traceability during testing and implementation.

---

## 1. Authentication and User Management

* **FR-AUTH-01 (Secure Login):** The system shall allow registered users to authenticate using a unique username (or email) and password.
* **FR-AUTH-02 (Password Security):** Passwords must be hashed using Django's industry-standard cryptographic hashing algorithm (PBKDF2 with SHA-256). Passwords must never be stored in plain text.
* **FR-AUTH-03 (Account Status):** Administrators shall have the ability to activate, deactivate, or lock user accounts without deleting historical academic records associated with the user.
* **FR-AUTH-04 (Password Reset):** Administrators and registrars shall be able to reset user passwords when a staff member forgets their credentials.
* **FR-AUTH-05 (Session Management):** The system shall automatically terminate idle sessions after a configurable period of inactivity to prevent unauthorized access on shared laboratory computers.

---

## 2. Role-Based Access Control (RBAC)

* **FR-RBAC-01 (Role Assignment):** Every user account must be assigned exactly one primary system role: **Principal**, **Registrar**, **Teacher**, or **System Administrator**.
* **FR-RBAC-02 (Navigation Filtering):** The user interface sidebar and menu options shall dynamically adapt to show only features permitted for the logged-in user's role.
* **FR-RBAC-03 (Enforced Authorization):** The backend must enforce permission checks on every view, API endpoint, and data modification request. Client-side URL tampering must be rejected with HTTP 403 (Forbidden).
* **FR-RBAC-04 (Scope Restrictions for Teachers):** Teachers shall only have access to input attendance and marks for the specific subjects, grades, and sections assigned to them in the current academic year.

---

## 3. Academic Structure Management

* **FR-ACAD-01 (Academic Year Management):** The system shall support creating and managing academic years (e.g., 2026/2027 or 2018/2019 E.C.). Only one academic year may be designated as "Current/Active" at any time.
* **FR-ACAD-02 (Semester Configuration):** Each academic year shall be subdivided into academic terms/semesters (standardly Semester 1 and Semester 2) with distinct start and end dates.
* **FR-ACAD-03 (Grade Level Management):** The system shall support standard secondary grades: **Grade 9, Grade 10, Grade 11, and Grade 12**.
* **FR-ACAD-04 (Section Management):** Each grade level shall support multiple sections (e.g., Grade 9A, 9B, 9C, 10A, etc.) with a configurable maximum student capacity per section.
* **FR-ACAD-05 (Stream Management):** The system shall support curriculum streams for senior secondary levels (Grades 11 and 12), specifically:
  * **Natural Science Stream**
  * **Social Science Stream**
  * **General Secondary** (for Grades 9 and 10)
* **FR-ACAD-06 (Subject Management):** The system shall maintain a master subject catalog. Each subject shall have a title, code, credit/weekly period weight, stream assignment, and status (Core or Elective).
* **FR-ACAD-07 (Term Locking):** Registrars or Principals shall have the ability to "Lock" a completed semester to prevent retroactive editing of grades.

---

## 4. Student Information Management

* **FR-STUD-01 (Three-Part Naming):** The student model shall natively store Ethiopian three-part names:
  1. `First Name` (Student's given name)
  2. `Father's Name`
  3. `Grandfather's Name`
* **FR-STUD-02 (Student Profile):** The system shall capture comprehensive student profile data:
  * Unique Student ID (auto-generated or manually assigned)
  * Gender (Male / Female)
  * Date of Birth
  * Primary Language / Mother Tongue
  * Contact Address / Kebele / Village in Majang Zone
  * Guardian / Emergency Contact Details (Name, Relationship, Phone number)
  * Health / Medical Notices (optional)
  * Student Profile Photograph (optional)
* **FR-STUD-03 (Student Search and Filter):** Staff shall be able to search for students in real-time by Name, Student ID, Grade, Section, or Stream with paginated results.
* **FR-STUD-04 (Student Enrollment):** The system shall support enrolling students into a specific Academic Year, Grade, Section, and Stream, maintaining a complete record of historical enrollments.
* **FR-STUD-05 (Student Status):** Each student shall have an operational status: `Active`, `Transferred Out`, `Dropped Out`, `Suspended`, or `Graduated`.

---

## 5. Teacher Management

* **FR-TEACH-01 (Teacher Profile):** The system shall store teacher records including:
  * Full Name (First, Father, Grandfather)
  * Employee Identification Number
  * Gender and Contact Information
  * Academic Qualification (e.g., B.Ed., B.Sc., M.A.)
  * Major Subject / Department Specialization
  * Employment Date and Active Status
* **FR-TEACH-02 (Teaching Allocations):** Registrars shall be able to assign teachers to specific Subject + Section combinations for an active academic year (e.g., "Teacher Abebe teaches Physics to Grade 11-A").
* **FR-TEACH-03 (Teacher Workload Overview):** The system shall provide an overview of each teacher's total weekly periods and assigned classes to prevent overallocation.

---

## 6. Timetable Management

* **FR-TIME-01 (Weekly Schedule Grid):** The system shall provide a timetable matrix for each section spanning Monday through Friday across standard class periods.
* **FR-TIME-02 (Conflict Detection):** When assigning a teacher or room to a period, the system shall validate that neither the teacher nor the classroom is already scheduled for that exact time slot.
* **FR-TIME-03 (Schedule Views):** The system shall generate printable timetable views:
  * By Section (for students and classroom notice boards)
  * By Teacher (for individual staff planning)

---

## 7. Attendance Management

* **FR-ATT-01 (Quick Attendance Grid):** Teachers shall be able to take daily or period-based attendance through a fast web interface listing all enrolled students in their section.
* **FR-ATT-02 (Attendance Statuses):** The system shall support standard attendance markers:
  * **Present (P)**
  * **Absent (A)**
  * **Late (L)**
  * **Excused (E)** (e.g., medical or approved family emergency)
* **FR-ATT-03 (Default Value Efficiency):** To minimize teacher data entry time, the attendance grid shall default all students to "Present", requiring teachers to only mark absent, late, or excused students.
* **FR-ATT-04 (Attendance Summaries):** The system shall automatically compute daily, monthly, and semester percentage attendance rates for each student and section.
* **FR-ATT-05 (Chronic Absence Alerts):** The system shall automatically highlight students whose absence rate exceeds a predefined threshold (e.g., >15% unexcused absences).

---

## 8. Examination and Marks Management

* **FR-EXAM-01 (Assessment Structure Configuration):** Administrators or Registrars shall configure assessment categories and percentage weights per semester. Standard configuration:
  * Continuous Assessment / Quizzes: 30%
  * Midterm Examination: 20%
  * Final Examination: 50%
  * Total: 100%
* **FR-EXAM-02 (Score Validation):** Score entry fields shall enforce strict numerical boundaries:
  * Minimum score: `0.0`
  * Maximum score: Equal to the maximum points allocated to that assessment component (e.g., cannot enter 35 into a 30-point quiz field).
* **FR-EXAM-03 (Controlled Mark Entry):** Teachers can enter and save draft marks, review entries, and officially submit them for registrar verification.
* **FR-EXAM-04 (Automated Grade Calculation):** The system shall compute:
  * Total Subject Score (Sum of all weighted components out of 100).
  * Letter Grade (e.g., A, B, C, D, F) based on the school's configured grading scale.
  * Subject Pass/Fail status.
* **FR-EXAM-05 (Semester Average and Rank):** The system shall calculate:
  * Overall Semester Average for each student.
  * Section Rank (e.g., 1st out of 55 students in Grade 10-A).
  * Grade-level Rank (e.g., 5th out of 350 students across all Grade 10 sections).

---

## 9. Student Promotion Management

* **FR-PROM-01 (Promotion Rule Configuration):** The system shall allow administrators to set dynamic promotion criteria (e.g., Minimum Average >= 50.0% AND number of failed subjects <= 2).
* **FR-PROM-02 (Automated Candidate Evaluation):** At the end of the academic year, the system shall evaluate all students in a grade and categorize them into:
  * `Promoted` (eligible for next grade level)
  * `Retained / Repeat` (failed criteria)
  * `Conditional / Summer Exam` (borderline case requiring review)
* **FR-PROM-03 (Human Review & Override):** Machine recommendations shall never be finalized without human review. The School Principal shall have the explicit authority to review, approve, or manually override a student's promotion status with an attached written rationale.

---

## 10. Reports and Official Records

* **FR-REP-01 (Student Report Card):** The system shall generate a clean, official, printable PDF report card for each student containing:
  * School Header and Student Personal Information
  * Subject scores, letter grades, conduct marks, and teacher remarks
  * Semester Average, Total Score, Section Rank, and Attendance Summary
  * Signature blocks for Homeroom Teacher and Principal
* **FR-REP-02 (Master Roster / Broad Sheet):** Generate printable tabular summary sheets for an entire section listing all students and their subject scores side-by-side for faculty review meetings.
* **FR-REP-03 (Official Academic Transcript):** Generate multi-year academic transcripts showing longitudinal performance from Grade 9 through Grade 12 for graduating students or transfer requests.
* **FR-REP-04 (Ministry Statistics Report):** Generate summary statistics grouped by Grade, Section, and Gender (e.g., Total Male/Female enrollment, pass rates, dropout counts) for educational reporting.

---

## 11. Artificial Intelligence and Analytics Features

* **FR-AI-01 (Academic Risk Prediction):** The system shall use machine learning algorithms (`scikit-learn`) to analyze historical marks and midterm scores to classify students into performance risk categories:
  * `Low Risk` (On track for promotion)
  * `Moderate Risk` (Borderline passing, declining trend)
  * `High Risk` (Projected failure; urgent academic intervention needed)
* **FR-AI-02 (Attendance Pattern Detection):** The AI module shall identify non-obvious absence patterns (e.g., consistent Monday or Friday absences, post-holiday dips, subject-specific skipping).
* **FR-AI-03 (Actionable Academic Recommendations):** The AI system shall generate specific, human-readable suggestions for teachers (e.g., *"Student shows a 25-point drop in Chemistry despite strong Mathematics scores; recommend peer tutoring in stoichiometry modules"*).
* **FR-AI-04 (Ethical Guardrail & Human Oversight):** AI features shall strictly serve as advisory tools. The AI shall never possess permissions to promote, demote, discipline, or alter student records independently.
* **FR-AI-05 (Offline AI School Assistant):** A localized, lightweight conversational assistant powered by internal rule engines or a quantized local model to answer user questions on school schedules, timetables, and academic policies without internet access.

---

## 12. Audit Logs and System Administration

* **FR-AUD-01 (Immutable Audit Logging):** The system shall automatically record an immutable audit log entry whenever critical records are created, updated, or deleted (especially exam marks, student promotions, and user role modifications).
* **FR-AUD-02 (Audit Metadata):** Each log entry must capture:
  * Timestamp (Date and Time)
  * User ID and Username
  * Client IP Address on the local LAN
  * Action Type (`CREATE`, `UPDATE`, `DELETE`, `OVERRIDE`)
  * Old Value vs. New Value
* **FR-AUD-03 (Database Backup):** Administrators shall be able to trigger a complete PostgreSQL database backup from the web interface, producing an encrypted or timestamped `.sql` archive saved to local storage or an external USB drive.
* **FR-AUD-04 (Database Restoration):** The system shall provide documented, safe procedures to restore the database from a backup file in the event of hardware failure.

---

## 13. Functional Flexibility and Configuration

To prevent hard-coding assumptions that might change over time:
* All grading scales, letter grades, and percentage ranges must be stored in database configuration tables.
* Assessment category weights must be editable per academic year.
* Grade levels, sections, and stream titles must be dynamic.
* The system shall allow toggling between 1-semester and 2-semester academic configurations.
