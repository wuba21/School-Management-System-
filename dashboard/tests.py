"""
Automated Test Suite for Step 7: Admin Dashboard Implementation.

Verifies:
  1. Unauthenticated request to /dashboard/ redirects to login.
  2. Empty database behavior (all KPIs safely render zero, no division by zero).
  3. Populated database statistics (accurate calculation of students, teachers, classes).
  4. Today's attendance percentage calculation.
  5. Principal role-based dashboard view.
  6. Registrar role-based dashboard view (unassigned student counts).
  7. Teacher role-based dashboard view (assigned classes & subjects filter).
  8. Administrator role-based dashboard view (system user counts & audit logs).
  9. Chart JSON payload generation and structure.
"""

import json
from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import User, Role
from academics.models import AcademicYear, Grade, Section, Stream, ClassOffering, Subject
from students.models import Student, StudentEnrollment
from teachers.models import Teacher, TeacherAssignment
from attendance.models import AttendanceSession, AttendanceRecord
from examinations.models import Examination, ExamSubject
from results.models import Mark
from core.models import AuditLog
from dashboard.services import DashboardService


class DashboardImplementationTests(TestCase):

    def setUp(self):
        self.client = Client()

        # Roles
        self.role_principal = Role.objects.create(code='PRINCIPAL', name='School Principal')
        self.role_registrar = Role.objects.create(code='REGISTRAR', name='Registrar')
        self.role_teacher = Role.objects.create(code='TEACHER', name='Teacher')
        self.role_admin = Role.objects.create(code='ADMIN', name='System Administrator')

        # Users
        self.user_principal = User.objects.create_user(
            username='principal_user', password='TestPassword123!', role=self.role_principal,
            first_name='Principal', last_name='One'
        )
        self.user_registrar = User.objects.create_user(
            username='registrar_user', password='TestPassword123!', role=self.role_registrar,
            first_name='Registrar', last_name='One'
        )
        self.user_teacher = User.objects.create_user(
            username='teacher_user', password='TestPassword123!', role=self.role_teacher,
            first_name='Teacher', last_name='One'
        )
        self.user_admin = User.objects.create_user(
            username='admin_user', password='TestPassword123!', role=self.role_admin,
            first_name='Admin', last_name='One'
        )

    # 1. Unauthenticated access redirect
    def test_unauthenticated_dashboard_redirects_to_login(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    # 2. Empty database behavior
    def test_empty_database_dashboard_renders_cleanly(self):
        self.client.login(username='principal_user', password='TestPassword123!')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Total Students')
        self.assertContains(response, '0')
        self.assertContains(response, 'No Student Enrollees Found')
        self.assertContains(response, 'No Attendance Sessions Recorded')

    # 3. Populated database statistics accuracy
    def test_populated_dashboard_statistics(self):
        year = AcademicYear.objects.create(
            name='2026/2027 (2018/2019 E.C.)', code='AY-2026', start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30), is_current=True
        )
        grade = Grade.objects.create(name='Grade 9', level=9)
        section = Section.objects.create(name='A')
        class_offering = ClassOffering.objects.create(
            academic_year=year, grade=grade, section=section
        )

        s1 = Student.objects.create(
            admission_number='SSMS/001', first_name='Abebe', father_name='Bikila',
            grandfather_name='Kebede', gender='M', date_of_birth=date(2010, 1, 1),
            emergency_contact_name='Bikila Kebede', emergency_contact_phone='0911000001',
            emergency_contact_relation='Father'
        )
        s2 = Student.objects.create(
            admission_number='SSMS/002', first_name='Chaltu', father_name='Tolessa',
            grandfather_name='Gemechu', gender='F', date_of_birth=date(2010, 5, 5),
            emergency_contact_name='Tolessa Gemechu', emergency_contact_phone='0911000002',
            emergency_contact_relation='Father'
        )
        StudentEnrollment.objects.create(student=s1, class_offering=class_offering, academic_year=year)
        StudentEnrollment.objects.create(student=s2, class_offering=class_offering, academic_year=year)

        teacher = Teacher.objects.create(
            user=self.user_teacher, employee_id='EMP-001', first_name='Abebe', father_name='Tadesse',
            gender='M', qualification='B.Ed in Mathematics', specialization='Mathematics',
            joining_date=date(2021, 9, 1)
        )

        kpis = DashboardService.get_overview_kpis(self.user_principal)
        self.assertEqual(kpis['total_students'], 2)
        self.assertEqual(kpis['total_teachers'], 1)
        self.assertEqual(kpis['total_active_classes'], 1)
        self.assertEqual(kpis['current_year'], year)

    # 4. Today's attendance calculation
    def test_attendance_rate_calculation(self):
        today = timezone.localdate()
        year = AcademicYear.objects.create(
            name='2026/2027 (2018/2019 E.C.)', code='AY-2026', start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30), is_current=True
        )
        grade = Grade.objects.create(name='Grade 10', level=10)
        section = Section.objects.create(name='B')
        class_offering = ClassOffering.objects.create(
            academic_year=year, grade=grade, section=section
        )
        teacher = Teacher.objects.create(
            user=self.user_teacher, employee_id='EMP-002', first_name='Teacher', father_name='Two',
            gender='M', qualification='B.Sc', specialization='Physics', joining_date=date(2020, 1, 1)
        )

        s1 = Student.objects.create(
            admission_number='SSMS/010', first_name='Dawit', father_name='Haile',
            grandfather_name='Girma', gender='M', date_of_birth=date(2009, 2, 2),
            emergency_contact_name='Haile Girma', emergency_contact_phone='0911000010',
            emergency_contact_relation='Father'
        )
        s2 = Student.objects.create(
            admission_number='SSMS/011', first_name='Eden', father_name='Mulu',
            grandfather_name='Tilahun', gender='F', date_of_birth=date(2009, 3, 3),
            emergency_contact_name='Mulu Tilahun', emergency_contact_phone='0911000011',
            emergency_contact_relation='Mother'
        )
        e1 = StudentEnrollment.objects.create(student=s1, class_offering=class_offering, academic_year=year)
        e2 = StudentEnrollment.objects.create(student=s2, class_offering=class_offering, academic_year=year)

        session = AttendanceSession.objects.create(
            class_offering=class_offering, date=today, recorded_by=teacher
        )
        AttendanceRecord.objects.create(attendance_session=session, student_enrollment=e1, status='PRESENT')
        AttendanceRecord.objects.create(attendance_session=session, student_enrollment=e2, status='ABSENT')

        kpis = DashboardService.get_overview_kpis(self.user_principal)
        self.assertEqual(kpis['attendance_rate'], 50.0)
        self.assertEqual(kpis['today_present'], 1)
        self.assertEqual(kpis['today_absent'], 1)

    # 5. Principal role-based view
    def test_principal_role_dashboard(self):
        self.client.login(username='principal_user', password='TestPassword123!')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Executive Dashboard & Academic Analytics')
        self.assertContains(response, 'School Principal')

    # 6. Registrar role-based view
    def test_registrar_role_dashboard(self):
        self.client.login(username='registrar_user', password='TestPassword123!')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Registrar Operations Panel')
        self.assertContains(response, 'Unassigned / Pending Class Placement')

    # 7. Teacher role-based view
    def test_teacher_role_dashboard_with_assignments(self):
        teacher = Teacher.objects.create(
            user=self.user_teacher, employee_id='EMP-003', first_name='Kassahun', father_name='Tefera',
            gender='M', qualification='B.Ed in Biology', specialization='Biology', joining_date=date(2019, 9, 1)
        )
        year = AcademicYear.objects.create(
            name='2026/2027 (2018/2019 E.C.)', code='AY-2026', start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30), is_current=True
        )
        grade = Grade.objects.create(name='Grade 11', level=11)
        section = Section.objects.create(name='C')
        class_offering = ClassOffering.objects.create(
            academic_year=year, grade=grade, section=section
        )
        subject = Subject.objects.create(code='BIO-11', name='Biology')
        TeacherAssignment.objects.create(
            teacher=teacher, class_offering=class_offering, subject=subject
        )

        self.client.login(username='teacher_user', password='TestPassword123!')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Teacher Workload Dashboard')
        self.assertContains(response, 'Assigned Classes: <strong>1</strong>')
        self.assertContains(response, 'Assigned Subjects: <strong>1</strong>')

    # 8. Administrator role-based view
    def test_administrator_role_dashboard(self):
        self.client.login(username='admin_user', password='TestPassword123!')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'System Administrator Center')
        self.assertContains(response, 'Active User Accounts')

    # 9. Chart payload JSON integrity
    def test_chart_payload_json_structure(self):
        self.client.login(username='principal_user', password='TestPassword123!')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        
        payload_json = response.context['chart_payload_json']
        payload = json.loads(payload_json)

        self.assertIn('gradeLabels', payload)
        self.assertIn('gradeCounts', payload)
        self.assertIn('genderMale', payload)
        self.assertIn('genderFemale', payload)
        self.assertIn('attendanceLabels', payload)
        self.assertIn('attendanceRates', payload)
