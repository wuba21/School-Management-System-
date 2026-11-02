from django.test import TestCase
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
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
        """Verify the dashboard page renders with KPI metrics and Chart.js canvases."""
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Total Students')
        self.assertContains(response, 'Total Teachers')
        self.assertContains(response, 'Academic Year')
        self.assertContains(response, 'Today\'s Attendance')
        self.assertContains(response, 'enrollmentChart')
        self.assertContains(response, 'attendanceChart')
        self.assertContains(response, 'Sample Data Preview')

    def test_all_sidebar_navigation_routes(self):
        """Verify every single sidebar navigation item resolves and loads with HTTP 200."""
        routes = [
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
            '/users/',
            '/settings/',
            '/audit/',
        ]
        for url in routes:
            with self.subTest(route=url):
                response = self.client.get(url)
                self.assertEqual(
                    response.status_code,
                    200,
                    f"Expected HTTP 200 for route '{url}', got {response.status_code}"
                )

    def test_static_asset_links_in_base_template(self):
        """Verify that offline vendor assets (Bootstrap, Icons, Chart.js) are referenced."""
        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'vendor/bootstrap/css/bootstrap.min.css')
        self.assertContains(response, 'vendor/bootstrap-icons/bootstrap-icons.css')
        self.assertContains(response, 'vendor/bootstrap/js/bootstrap.bundle.min.js')
        self.assertContains(response, 'vendor/chartjs/chart.umd.min.js')
        self.assertContains(response, 'css/styles.css')
        self.assertContains(response, 'js/main.js')

