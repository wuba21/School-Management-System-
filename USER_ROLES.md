# User Roles and Permissions Specification

This document defines the four primary user roles in the **Smart School Management and Academic Information System (SSMS)**, their operational responsibilities, and their exact permissions across all system modules.

---

## 1. Role Definitions

### 1.1 School Principal (Executive & Academic Leader)
* **Description:** The chief academic and administrative executive of the school.
* **Core Responsibilities:**
  * High-level institutional oversight and policy execution.
  * Reviewing school-wide academic performance, gender parity, and attendance trends.
  * Final review and formal approval of semester marks and student promotions.
  * Overriding borderline academic or promotion cases when justified.
  * Reviewing audit logs for accountability and fraud prevention.

### 1.2 Registrar (Academic Records & Admissions Officer)
* **Description:** The primary officer responsible for student records, enrollment, class allocations, and official transcripts.
* **Core Responsibilities:**
  * Registering new and transferring students.
  * Managing grade levels, sections, streams, and subject rosters.
  * Assigning enrolled students to specific sections (e.g., Grade 9-A).
  * Mapping teachers to their assigned subjects and sections each academic year.
  * Verifying that teacher mark submissions are complete before term closing.
  * Locking academic terms and generating official report cards and transcripts.

### 1.3 Teacher (Instructional & Evaluative Staff)
* **Description:** Classroom instructors responsible for daily student contact, instruction, and performance evaluation.
* **Core Responsibilities:**
  * Taking daily or period-based attendance for assigned classes.
  * Entering continuous assessment, quiz, midterm, and final examination marks for assigned subjects.
  * Monitoring academic progress and attendance risks of students in their assigned sections.
  * Providing qualitative feedback and conduct remarks for student report cards.
  * Viewing assigned teaching schedules and timetables.

### 1.4 System Administrator (Technical Operations & Security Officer)
* **Description:** The IT professional or designated staff member managing the local computer lab server, network security, and application maintenance.
* **Core Responsibilities:**
  * Creating, updating, and deactivating user accounts.
  * Assigning roles and resetting staff passwords.
  * Performing and verifying daily database backups.
  * Monitoring system performance, server storage, and audit logs.
  * Restoring the database in case of hardware or power failures.
  * Configuring system-wide technical parameters (e.g., LAN IP addresses, backup directories).

---

## 2. Role-Based Permissions Matrix

The table below details CRUD permissions (**C**reate, **R**ead, **U**pdate, **D**elete) across all modules:

| Module / Resource | System Administrator | School Principal | Registrar | Teacher |
| :--- | :---: | :---: | :---: | :---: |
| **System Settings & Server Config** | **CRUD** | **R** | None | None |
| **Database Backup & Restore** | **CRUD** | None | None | None |
| **Audit Logs** | **R** (Full Audit) | **R** (Summary) | None | None |
| **Staff & User Accounts** | **CRUD** | **R** | **R** | Self (Profile Only) |
| **Academic Years & Terms** | **CRUD** | **R** | **CRUD** | **R** |
| **Grades, Sections & Streams** | **CRUD** | **R** | **CRUD** | **R** (Assigned Only) |
| **Subject Catalog** | **CRUD** | **R** | **CRUD** | **R** |
| **Teacher Profiles & Allocations** | **CRUD** | **R** | **CRUD** | **R** (Self Only) |
| **Student Profiles & Records** | **R** (Emergency) | **R** (All) | **CRUD** | **R** (Assigned Classes) |
| **Student Class Enrollment** | None | **R** | **CRUD** | **R** (Assigned Classes) |
| **Daily Attendance** | None | **R** (Aggregates) | **R** (Reports) | **CRUD** (Assigned Classes) |
| **Timetable Scheduling** | **CRUD** | **R** | **CRUD** | **R** (View Schedule) |
| **Exam Setup & Assessment Rules**| **CRUD** | **R** | **CRUD** | **R** |
| **Mark Entry (Drafts & Edits)** | None | **R** | **R** (Verification)| **CRUD** (Assigned Classes)* |
| **Mark Finalization / Term Lock**| None | **Approve / Lock**| **Prepare / Lock** | None |
| **Student Promotion Processing** | None | **Final Approval**| **Process List** | **R** (Recommendations) |
| **Report Cards & Transcripts** | None | **R / Print** | **Generate / Print**| **R / Print** (Own Class)|
| **AI Academic Risk Analytics** | Technical Setup | **Full Executive View**| **Operational View**| **Class-Level View** |
| **AI Attendance Pattern Insights**| Technical Setup | **Full Executive View**| **Operational View**| **Class-Level View** |
| **AI Conversational Assistant** | Technical Setup | **Enabled** | **Enabled** | **Enabled** |

*\*Note on Mark Entry: Teachers may only create and update marks during the active assessment submission window. Once a term or assessment is marked "Locked" or "Approved" by the Registrar/Principal, marks become read-only for teachers.*

---

## 3. Separation of Duties and Security Controls

To preserve academic integrity and prevent administrative fraud:
1. **No Single User Can Act Alone on Marks:**
   * Teachers enter draft marks.
   * Registrars verify completeness and calculate statistical averages.
   * The Principal provides final authorization to publish marks.
2. **Promotion Safeguard:**
   * The AI engine and system rules flag students eligible or ineligible for promotion based on rules.
   * The Registrar generates the candidate list.
   * The Principal must explicitly approve the promotion list.
3. **No Academic Tampering by IT Staff:**
   * The System Administrator has technical permissions to manage user accounts and database backups, but **cannot edit student marks or attendance** through the user interface.
4. **Audit Trail Accountability:**
   * Any change made to a student's finalized mark produces an un-deletable audit log specifying who requested the change, who made the edit, the old value, the new value, and the timestamp.
