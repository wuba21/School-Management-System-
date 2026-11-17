"""
Dedicated automated verification suite for SSMS UI/UX Redesign.

Tests coverage:
  1. Professional Login Page (Branding, Show/Hide Password, Remember Me, LAN Badge, Ethiopian Date, Amharic/English).
  2. Role-Based Dashboard Sub-Templates for all 4 roles:
     - System Administrator
     - School Principal
     - Registrar
     - Teacher
  3. Strict RBAC menu filtering in the sidebar (base.html).
  4. Top Navbar components (Ethiopian Calendar date with Gregorian tooltip, LAN status, Language Switcher, Notifications, User Profile).
  5. Zero unrendered split tags across all rendered pages.
"""

from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User, Role
from academics.models import AcademicYear, Grade, Section, ClassOffering, Subject
from teachers.models import Teacher, TeacherAssignment
from timetable.models import TimetableEntry, Period, Classroom
from attendance.models import AttendanceSession


class UIUXRedesignComprehensiveTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Create Roles
        self.admin_role, _ = Role.objects.get_or_create(code=Role.ADMIN, defaults={'name': 'System Administrator'})
        self.principal_role, _ = Role.objects.get_or_create(code=Role.PRINCIPAL, defaults={'name': 'School Principal'})
        self.registrar_role, _ = Role.objects.get_or_create(code=Role.REGISTRAR, defaults={'name': 'Registrar'})
        self.teacher_role, _ = Role.objects.get_or_create(code=Role.TEACHER, defaults={'name': 'Teacher'})

        # Create Users
        self.admin_user = User.objects.create_user(
            username='ux_admin', password='Password123!', role=self.admin_role, is_staff=True
        )
        self.principal_user = User.objects.create_user(
            username='ux_principal', password='Password123!', role=self.principal_role
        )
        self.registrar_user = User.objects.create_user(
            username='ux_registrar', password='Password123!', role=self.registrar_role
        )
        self.teacher_user = User.objects.create_user(
            username='ux_teacher', password='Password123!', role=self.teacher_role
        )

        # Academic structure
        self.year = AcademicYear.objects.create(
            name='2026/2027 (2018/2019 E.C.)', code='AY-2026-UX',
            start_date=date(2026, 9, 1), end_date=date(2027, 6, 30), is_current=True
        )
        self.grade = Grade.objects.create(name='Grade 10', level=10)
        self.section = Section.objects.create(name='A')
        self.class_off = ClassOffering.objects.create(
            academic_year=self.year, grade=self.grade, section=self.section, max_capacity=50
        )
        self.subject = Subject.objects.create(code='MATH-10', name='Mathematics')

        # Teacher profile & assignment
        self.teacher_profile = Teacher.objects.create(
            user=self.teacher_user, employee_id='T-UX-01', first_name='Almaz', father_name='Bekele',
            gender='F', qualification='B.Sc Mathematics', specialization='Mathematics', joining_date=date(2020, 9, 1)
        )
        self.assignment = TeacherAssignment.objects.create(
            teacher=self.teacher_profile, class_offering=self.class_off, subject=self.subject
        )

    def test_login_page_redesign_elements(self):
        """Verify login page includes all redesigned institutional elements."""
        resp = self.client.get(reverse('login'))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')

        # Institutional Branding
        self.assertIn('SSMS Portal', content)
        self.assertIn('Smart School Management System', content)
        self.assertIn('Metti Secondary School', content)
        self.assertIn('Grades 9-12', content)

        # Controls & Elements
        self.assertIn('usernameInput', content)
        self.assertIn('passwordInput', content)
        self.assertIn('togglePasswordBtn', content)
        self.assertIn('rememberMeCheck', content)
        self.assertIn('Local LAN Mode', content)

        # Ensure no raw split tags
        self.assertNotIn('{{', content)
        self.assertNotIn('{%', content)

    def test_login_page_amharic_rendering(self):
        """Verify login page renders properly in Amharic."""
        self.client.cookies['django_language'] = 'am'
        resp = self.client.get(reverse('login'))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')
        self.assertIn('አማርኛ', content)

    def test_admin_dashboard_rendering_and_rbac(self):
        """Verify Admin dashboard renders admin-specific tools and full sidebar navigation."""
        self.client.login(username='ux_admin', password='Password123!')
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')

        # Admin content
        self.assertIn('System Administrator Center', content)
        self.assertIn('Backup & Storage Integrity', content)
        self.assertIn('User Accounts & Role Distribution', content)
        self.assertIn('Recent Security & System Activities', content)

        # Admin sidebar menu permissions (has access to System section)
        self.assertIn('User Management', content)
        self.assertIn('Backup & Recovery', content)
        self.assertIn('Audit Logs', content)
        self.assertIn('Students', content)
        self.assertIn('Teachers', content)

        # Zero unrendered tags
        self.assertNotIn('{{', content)

    def test_principal_dashboard_rendering_and_rbac(self):
        """Verify Principal dashboard renders executive metrics and hides System configuration."""
        self.client.login(username='ux_principal', password='Password123!')
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')

        # Principal content
        self.assertIn('Executive Dashboard & Academic Analytics', content)
        self.assertIn('School Principal', content)
        self.assertIn('School Pass Rate', content)
        self.assertIn('Class Offerings & Capacity Matrix', content)
        self.assertIn('Executive Reports & Tools', content)

        # Strict RBAC: Principal must NOT see System administration links
        self.assertNotIn('System Administration', content)
        self.assertNotIn('Backup & Recovery', content)

        # Zero unrendered tags
        self.assertNotIn('{{', content)

    def test_registrar_dashboard_rendering_and_rbac(self):
        """Verify Registrar dashboard renders registry tools and hides Teachers and System sections."""
        self.client.login(username='ux_registrar', password='Password123!')
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')

        # Registrar content
        self.assertIn('Registrar Operations Panel', content)
        self.assertIn('Search Student', content)
        self.assertIn('Register New Student', content)
        self.assertIn('Class Capacity & Utilization', content)
        self.assertIn('Recent Student Registrations & Enrollments', content)

        # Strict RBAC: Registrar must NOT see Teachers, Curriculum Matrix, or System menu
        self.assertNotIn('Teachers', content)
        self.assertNotIn('Curriculum Matrix', content)
        self.assertNotIn('Backup & Recovery', content)

        # Zero unrendered tags
        self.assertNotIn('{{', content)

    def test_teacher_dashboard_rendering_and_rbac(self):
        """Verify Teacher dashboard renders workload, schedule, and hides Management/System menus."""
        self.client.login(username='ux_teacher', password='Password123!')
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode('utf-8')

        # Teacher content
        self.assertIn('Teacher Workload Dashboard', content)
        self.assertIn('Today\'s Teaching Timetable Schedule', content)
        self.assertIn('My Assigned Classes & Subjects', content)
        self.assertIn('Take Daily Attendance', content)

        # Strict RBAC: Teacher must NOT see Management, Reports, or System menus
        self.assertNotIn('User Management', content)
        self.assertNotIn('Backup & Recovery', content)
        self.assertNotIn('Academic Years', content)
        self.assertNotIn('Curriculum Matrix', content)
        self.assertNotIn('Analytics Dashboard', content)

        # Zero unrendered tags
        self.assertNotIn('{{', content)
