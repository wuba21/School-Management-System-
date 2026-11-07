"""
Automated Test Suite for Step 6: Authentication and Role-Based Access Control (RBAC).

Tests:
  1. Valid login
  2. Invalid login
  3. Logout
  4. Protected pages redirect unauthenticated users
  5. Principal permissions
  6. Registrar permissions
  7. Teacher permissions
  8. Administrator permissions
  9. Unauthorized access returns 403
  10. Deactivated user account cannot log in
"""

from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import User, Role


class AuthenticationAndRBACTests(TestCase):

    def setUp(self):
        self.client = Client()

        # Create system roles
        self.role_principal = Role.objects.create(code='PRINCIPAL', name='School Principal')
        self.role_registrar = Role.objects.create(code='REGISTRAR', name='Registrar')
        self.role_teacher = Role.objects.create(code='TEACHER', name='Teacher')
        self.role_admin = Role.objects.create(code='ADMIN', name='System Administrator')

        # Create test users with hashed passwords
        self.principal_user = User.objects.create_user(
            username='test_principal',
            password='SecretPassword123!',
            role=self.role_principal,
            first_name='Kebede',
            last_name='Tadesse'
        )
        self.registrar_user = User.objects.create_user(
            username='test_registrar',
            password='SecretPassword123!',
            role=self.role_registrar,
            first_name='Almaz',
            last_name='Bekele'
        )
        self.teacher_user = User.objects.create_user(
            username='test_teacher',
            password='SecretPassword123!',
            role=self.role_teacher,
            first_name='Abebe',
            last_name='Bikila'
        )
        self.admin_user = User.objects.create_user(
            username='test_admin',
            password='SecretPassword123!',
            role=self.role_admin,
            first_name='Admin',
            last_name='User'
        )
        self.deactivated_user = User.objects.create_user(
            username='test_inactive',
            password='SecretPassword123!',
            role=self.role_teacher,
            is_active=False
        )

    # 1. Valid Login
    def test_valid_login(self):
        response = self.client.post(reverse('login'), {
            'username': 'test_principal',
            'password': 'SecretPassword123!'
        })
        self.assertRedirects(response, reverse('dashboard'))
        self.assertTrue('_auth_user_id' in self.client.session)

    # 2. Invalid Login
    def test_invalid_login(self):
        response = self.client.post(reverse('login'), {
            'username': 'test_principal',
            'password': 'WrongPassword999!'
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse('_auth_user_id' in self.client.session)
        self.assertContains(response, 'Invalid username or password')

    # 3. Logout
    def test_logout(self):
        self.client.login(username='test_principal', password='SecretPassword123!')
        response = self.client.get(reverse('logout'))
        self.assertRedirects(response, reverse('login'))
        self.assertFalse('_auth_user_id' in self.client.session)

    # 4. Protected Pages redirect unauthenticated users
    def test_protected_pages_redirect_unauthenticated(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('login')))

    # 5. Principal permissions
    def test_principal_can_access_dashboard_and_reports(self):
        self.client.login(username='test_principal', password='SecretPassword123!')
        # Dashboard
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        # Academic Reports
        response = self.client.get(reverse('reports_academic'))
        self.assertEqual(response.status_code, 200)
        # Cannot access user administration
        response = self.client.get(reverse('user_list'))
        self.assertEqual(response.status_code, 403)

    # 6. Registrar permissions
    def test_registrar_can_access_students_and_reports(self):
        self.client.login(username='test_registrar', password='SecretPassword123!')
        response = self.client.get(reverse('students_list'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('reports_students'))
        self.assertEqual(response.status_code, 200)
        # Cannot access system user management
        response = self.client.get(reverse('user_list'))
        self.assertEqual(response.status_code, 403)

    # 7. Teacher permissions
    def test_teacher_can_access_attendance_and_results(self):
        self.client.login(username='test_teacher', password='SecretPassword123!')
        response = self.client.get(reverse('attendance_index'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('results_index'))
        self.assertEqual(response.status_code, 200)
        # Teachers CAN access the student list (filtered to their assigned classes only)
        response = self.client.get(reverse('students_list'))
        self.assertEqual(response.status_code, 200)
        # Teacher cannot access restricted academic reports
        response = self.client.get(reverse('reports_academic'))
        self.assertEqual(response.status_code, 403)

    # 8. Administrator permissions
    def test_administrator_can_manage_users(self):
        self.client.login(username='test_admin', password='SecretPassword123!')
        response = self.client.get(reverse('user_list'))
        self.assertEqual(response.status_code, 200)
        response = self.client.get(reverse('user_create'))
        self.assertEqual(response.status_code, 200)

    # 9. Unauthorized access returns 403
    def test_unauthorized_access_returns_403(self):
        self.client.login(username='test_teacher', password='SecretPassword123!')
        response = self.client.get(reverse('user_list'))
        self.assertEqual(response.status_code, 403)

    # 10. Deactivated user cannot log in
    def test_deactivated_user_cannot_login(self):
        response = self.client.post(reverse('login'), {
            'username': 'test_inactive',
            'password': 'SecretPassword123!'
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse('_auth_user_id' in self.client.session)
        self.assertContains(response, 'Invalid username or password')
