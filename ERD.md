# Entity-Relationship Diagram (ERD)

**Project:** Smart School Management and Academic Information System (SSMS)  
**School Scope:** Grades 9–12, Majang Zone, Gambella Region, Ethiopia  

---

## 1. Complete Mermaid Entity-Relationship Diagram

```mermaid
erDiagram
    ROLE ||--o{ USER : "categorizes"
    USER ||--o| TEACHER : "authenticates"
    USER ||--o{ AUDIT_LOG : "triggers"
    USER ||--o{ PROMOTION_RECORD : "approves"
    USER ||--o{ MARK : "enters"

    ACADEMIC_YEAR ||--o{ CLASS_OFFERING : "schedules"
    ACADEMIC_YEAR ||--o{ STUDENT_ENROLLMENT : "encompasses"
    ACADEMIC_YEAR ||--o{ EXAMINATION : "holds"
    ACADEMIC_YEAR ||--o{ PROMOTION_RECORD : "transitions_from"
    ACADEMIC_YEAR ||--o{ PROMOTION_RECORD : "transitions_to"

    GRADE ||--o{ CLASS_OFFERING : "specifies"
    GRADE ||--o{ CURRICULUM_SUBJECT : "mandates"
    GRADE ||--o{ EXAM_SUBJECT : "scopes"
    GRADE ||--o{ PROMOTION_RECORD : "promotes_from"
    GRADE ||--o{ PROMOTION_RECORD : "promotes_to"

    SECTION ||--o{ CLASS_OFFERING : "allocates"
    STREAM ||--o{ CLASS_OFFERING : "specializes"
    STREAM ||--o{ CURRICULUM_SUBJECT : "specializes"
    STREAM ||--o{ EXAM_SUBJECT : "specializes"

    SUBJECT ||--o{ CURRICULUM_SUBJECT : "defines"
    SUBJECT ||--o{ TEACHER_ASSIGNMENT : "taught_as"
    SUBJECT ||--o{ EXAM_SUBJECT : "examined_in"

    CLASS_OFFERING ||--o{ TEACHER_ASSIGNMENT : "assigned_to"
    CLASS_OFFERING ||--o{ STUDENT_ENROLLMENT : "enrolls"
    CLASS_OFFERING ||--o{ ATTENDANCE_SESSION : "conducts"

    TEACHER ||--o{ TEACHER_ASSIGNMENT : "conducts"
    TEACHER ||--o{ ATTENDANCE_SESSION : "records"

    STUDENT ||--o{ STUDENT_ENROLLMENT : "enrolled_in"
    STUDENT ||--o{ PROMOTION_RECORD : "evaluated_for"

    STUDENT_ENROLLMENT ||--o{ ATTENDANCE_RECORD : "marked_in"
    STUDENT_ENROLLMENT ||--o{ MARK : "evaluated_in"

    ATTENDANCE_SESSION ||--o{ ATTENDANCE_RECORD : "contains"

    EXAMINATION ||--o{ EXAM_SUBJECT : "contains"
    EXAM_SUBJECT ||--o{ MARK : "assessed_by"

    %% Entity Field Definitions
    ROLE {
        bigint id PK
        string code UK
        string name
        boolean is_active
    }

    USER {
        bigint id PK
        string username UK
        string email
        bigint role_id FK
        string phone_number
        boolean is_active
    }

    TEACHER {
        bigint id PK
        bigint user_id FK,UK
        string employee_id UK
        string first_name
        string father_name
        string qualification
        string specialization
        date joining_date
    }

    STUDENT {
        bigint id PK
        string admission_number UK
        string first_name
        string father_name
        string grandfather_name
        string gender
        date date_of_birth
        string status
    }

    ACADEMIC_YEAR {
        bigint id PK
        string name UK
        string code UK
        date start_date
        date end_date
        boolean is_current
        boolean is_closed
    }

    GRADE {
        bigint id PK
        string name UK
        smallint level UK
    }

    SECTION {
        bigint id PK
        string name UK
    }

    STREAM {
        bigint id PK
        string code UK
        string name
    }

    SUBJECT {
        bigint id PK
        string code UK
        string name
        boolean is_active
    }

    CURRICULUM_SUBJECT {
        bigint id PK
        bigint grade_id FK
        bigint stream_id FK
        bigint subject_id FK
        smallint credit_hours
        boolean is_elective
    }

    CLASS_OFFERING {
        bigint id PK
        bigint academic_year_id FK
        bigint grade_id FK
        bigint section_id FK
        bigint stream_id FK
        smallint max_capacity
    }

    TEACHER_ASSIGNMENT {
        bigint id PK
        bigint teacher_id FK
        bigint class_offering_id FK
        bigint subject_id FK
        boolean is_primary
    }

    STUDENT_ENROLLMENT {
        bigint id PK
        bigint student_id FK
        bigint class_offering_id FK
        bigint academic_year_id FK
        date enrollment_date
        string status
    }

    ATTENDANCE_SESSION {
        bigint id PK
        bigint class_offering_id FK
        date date
        string session_type
        bigint recorded_by_id FK
    }

    ATTENDANCE_RECORD {
        bigint id PK
        bigint attendance_session_id FK
        bigint student_enrollment_id FK
        string status
        string reason
    }

    EXAMINATION {
        bigint id PK
        bigint academic_year_id FK
        string semester
        string name
        date start_date
        date end_date
        boolean is_locked
    }

    EXAM_SUBJECT {
        bigint id PK
        bigint examination_id FK
        bigint grade_id FK
        bigint stream_id FK
        bigint subject_id FK
        decimal max_marks
        decimal pass_marks
        decimal weight_percentage
    }

    MARK {
        bigint id PK
        bigint student_enrollment_id FK
        bigint exam_subject_id FK
        decimal marks_obtained
        boolean is_absent
        bigint entered_by_id FK
    }

    PROMOTION_RECORD {
        bigint id PK
        bigint student_id FK
        bigint from_academic_year_id FK
        bigint to_academic_year_id FK
        bigint from_grade_id FK
        bigint to_grade_id FK
        string decision
        decimal average_mark
        bigint approved_by_id FK
    }

    AUDIT_LOG {
        bigint id PK
        bigint actor_id FK
        string action
        string entity_name
        string record_id
        inet ip_address
        jsonb changes_json
        timestamp timestamp
    }
```

