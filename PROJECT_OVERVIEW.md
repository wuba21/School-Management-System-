# Project Overview

## 1. Project Title
**Smart School Management and Academic Information System (SSMS)**  
*An AI-Powered, Offline-First Local Area Network (LAN) Solution for Secondary Schools*

---

## 2. Project Background
This project is designed for a real public secondary school located in **Majang Zone, Gambella Region, Ethiopia**. 

The school environment has the following key characteristics:
* **Academic Level:** Secondary education covering **Grades 9 through 12**.
* **Student Population:** Estimated between **1,000 and 2,000 students**.
* **Teaching Staff:** Approximately **40 to 80 teachers** and administrative personnel.
* **Computer Infrastructure:** Over **20 desktop computers** located in computer laboratories and administrative offices.
* **Network Infrastructure:** The computers are interconnected via a **Local Area Network (LAN)** using local switches and Ethernet cables.
* **Connectivity Challenges:** External internet connectivity is intermittent, slow, or frequently unavailable.
* **Current Operational Practice:**
  * Student personal information is stored in paper folders and physical logbooks.
  * Daily student attendance is taken on paper rosters.
  * Examination results, marks, and semester grades are tabulated manually on paper sheets.
  * Report cards and transcripts are hand-written.
* **Financial Model:** As a government public secondary school, the school **does not collect tuition fees**. Consequently, financial accounting and billing modules are not needed; the entire focus is on academic, student, and administrative excellence.

---

## 3. Problem Statement
The current manual, paper-based workflow creates several major operational bottlenecks:
1. **Risk of Data Loss and Damage:** Physical paper records are vulnerable to fire, water damage, termites, humidity, and accidental loss.
2. **Time-Consuming Administration:** Teachers and registrars spend hundreds of hours manually calculating averages, ranks, and writing report cards at the end of each semester.
3. **Calculation Errors:** Manual grade summation, average computation, and rank determination frequently lead to human errors.
4. **Lack of Early Warning for At-Risk Students:** Because attendance and marks are scattered across individual paper books, administrators cannot easily detect chronic absenteeism or failing academic trends until the semester has already ended.
5. **Slow Information Retrieval:** Finding a student's past academic transcript from several years ago requires manually searching through physical paper archives.
6. **Internet Dependency of Commercial Software:** Existing commercial school management systems depend on continuous cloud access, rendering them unusable during frequent regional internet outages.

---

## 4. General Objective
To design, develop, and deploy a secure, robust, user-friendly, and offline-capable School Management and Academic Information System that operates reliably over the school's Local Area Network (LAN) without requiring continuous internet access, augmented with artificial intelligence tools for academic analysis and decision support.

---

## 5. Specific Objectives
1. **Digitize Student and Teacher Records:** Provide a centralized, searchable database for student admissions, personal profiles, and teacher allocations.
2. **Automate Academic Structure:** Configure academic years, semesters, grades (9–12), sections, streams (Natural Science and Social Science), and subjects.
3. **Streamline Daily Attendance:** Enable teachers to record attendance in seconds through local network browsers and generate absence alerts.
4. **Automate Examination and Result Management:** Allow teachers to enter continuous assessment and exam marks, and have the system automatically compute totals, averages, letter grades, and ranks.
5. **Automate Report Generation:** Generate professional, printable student report cards, semester rosters, and student transcripts with one click.
6. **Provide Intelligent Academic Analytics:** Utilize machine learning algorithms (using Python, Pandas, and Scikit-learn) to identify students needing academic assistance, detect absenteeism patterns, and generate actionable recommendations for educators.
7. **Deploy on Local Network (Offline-First):** Bundle all frontend libraries (Bootstrap, Chart.js) and backend services so that the entire school can use the system 100% offline via LAN.
8. **Enforce Role-Based Access Control and Security:** Protect student data through role-specific permissions (Principal, Registrar, Teacher, Administrator) and comprehensive audit logging.

---

## 6. Project Scope

### In Scope
* User authentication and role-based access control.
* Academic year and semester management.
* Grade level (9–12), section, and stream (Natural / Social Science) configuration.
* Student registration, profile management, and class enrollment.
* Teacher profile management and subject/section assignment.
* Weekly timetable creation and schedule viewing.
* Attendance tracking and chronic absence analysis.
* Examination definition, mark entry, grade calculation, and rank generation.
* Automated promotion and repetition evaluation.
* Generation of printable PDF report cards and official academic transcripts.
* Comprehensive audit logging for sensitive actions (e.g., mark changes).
* Automated local database backup and recovery.
* Machine learning analysis for student risk detection and attendance correlation.
* Offline AI conversational assistant for school procedures and rules.

### Out of Scope
* Tuition fee collection, invoice generation, or financial payment gateways (school does not charge tuition).
* Online student/parent self-registration portals requiring external internet connectivity.
* SMS or internet email notifications (due to regional infrastructure constraints; local dashboard alerts are used instead).
* Automated biometric hardware integrations in the initial release (can be added as a future upgrade).

---

## 7. Expected Outcomes
* **Zero Paper Loss:** Permanent, secure digital preservation of all student and academic data.
* **Instant Academic Computation:** Elimination of manual calculation errors in student averages, percentiles, and class ranks.
* **Rapid Report Card Issuance:** End-of-semester report cards produced in minutes rather than weeks.
* **Data-Driven Interventions:** Timely identification of students struggling academically or exhibiting high absence rates before final exams.
* **Resilient Infrastructure:** Reliable, uninterrupted day-to-day operations regardless of regional power fluctuations or external internet blackouts.

---

## 8. Requirements Needing Confirmation with School Staff
During the planning phase, the following operational details have been identified as requiring formal confirmation by the School Principal and Department Heads:

| Item | Preliminary Assumption | Needs Confirmation From School |
| :--- | :--- | :--- |
| **Calendar System** | System displays Gregorian dates and supports Ethiopian academic year notation (e.g., 2016/2017 E.C.). | Does the school require native Ge'ez calendar date input or standard Ethiopian fiscal/academic year labels? |
| **Assessment Breakdown** | 30% Continuous Assessment (quizzes/tests), 20% Midterm Exam, 50% Final Exam = 100%. | Exact percentage breakdown approved by the Regional Education Bureau. |
| **Passing Mark & Promotion** | Passing threshold is an overall semester average of 50%, with no more than 2 failing subjects. | Exact minimum score required for promotion from Grade 9 to 10, 10 to 11, and 11 to 12. |
| **Subject List by Stream** | Standard national curriculum for Grades 9–10, and split Natural/Social science subjects for 11–12. | Specific local elective subjects or regional language offerings (e.g., Majang language, Anywaa, Nuer, or Amharic). |
| **Student ID Numbering** | Auto-generated alphanumeric format: `SSMS/YEAR/XXXX` (e.g., `SSMS/2026/0001`). | Existing manual student registration numbering convention used by the school. |
