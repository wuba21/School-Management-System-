from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.db import transaction
from datetime import date
from decimal import Decimal

from accounts.models import Role, User
from academics.models import AcademicYear, Grade, Section, Stream, Subject, CurriculumSubject, ClassOffering
from teachers.models import Teacher, TeacherAssignment
from students.models import Student, StudentEnrollment, PromotionRecord
from attendance.models import AttendanceSession, AttendanceRecord
from examinations.models import Examination, ExamSubject
from results.models import Mark
from core.models import AuditLog


class DatabaseIntegrityAndModelTests(TestCase):
    """
    Comprehensive test suite verifying database architecture, 
    relationships, unique constraints, and business logic validations.
    """

    def setUp(self):
        # 1. Setup Roles and Users
        self.role_teacher = Role.objects.create(code='TEACHER', name='Teacher')
        self.role_principal = Role.objects.create(code='PRINCIPAL', name='School Principal')
        
        self.user_teacher = User.objects.create_user(
            username='teacher_abebe',
            password='TestPassword123!',
            role=self.role_teacher
        )
        self.user_principal = User.objects.create_user(
            username='principal_kebede',
            password='TestPassword123!',
            role=self.role_principal
        )

        # 2. Setup Academic Structure
        self.year_2026 = AcademicYear.objects.create(
            name='2026/2027 (2018/2019 E.C.)',
            code='AY-2026',
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_current=True
        )
        self.grade_10 = Grade.objects.create(name='Grade 10', level=10)
        self.section_a = Section.objects.create(name='A')
        self.stream_general = Stream.objects.create(code='GENERAL', name='General Secondary')
        
        self.class_10a = ClassOffering.objects.create(
            academic_year=self.year_2026,
            grade=self.grade_10,
            section=self.section_a,
            stream=self.stream_general,
            max_capacity=50
        )

        self.subject_math = Subject.objects.create(code='MATH-10', name='Mathematics')
        self.curriculum = CurriculumSubject.objects.create(
            grade=self.grade_10,
            stream=self.stream_general,
            subject=self.subject_math,
            credit_hours=4
        )

        # 3. Setup Teacher & Assignment
        self.teacher = Teacher.objects.create(
            user=self.user_teacher,
            employee_id='EMP-1001',
            first_name='Abebe',
            father_name='Bikila',
            gender='M',
            qualification='B.Ed in Mathematics',
            specialization='Mathematics',
            joining_date=date(2020, 9, 1)
        )
        self.assignment = TeacherAssignment.objects.create(
            teacher=self.teacher,
            class_offering=self.class_10a,
            subject=self.subject_math
        )

        # 4. Setup Student & Enrollment
        self.student = Student.objects.create(
            admission_number='SSMS/2026/0001',
            first_name='Chaltu',
            father_name='Tolessa',
            grandfather_name='Gemechu',
            gender='F',
            date_of_birth=date(2010, 5, 12),
            address='Godere Woreda, Majang Zone',
            emergency_contact_name='Tolessa Gemechu',
            emergency_contact_phone='0911223344',
            emergency_contact_relation='Father'
        )
        self.enrollment = StudentEnrollment.objects.create(
            student=self.student,
            class_offering=self.class_10a,
            academic_year=self.year_2026
        )

    def test_student_ethiopian_three_part_naming(self):
        """Verify student full name construction follows Ethiopian three-part convention."""
        self.assertEqual(self.student.full_name, 'Chaltu Tolessa Gemechu')
        self.assertEqual(str(self.student), 'Chaltu Tolessa Gemechu (SSMS/2026/0001)')

    def test_unique_student_admission_number(self):
        """Verify duplicate admission numbers are rejected."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Student.objects.create(
                    admission_number='SSMS/2026/0001',  # Duplicate
                    first_name='Almaz',
                    father_name='Hailu',
                    grandfather_name='Desta',
                    gender='F',
                    date_of_birth=date(2010, 8, 1),
                    emergency_contact_name='Hailu Desta',
                    emergency_contact_phone='0922334455',
                    emergency_contact_relation='Father'
                )

    def test_unique_enrollment_per_academic_year(self):
        """Verify a student cannot have multiple enrollments in the same academic year."""
        section_b = Section.objects.create(name='B')
        class_10b = ClassOffering.objects.create(
            academic_year=self.year_2026,
            grade=self.grade_10,
            section=section_b,
            stream=self.stream_general
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StudentEnrollment.objects.create(
                    student=self.student,
                    class_offering=class_10b,
                    academic_year=self.year_2026  # Duplicate enrollment for 2026
                )

    def test_attendance_session_and_record_constraints(self):
        """Verify attendance session and duplicate record prevention."""
        session = AttendanceSession.objects.create(
            class_offering=self.class_10a,
            date=date(2026, 10, 15),
            session_type='DAILY',
            recorded_by=self.teacher
        )
        # Create first attendance record
        record1 = AttendanceRecord.objects.create(
            attendance_session=session,
            student_enrollment=self.enrollment,
            status='PRESENT'
        )
        self.assertEqual(record1.status, 'PRESENT')

        # Attempting duplicate attendance record for the same student in the same session must fail
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AttendanceRecord.objects.create(
                    attendance_session=session,
                    student_enrollment=self.enrollment,
                    status='ABSENT'
                )

    def test_examination_and_mark_boundary_validation(self):
        """Verify mark validation bounds (cannot exceed max_marks, cannot be duplicate)."""
        exam = Examination.objects.create(
            academic_year=self.year_2026,
            semester='SEM1',
            name='Semester 1 Midterm Exam',
            start_date=date(2026, 11, 10),
            end_date=date(2026, 11, 20)
        )
        exam_subject = ExamSubject.objects.create(
            examination=exam,
            grade=self.grade_10,
            stream=self.stream_general,
            subject=self.subject_math,
            max_marks=Decimal('30.00'),
            pass_marks=Decimal('15.00'),
            weight_percentage=Decimal('30.00')
        )

        # Valid mark entry
        mark = Mark.objects.create(
            student_enrollment=self.enrollment,
            exam_subject=exam_subject,
            marks_obtained=Decimal('25.50'),
            entered_by=self.user_teacher
        )
        self.assertEqual(mark.marks_obtained, Decimal('25.50'))

        # Duplicate mark entry for same exam subject must fail validation
        with self.assertRaises((IntegrityError, ValidationError)):
            with transaction.atomic():
                Mark.objects.create(
                    student_enrollment=self.enrollment,
                    exam_subject=exam_subject,
                    marks_obtained=Decimal('20.00')
                )

        # Score exceeding max_marks must be caught by clean() validation
        invalid_mark = Mark(
            student_enrollment=self.enrollment,
            exam_subject=exam_subject,
            marks_obtained=Decimal('35.00')  # Max is 30.00
        )
        with self.assertRaises(ValidationError):
            invalid_mark.full_clean()

    def test_promotion_record_preservation(self):
        """Verify academic progression preserves historical records without data loss."""
        year_2027 = AcademicYear.objects.create(
            name='2027/2028 (2019/2020 E.C.)',
            code='AY-2027',
            start_date=date(2027, 9, 1),
            end_date=date(2028, 6, 30),
            is_current=False
        )
        grade_11 = Grade.objects.create(name='Grade 11', level=11)

        promotion = PromotionRecord.objects.create(
            student=self.student,
            from_academic_year=self.year_2026,
            to_academic_year=year_2027,
            from_grade=self.grade_10,
            to_grade=grade_11,
            decision='PROMOTED',
            average_mark=Decimal('82.50'),
            rank_in_section=3,
            approved_by=self.user_principal
        )
        self.assertEqual(promotion.decision, 'PROMOTED')
        self.assertEqual(self.student.enrollments.count(), 1)
        self.assertEqual(self.student.promotion_records.count(), 1)

    def test_audit_log_creation(self):
        """Verify audit trail logging."""
        log = AuditLog.objects.create(
            actor=self.user_teacher,
            action='UPDATE',
            entity_name='Mark',
            record_id='101',
            ip_address='192.168.1.55',
            changes_json={'old_score': 20.0, 'new_score': 25.5}
        )
        self.assertEqual(log.actor.username, 'teacher_abebe')
        self.assertEqual(log.action, 'UPDATE')
        self.assertIn('192.168.1.55', str(log.ip_address))


class UITemplateAndNavigationTests(TestCase):
    """
    Test suite verifying that all UI templates, sidebar navigation routes,
    login page, and static assets render cleanly with HTTP 200.
    """

    def setUp(self):
        self.client = TestCase.client_class()
        # Create an administrative user to test protected navigation routes
        self.admin_role = Role.objects.create(code='ADMIN', name='System Administrator')
        self.admin_user = User.objects.create_superuser(
            username='admin_tester',
            password='TestPassword123!',
            email='admin@school.test',
            role=self.admin_role
        )

    def test_login_page_renders_cleanly(self):
        """Verify the login page renders with all required form controls."""
        response = self.client.get('/login/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'SSMS Portal')
        self.assertContains(response, 'Staff Authentication')
        self.assertContains(response, 'usernameInput')
        self.assertContains(response, 'passwordInput')
        self.assertContains(response, 'togglePasswordBtn')
        self.assertContains(response, 'rememberMeCheck')

    def test_dashboard_renders_with_kpis_and_charts(self):
        """Verify the dashboard page renders with KPI metrics and Chart.js canvases when logged in."""
        self.client.login(username='admin_tester', password='TestPassword123!')
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Total Students')
        self.assertContains(response, 'Total Teachers')
        self.assertContains(response, 'Academic Year')
        self.assertContains(response, 'Today\'s Attendance')
        self.assertContains(response, 'enrollmentChart')
        self.assertContains(response, 'attendanceChart')

    def test_all_sidebar_navigation_routes(self):
        """Verify every single sidebar navigation item resolves and loads for authenticated admin."""
        self.client.login(username='admin_tester', password='TestPassword123!')
        # Routes expected to return HTTP 200
        routes_200 = [
            '/',
            '/dashboard/',
            '/students/',
            '/teachers/',
            '/academics/years/',
            '/academics/grades/',
            '/academics/subjects/',
            '/attendance/',
            '/examinations/',
            '/results/',
            '/promotion/',
            '/timetable/',
            '/reports/students/',
            '/reports/academic/',
            '/reports/attendance/',
            '/ai-assistant/',
            '/ai-assistant/analytics/',
            '/settings/',
            '/audit/',
        ]
        # Routes that redirect (e.g. /system/users/ → /users/)
        routes_302 = [
            '/system/users/',
        ]
        for url in routes_200:
            with self.subTest(route=url):
                response = self.client.get(url)
                self.assertEqual(
                    response.status_code,
                    200,
                    f"Expected HTTP 200 for route '{url}', got {response.status_code}"
                )
        for url in routes_302:
            with self.subTest(route=url):
                response = self.client.get(url)
                self.assertIn(
                    response.status_code,
                    [200, 302],
                    f"Expected HTTP 200 or 302 for redirect route '{url}', got {response.status_code}"
                )

    def test_static_asset_links_in_base_template(self):
        """Verify that offline vendor assets (Bootstrap, Icons, Chart.js) are referenced."""
        self.client.login(username='admin_tester', password='TestPassword123!')
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'vendor/bootstrap/css/bootstrap.min.css')
        self.assertContains(response, 'vendor/bootstrap-icons/bootstrap-icons.css')
        self.assertContains(response, 'vendor/bootstrap/js/bootstrap.bundle.min.js')
        self.assertContains(response, 'vendor/chartjs/chart.umd.min.js')
        self.assertContains(response, 'css/styles.css')
        self.assertContains(response, 'js/main.js')


class SystemWideIntegrationWorkflowTests(TestCase):
    """
    Phase 2 Integration Verification:
    Executes a 14-step realistic academic workflow on synthetic data,
    validating the 10 core cross-module integrations:
      1. Student Management <-> Academic Management
      2. Teacher Management <-> Academic Management
      3. Academic Management <-> Attendance Management
      4. Academic Management <-> Examination Management
      5. Examination Management <-> Student Promotion
      6. Teacher Management <-> Timetable Management
      7. Attendance Management <-> School Analytics
      8. Examination Management <-> School Analytics
      9. Student Promotion <-> Student Academic History
      10. Authentication <-> All Applications
    """

    def test_full_14_step_academic_workflow(self):
        from datetime import time
        from timetable.models import Timetable, Period, SchoolDay, TimetableEntry
        from promotion.models import PromotionBatch, PromotionCriteria, PromotionRecord as BatchPromotionRecord
        from reports.services import AnalyticsService, StudentReportService, ExaminationPerformanceReportService

        # STEP 1: Academic Year creation
        year1 = AcademicYear.objects.create(
            name='2026/2027 (2018/2019 E.C.)',
            code='AY-2026-INT',
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_current=True
        )
        year2 = AcademicYear.objects.create(
            name='2027/2028 (2019/2020 E.C.)',
            code='AY-2027-INT',
            start_date=date(2027, 9, 1),
            end_date=date(2028, 6, 30),
            is_current=False
        )

        # STEP 2: Grades, Sections, and Subjects
        grade9 = Grade.objects.create(name='Grade 9', level=9)
        grade10 = Grade.objects.create(name='Grade 10', level=10)
        section_a = Section.objects.create(name='A')
        subject_math = Subject.objects.create(name='Mathematics', code='MATH-INT')
        subject_eng = Subject.objects.create(name='English', code='ENG-INT')

        # STEP 3: Register Teacher
        teacher_role, _ = Role.objects.get_or_create(code='TEACHER', defaults={'name': 'Teacher'})
        teacher_user = User.objects.create_user(
            username='teacher_chala_int',
            password='Password123!',
            role=teacher_role,
            first_name='Chala',
            last_name='Tolosa'
        )
        teacher = Teacher.objects.create(
            user=teacher_user,
            employee_id='EMP-INT-001',
            first_name='Chala',
            father_name='Tolosa',
            grandfather_name='Geda',
            gender='MALE',
            joining_date=date(2020, 9, 1),
            qualification='B.Ed Mathematics'
        )

        # STEP 4: Register Students (Ethiopian three-part names)
        student1 = Student.objects.create(
            admission_number='STD-INT-001',
            first_name='Tolosa',
            father_name='Bekele',
            grandfather_name='Negash',
            gender='MALE',
            date_of_birth=date(2010, 5, 12),
            admission_date=date(2026, 9, 1),
            status='ACTIVE'
        )
        student2 = Student.objects.create(
            admission_number='STD-INT-002',
            first_name='Ayantu',
            father_name='Girma',
            grandfather_name='Desta',
            gender='FEMALE',
            date_of_birth=date(2010, 8, 22),
            admission_date=date(2026, 9, 1),
            status='ACTIVE'
        )

        # STEP 5: Create Class Offerings
        offering9a = ClassOffering.objects.create(academic_year=year1, grade=grade9, section=section_a)
        offering10a = ClassOffering.objects.create(academic_year=year2, grade=grade10, section=section_a)

        # STEP 6: Enroll Students (Integration 1: Student <-> Academic)
        enrollment1 = StudentEnrollment.objects.create(
            student=student1, class_offering=offering9a, academic_year=year1, status='ACTIVE'
        )
        enrollment2 = StudentEnrollment.objects.create(
            student=student2, class_offering=offering9a, academic_year=year1, status='ACTIVE'
        )
        self.assertEqual(offering9a.student_enrollments.count(), 2)
        self.assertEqual(student1.enrollments.first().class_offering, offering9a)

        # STEP 7: Assign Teacher (Integration 2: Teacher <-> Academic)
        assignment = TeacherAssignment.objects.create(
            teacher=teacher, class_offering=offering9a, subject=subject_math, academic_year=year1
        )
        self.assertEqual(teacher.assignments.count(), 1)
        self.assertEqual(offering9a.teacher_assignments.first().teacher, teacher)

        # STEP 8: Create Timetable (Integration 6: Teacher <-> Timetable)
        from timetable.models import Timetable, Period, SchoolDay, TimetableEntry
        period1 = Period.objects.create(
            name='Period 1', period_number=1, start_time=time(8, 30), end_time=time(9, 15), is_break=False
        )
        mon = SchoolDay.objects.create(day_of_week=0, name='Monday', short_name='Mon', is_active=True, order=1)
        tt = Timetable.objects.create(
            academic_year=year1, class_offering=offering9a, name='Grade 9A Timetable', status='PUBLISHED'
        )
        tt_entry = TimetableEntry.objects.create(
            timetable=tt,
            class_offering=offering9a,
            day_of_week=0,
            period=period1,
            subject=subject_math,
            teacher=teacher,
            teacher_assignment=assignment
        )
        self.assertEqual(teacher.timetable_entries.count(), 1)
        self.assertEqual(tt.entries.count(), 1)

        # STEP 9: Record Attendance (Integration 3: Academic <-> Attendance)
        session = AttendanceSession.objects.create(
            class_offering=offering9a, date=date(2026, 10, 5), session_type='MORNING', recorded_by=teacher
        )
        AttendanceRecord.objects.create(attendance_session=session, student_enrollment=enrollment1, status='PRESENT')
        AttendanceRecord.objects.create(attendance_session=session, student_enrollment=enrollment2, status='ABSENT')
        self.assertEqual(session.records.count(), 2)

        # STEP 10: Create Examination (Integration 4: Academic <-> Examination)
        exam = Examination.objects.create(
            academic_year=year1,
            name='Semester 1 Final Exam',
            semester='SEM1',
            start_date=date(2026, 12, 1),
            end_date=date(2026, 12, 15),
            status='PUBLISHED'
        )
        exam_sub = ExamSubject.objects.create(
            examination=exam, grade=grade9, subject=subject_math, max_marks=Decimal('100.00'), pass_marks=Decimal('50.00')
        )
        self.assertEqual(exam.exam_subjects.count(), 1)

        # STEP 11: Enter Marks
        Mark.objects.create(exam_subject=exam_sub, student_enrollment=enrollment1, marks_obtained=Decimal('88.50'), status='VERIFIED')
        Mark.objects.create(exam_subject=exam_sub, student_enrollment=enrollment2, marks_obtained=Decimal('42.00'), status='VERIFIED')

        # STEP 12: Verify and Publish Results
        verified_marks = Mark.objects.filter(exam_subject=exam_sub, status='VERIFIED')
        self.assertEqual(verified_marks.count(), 2)

        # STEP 13: Prepare Promotion (Integration 5 & 9: Exam <-> Promotion & Promotion <-> History)
        criteria = PromotionCriteria.objects.create(
            name='Standard Secondary Promotion',
            code='SEC-STD-INT',
            minimum_average=Decimal('50.00'),
            max_failing_subjects=1,
            is_default=True
        )
        batch = PromotionBatch.objects.create(
            name='Grade 9 Cohort Promotion',
            academic_year=year1,
            target_academic_year=year2,
            grade=grade9,
            promotion_criteria=criteria,
            status='FINALIZED'
        )
        rec1 = BatchPromotionRecord.objects.create(
            batch=batch,
            student=student1,
            student_enrollment=enrollment1,
            previous_academic_year=year1,
            next_academic_year=year2,
            previous_grade=grade9,
            next_grade=grade10,
            previous_class_offering=offering9a,
            next_class_offering=offering10a,
            academic_average=Decimal('88.50'),
            recommended_outcome='PROMOTED',
            final_outcome='PROMOTED',
            decision_status='APPROVED'
        )
        rec2 = BatchPromotionRecord.objects.create(
            batch=batch,
            student=student2,
            student_enrollment=enrollment2,
            previous_academic_year=year1,
            next_academic_year=year2,
            previous_grade=grade9,
            next_grade=grade9,
            previous_class_offering=offering9a,
            academic_average=Decimal('42.00'),
            recommended_outcome='REPEATED',
            final_outcome='REPEATED',
            decision_status='APPROVED'
        )
        self.assertEqual(batch.records.filter(final_outcome='PROMOTED').count(), 1)
        self.assertEqual(batch.records.filter(final_outcome='REPEATED').count(), 1)

        # STEP 14: Generate Academic & School Analytics (Integration 7 & 8: Attendance & Exam <-> Analytics)
        overview_stats = AnalyticsService.get_school_overview_stats(filters={}, user=teacher_user)
        self.assertGreaterEqual(overview_stats['total_registered_students'], 2)
        self.assertGreaterEqual(overview_stats['total_teachers'], 1)

        # Integration 7: Attendance analytics
        self.assertIn('attendance_percentage', overview_stats)
        self.assertEqual(overview_stats['total_attendance_records'], 2)

        # Integration 8: Examination analytics
        subject_reports = ExaminationPerformanceReportService.get_subject_performance_reports(filters={'examination': exam})
        self.assertEqual(len(subject_reports), 1)
        self.assertEqual(subject_reports[0]['pass_percentage'], 50.0)
        self.assertEqual(subject_reports[0]['average'], 65.2)

        # Student 360 portfolio includes multi-year history, attendance & promotion
        student1_portfolio = StudentReportService.get_student_detail_report(student1.id, user=teacher_user)
        self.assertEqual(student1_portfolio['student'].admission_number, 'STD-INT-001')
        self.assertEqual(len(student1_portfolio['promotions']), 1)
        self.assertEqual(student1_portfolio['promotions'][0].final_outcome, 'PROMOTED')


