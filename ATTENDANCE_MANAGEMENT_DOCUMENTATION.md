# SSMS — STEP 11: ATTENDANCE MANAGEMENT SYSTEM DOCUMENTATION

**Project:** Smart School Management and Academic Information System (SSMS)  
**Target School:** Secondary School in Majang Zone, Gambella Region, Ethiopia  
**School Levels:** Grades 9–12  
**Deployment:** Offline Local Area Network (LAN)  
**Date:** November 2026  

---

## 1. System Overview

The Attendance Management System replaces error-prone paper roll-call registers with an intuitive, offline-first digital attendance workflow designed specifically for secondary school operations in Majang Zone. 

### Key Capabilities:
- **Fast Roll-Call Entry:** Teachers can record an entire classroom of up to 50 students in under 30 seconds using interactive quick-fill controls (All Present, All Absent, All Late) with full manual override per student.
- **Configurable Sessions:** Supports full-day roll calls, morning/afternoon split periods, or subject-specific period attendance.
- **Historical Longitudinal Tracking:** Preserves multi-year attendance records across grade promotions and academic transitions.
- **Visual Analytics:** Interactive Chart.js graphs displaying 7-day school-wide attendance trends and grade-level comparisons.
- **Early-Warning Pastoral Alerts:** Non-punitive monitoring for chronic absenteeism (< 75% rate) and consecutive unexcused absences (3+ days) to trigger timely academic guidance and counseling.
- **Offline Exports:** Complete export engine producing Microsoft Excel (`.xlsx`) via OpenPyXL and print-ready PDF reports via ReportLab without any external internet dependency.

---

## 2. Database Architecture & Relationships

```
+-------------------------------------------------------------+
|                       AcademicYear                          |
|  - code: "AY-2026"                                          |
|  - is_current: True / False                                 |
|  - is_closed: True / False                                  |
+------------------------------+------------------------------+
                               | 1
                               | 
                               | *
+------------------------------v------------------------------+
|                       ClassOffering                         |
|  - grade (Grade 9 - 12)                                     |
|  - section (A, B, C...)                                     |
|  - stream (Optional: Natural / Social Science)              |
+------------------------------+------------------------------+
                               | 1
                               |
                               | *
+------------------------------v------------------------------+
|                     AttendanceSession                       |
|  - academic_year: FK -> AcademicYear                        |
|  - class_offering: FK -> ClassOffering                      |
|  - date: DateField (defaults to today)                      |
|  - session_type: DAILY | MORNING | AFTERNOON | PERIOD        |
|  - subject: FK -> Subject (optional)                        |
|  - recorded_by: FK -> Teacher (assigned faculty)            |
|  - created_by: FK -> User (initiator)                       |
|  - status: OPEN | SUBMITTED | CLOSED                        |
|  - remarks: CharField                                       |
+------------------------------+------------------------------+
                               | 1
                               |
                               | *
+------------------------------v------------------------------+
|                     AttendanceRecord                        |
|  - attendance_session: FK -> AttendanceSession              |
|  - student_enrollment: FK -> StudentEnrollment              |
|  - status: PRESENT | ABSENT | LATE | EXCUSED                |
|  - reason: CharField (reason for absence or tardiness)      |
|  - recorded_by: FK -> User                                  |
|  - created_at / updated_at: DateTimeField                   |
+-------------------------------------------------------------+
```

### Constraints & Data Integrity:
1. **Unique Session Constraint:** Prevent duplicate sessions for the same class offering, date, session type, and subject.
2. **Unique Student Mark Constraint:** `UniqueConstraint(fields=['attendance_session', 'student_enrollment'])` prevents duplicate marks for a student in the same session. Submitting updates existing marks.
3. **Classroom Enrollment Check:** `clean()` ensures that students marked in a session are actively enrolled in that session's `ClassOffering`.
4. **Closed Period Immutability:** When an `AcademicYear` or `AttendanceSession` is closed, modifications are blocked.

---

## 3. How Teachers Record Attendance

1. **Accessing the Classroom:**
   - Log in with Teacher credentials (e.g. `teacher_abebe`).
   - Navigate to the **Attendance Dashboard** (`/attendance/`).
   - Teachers see their assigned classrooms prominently under **My Assigned Classrooms**.
2. **Initiating Roll Call:**
   - Click **Take Attendance** on the desired classroom card, or click **New Roll-Call Session**.
   - Select the date and session type (defaults to Today and Full Day).
   - Click **Open & Start Roll-Call**.
3. **Marking Attendance:**
   - The interactive roll-call grid displays student portraits, names, and admission numbers.
   - Use the **Quick Fill** toolbar (e.g. click `All Present` to mark the entire class).
   - Toggle individual students to `Absent`, `Late`, or `Excused` as needed.
   - Optionally enter an excuse note or reason in the text box.
   - Click **Save Roll-Call Records**.
4. **Confirmation:**
   - The system displays a confirmation banner detailing exact counts (e.g. `45 Present, 3 Absent, 2 Late`).
   - The session status updates to **Submitted**.

---

## 4. How Authorized Users Correct Attendance

1. **Open / Submitted Sessions:**
   - Assigned teachers and administrative staff can reopen the session sheet and edit statuses directly.
   - Submitting updates existing rows and logs an audit trail in `AuditLog`.
2. **Closed / Locked Sessions:**
   - To protect historical integrity, sessions can be locked by School Administration (`Close Session`).
   - Only **Registrars** or **System Administrators** can unlock closed sessions by clicking **Reopen Session**.

---

## 5. Attendance Percentage Calculation

In alignment with educational administration standards:
- **Attended Sessions:** `Present + Late` arrivals.
- **Unattended Sessions:** `Absent + Excused`.
- **Attendance Percentage Formula:**
  $$\text{Attendance Rate (\%)} = \left(\frac{\text{Present Count} + \text{Late Count}}{\text{Total Sessions Recorded}}\right) \times 100$$
- If no sessions have been recorded, the percentage safely displays `0.0%` (or `None` in student profiles).

---

## 6. Role-Based Access Control (RBAC)

| Role | Dashboard | View Own Classes | View All School | Create / Record | Close Session | Reopen Session | View Alerts | Export Reports |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Teacher** | Assigned Only | Yes | No | Assigned Only | No | No | No | Assigned Only |
| **Registrar** | School-wide | Yes | Yes | All Classes | Yes | Yes | Yes | Yes |
| **Principal** | School-wide | Yes | Yes | Read-Only | Yes | Yes | Yes | Yes |
| **Administrator**| School-wide | Yes | Yes | All Classes | Yes | Yes | Yes | Yes |

---

## 7. Reporting & Data Export

Located under `/attendance/reports/`:
- **Daily Classroom Summaries:** Real-time present/absent counts per grade and section.
- **Class-Level Analytical Reports:** Aggregated sessions, total presents, absents, tardies, and attendance rates.
- **Longitudinal Student Attendance Profile:** Accessible from `/attendance/students/<id>/` or via the student master record.
- **Excel Export:** Generates standardized, formatted `.xlsx` workbooks with auto-adjusted column widths and navy headers.
- **PDF Export:** Generates printable landscape PDF documents via ReportLab with school crest and official tabular layout.

---

## 8. Verification & Test Execution

Run the complete attendance test suite:

```bash
python manage.py test attendance --verbosity=2
```

Expected output:
```
Ran 14 tests in ...
OK
```