---

## 2. Key Relationship Explanations

1. **Academic Year & Class Offerings (`1 : M`):**
   * An academic year (e.g., 2026/2027) establishes multiple `ClassOffering` instances (e.g., Grade 9-A, Grade 9-B, Grade 11-A Natural Science, Grade 11-B Social Science).
2. **Student & Historical Enrollment (`1 : M`):**
   * A `Student` is enrolled in exactly one `ClassOffering` per academic year via `StudentEnrollment`. When the student advances from Grade 9 to Grade 10 next year, a new enrollment record is added, preserving the Grade 9 enrollment forever.
3. **Teacher Allocations (`M : M` through `TeacherAssignment`):**
   * Teachers are mapped to specific subjects in specific class offerings, allowing a teacher to teach Physics to Grade 10-A, 10-B, and 11-A.
4. **Attendance Tracking (`1 : M` Session to Records):**
   * An `AttendanceSession` represents a single roll-call event. It contains one `AttendanceRecord` per enrolled student.
5. **Examinations & Mark Entries (`1 : M` and Junctions):**
   * An `Examination` contains multiple `ExamSubject` rows (e.g., Grade 10 Chemistry, max marks 100).
   * A `Mark` joins an individual `StudentEnrollment` with an `ExamSubject`.
6. **Promotion & Academic Progress (`1 : M`):**
   * `PromotionRecord` captures the year-end transition, storing the decision (`PROMOTED`, `RETAINED`, `GRADUATED`), final average, and Principal authorization.
