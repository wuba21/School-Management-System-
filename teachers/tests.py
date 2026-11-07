"""
Comprehensive Automated Test Suite for Step 9: Teacher Management System.

Tests:
  1. Teacher registration by authorized registrar
  2. Auto-generation of teacher employee IDs
  3. Custom teacher ID policy
  4. Duplicate teacher ID prevention
  5. Teacher profile view & workload rendering
  6. Teacher profile update with audit trail diff
  7. Class & Subject allocation
  8. Duplicate assignment prevention
  9. Assignment to closed academic year rejected
 10. Teacher search, filtering, and sorting
 11. File upload security (Pillow binary check, extension check)
 12. Teacher status lifecycle (On Leave, Transferred) preserves historical records
 13. Role-based access control (Principal, Registrar, Teacher, Anonymous)
 14. Dedicated teacher "My Profile" endpoint
"""

import io
from datetime import date, timedelta
from PIL import Image

from django.test import TestCase, Client
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError

from accounts.models import User, Role
from teachers.models import Teacher, TeacherAssignment
from teachers.services import TeacherIDService, FileUploadSecurityService, TeacherService
from academics.models import AcademicYear, Grade, Section, Stream, Subject, ClassOffering
from core.models import AuditLog


class TeacherManagementTests(TestCase):

    def setUp(self):
        self.client = Client()

        # System Roles
        self.role_admin = Role.objects.create(code='ADMIN', name='System Administrator')
        self.role_principal = Role.objects.create(code='PRINCIPAL', name='School Principal')
        self.role_registrar = Role.objects.create(code='REGISTRAR', name='Registrar')
        self.role_teacher = Role.objects.create(code='TEACHER', name='Teacher')

        # Test Users
        self.user_admin = User.objects.create_user(
            username='admin_test',
            password='Password123!',
            role=self.role_admin,
            is_staff=True,
            is_superuser=True
        )
        self.user_principal = User.objects.create_user(
            username='principal_test',
            password='Password123!',
            role=self.role_principal
        )
        self.user_registrar = User.objects.create_user(
            username='registrar_test',
            password='Password123!',
            role=self.role_registrar
        )
        self.user_teacher_1 = User.objects.create_user(
            username='teacher_one',
            password='Password123!',
            role=self.role_teacher
        )
        self.user_teacher_2 = User.objects.create_user(
            username='teacher_two',
            password='Password123!',
            role=self.role_teacher
        )

        # Academic Infrastructure
        self.ay_current = AcademicYear.objects.create(
            name='2026/2027 Academic Year',
            code='AY-2026',
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_current=True,
            is_closed=False
        )
        self.ay_closed = AcademicYear.objects.create(
            name='2025/2026 Academic Year',
            code='AY-2025',
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_current=False,
            is_closed=True
        )

        self.grade_10 = Grade.objects.create(name='Grade 10', level=10)
        self.grade_11 = Grade.objects.create(name='Grade 11', level=11)
        self.section_a = Section.objects.create(name='A')
        self.section_b = Section.objects.create(name='B')
        self.stream_natural = Stream.objects.create(code='NAT', name='Natural Science')

        self.class_10a = ClassOffering.objects.create(
            academic_year=self.ay_current,
            grade=self.grade_10,
            section=self.section_a,
            max_capacity=50
        )
        self.class_11a_nat = ClassOffering.objects.create(
            academic_year=self.ay_current,
            grade=self.grade_11,
            section=self.section_a,
            stream=self.stream_natural,
            max_capacity=50
        )

        self.subject_math = Subject.objects.create(code='MATH-10', name='Mathematics', is_active=True)
        self.subject_physics = Subject.objects.create(code='PHYS-11', name='Physics', is_active=True)

        # Pre-existing Teacher
        self.teacher_1 = Teacher.objects.create(
            user=self.user_teacher_1,
            employee_id='EMP/2026/0001',
            first_name='Abebe',
            father_name='Bikila',
            grandfather_name='Desta',
            gender='M',
            date_of_birth=date(1988, 5, 12),
            qualification='B.Ed in Mathematics',
            specialization='Mathematics',
            joining_date=date(2020, 9, 1),
            employment_status='ACTIVE',
            is_active=True
        )

    def _create_test_image(self, filename="portrait.jpg", format_type="JPEG"):
        """Creates a dummy valid in-memory image for upload testing."""
        file_obj = io.BytesIO()
        image = Image.new('RGB', (100, 100), color=(73, 109, 137))
        image.save(file_obj, format=format_type)
        file_obj.seek(0)
        return SimpleUploadedFile(filename, file_obj.read(), content_type=f'image/{format_type.lower()}')

    # 1. Teacher Registration
    def test_teacher_registration_by_registrar(self):
        self.client.login(username='registrar_test', password='Password123!')
        response = self.client.post(reverse('teacher_register'), {
            'first_name': 'Derartu',
            'father_name': 'Tulu',
            'grandfather_name': 'Bekele',
            'gender': 'F',
            'date_of_birth': '1992-03-21',
            'qualification': 'M.Sc in Physics Education',
            'specialization': 'Physics',
            'joining_date': '2026-09-01',
            'employment_status': 'ACTIVE',
            'phone_number': '+251911889900',
            'email': 'derartu.tulu@school.edu.et',
            'address': 'Gambella, Majang, Godere',
            'auto_generate_teacher_id': 'on',
            'employee_id': '',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        new_teacher = Teacher.objects.filter(first_name='Derartu', father_name='Tulu').first()
        self.assertIsNotNone(new_teacher)
        self.assertTrue(new_teacher.employee_id.startswith('EMP/2026/'))
        self.assertEqual(new_teacher.specialization, 'Physics')

        # Verify audit log recorded
        audit = AuditLog.objects.filter(entity_name='Teacher', record_id=new_teacher.employee_id).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.action, 'CREATE')

    # 2. Custom Teacher ID Policy
    def test_custom_teacher_id_accepted(self):
        self.client.login(username='registrar_test', password='Password123!')
        response = self.client.post(reverse('teacher_register'), {
            'first_name': 'Haile',
            'father_name': 'Gebrselassie',
            'gender': 'M',
            'qualification': 'B.Sc in Chemistry',
            'specialization': 'Chemistry',
            'joining_date': '2026-09-01',
            'employment_status': 'ACTIVE',
            'auto_generate_teacher_id': '',
            'employee_id': 'EMP-GOV-8821',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        teacher = Teacher.objects.filter(employee_id='EMP-GOV-8821').first()
        self.assertIsNotNone(teacher)
        self.assertEqual(teacher.first_name, 'Haile')

    # 3. Duplicate Teacher ID Rejected
    def test_duplicate_teacher_id_rejected(self):
        self.client.login(username='registrar_test', password='Password123!')
        response = self.client.post(reverse('teacher_register'), {
            'first_name': 'Duplicate',
            'father_name': 'Test',
            'gender': 'M',
            'qualification': 'B.A in English',
            'specialization': 'English',
            'joining_date': '2026-09-01',
            'employment_status': 'ACTIVE',
            'auto_generate_teacher_id': '',
            'employee_id': 'EMP/2026/0001',  # Already belongs to teacher_1
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Teacher.objects.filter(first_name='Duplicate').exists())
        self.assertFormError(response.context['form'], 'employee_id', "Teacher ID 'EMP/2026/0001' is already registered in the system.")

    # 4. Teacher Profile View
    def test_teacher_profile_view(self):
        self.client.login(username='principal_test', password='Password123!')
        response = self.client.get(reverse('teacher_detail', args=[self.teacher_1.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Abebe Bikila Desta')
        self.assertContains(response, 'EMP/2026/0001')
        self.assertContains(response, 'B.Ed in Mathematics')

    # 5. Teacher Profile Update
    def test_teacher_update_by_registrar(self):
        self.client.login(username='registrar_test', password='Password123!')
        response = self.client.post(reverse('teacher_edit', args=[self.teacher_1.pk]), {
            'first_name': 'Abebe',
            'father_name': 'Bikila',
            'grandfather_name': 'Desta',
            'gender': 'M',
            'date_of_birth': '1988-05-12',
            'qualification': 'M.Ed in Higher Mathematics',
            'specialization': 'Mathematics',
            'joining_date': '2020-09-01',
            'phone_number': '+251911999888',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.teacher_1.refresh_from_db()
        self.assertEqual(self.teacher_1.qualification, 'M.Ed in Higher Mathematics')
        self.assertEqual(self.teacher_1.phone_number, '+251911999888')

        # Check audit log diff
        audit = AuditLog.objects.filter(entity_name='Teacher', record_id=self.teacher_1.employee_id, action='UPDATE').first()
        self.assertIsNotNone(audit)
        self.assertIn('qualification', audit.changes_json)

    # 6. Class & Subject Assignment
    def test_class_and_subject_assignment(self):
        self.client.login(username='registrar_test', password='Password123!')
        response = self.client.post(reverse('teacher_assign', args=[self.teacher_1.pk]), {
            'academic_year': self.ay_current.pk,
            'class_offering': self.class_10a.pk,
            'subject': self.subject_math.pk,
            'is_primary': 'on',
            'notes': 'Period 1 & 2 Mon/Wed',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        assignment = TeacherAssignment.objects.filter(
            teacher=self.teacher_1,
            class_offering=self.class_10a,
            subject=self.subject_math
        ).first()

        self.assertIsNotNone(assignment)
        self.assertTrue(assignment.is_primary)
        self.assertEqual(assignment.academic_year, self.ay_current)

    # 7. Duplicate Assignment Prevention
    def test_duplicate_assignment_prevented(self):
        # Create initial assignment
        TeacherAssignment.objects.create(
            teacher=self.teacher_1,
            class_offering=self.class_10a,
            subject=self.subject_math,
            academic_year=self.ay_current
        )

        self.client.login(username='registrar_test', password='Password123!')
        response = self.client.post(reverse('teacher_assign', args=[self.teacher_1.pk]), {
            'academic_year': self.ay_current.pk,
            'class_offering': self.class_10a.pk,
            'subject': self.subject_math.pk,
            'is_primary': 'on',
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(TeacherAssignment.objects.filter(teacher=self.teacher_1).count(), 1)
        self.assertContains(response, 'already assigned')

    # 8. Assignment in Closed Academic Year Rejected
    def test_assignment_to_closed_academic_year_rejected(self):
        with self.assertRaises(ValidationError):
            TeacherService.assign_teacher_to_class(
                teacher=self.teacher_1,
                class_offering=self.class_10a,
                subject=self.subject_math,
                academic_year=self.ay_closed
            )

    # 9. Search and Filter
    def test_teacher_search_and_filter(self):
        Teacher.objects.create(
            employee_id='EMP/2026/0002',
            first_name='Kenenisa',
            father_name='Bekele',
            gender='M',
            qualification='B.Sc in Biology',
            specialization='Biology',
            joining_date=date(2021, 9, 1),
            employment_status='ON_LEAVE'
        )

        self.client.login(username='principal_test', password='Password123!')

        # Search by name
        res = self.client.get(reverse('teachers_list') + '?q=Kenenisa')
        self.assertEqual(len(res.context['teachers']), 1)
        self.assertEqual(res.context['teachers'][0].first_name, 'Kenenisa')

        # Filter by status
        res_status = self.client.get(reverse('teachers_list') + '?status=ON_LEAVE')
        self.assertEqual(len(res_status.context['teachers']), 1)
        self.assertEqual(res_status.context['teachers'][0].first_name, 'Kenenisa')

        # Filter by specialization
        res_spec = self.client.get(reverse('teachers_list') + '?specialization=Mathematics')
        self.assertEqual(len(res_spec.context['teachers']), 1)
        self.assertEqual(res_spec.context['teachers'][0].first_name, 'Abebe')

    # 10. File Upload Security
    def test_file_upload_security(self):
        # 1. Genuine Image passes
        good_img = self._create_test_image("portrait.png", "PNG")
        validated = FileUploadSecurityService.validate_image_file(good_img)
        self.assertIsNotNone(validated)

        # 2. Fake image (disguised text file) fails
        fake_img = SimpleUploadedFile("malicious.jpg", b"<?php echo 'attack'; ?>", content_type="image/jpeg")
        with self.assertRaises(ValidationError):
            FileUploadSecurityService.validate_image_file(fake_img)

        # 3. Disallowed extension fails
        bad_ext = SimpleUploadedFile("script.sh", b"echo hello", content_type="application/x-sh")
        with self.assertRaises(ValidationError):
            FileUploadSecurityService.validate_image_file(bad_ext)

    # 11. Teacher Status Lifecycle Preserves Records
    def test_teacher_status_lifecycle_preserves_records(self):
        # Create assignment
        TeacherAssignment.objects.create(
            teacher=self.teacher_1,
            class_offering=self.class_10a,
            subject=self.subject_math,
            academic_year=self.ay_current
        )

        self.client.login(username='registrar_test', password='Password123!')
        response = self.client.post(reverse('teacher_status', args=[self.teacher_1.pk]), {
            'employment_status': 'ON_LEAVE',
            'remarks': 'Approved 3-month research and study leave by Gambella Education Bureau.',
        }, follow=True)

        self.assertEqual(response.status_code, 200)
        self.teacher_1.refresh_from_db()
        self.assertEqual(self.teacher_1.employment_status, 'ON_LEAVE')

        # Verify historical assignment still exists
        self.assertEqual(TeacherAssignment.objects.filter(teacher=self.teacher_1).count(), 1)

    # 12. Role-Based Permissions
    def test_role_based_permissions(self):
        # Anonymous redirects to login
        res_anon = self.client.get(reverse('teachers_list'))
        self.assertEqual(res_anon.status_code, 302)

        # Principal can view directory and detail, but CANNOT register or edit
        self.client.login(username='principal_test', password='Password123!')
        self.assertEqual(self.client.get(reverse('teachers_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('teacher_detail', args=[self.teacher_1.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('teacher_register')).status_code, 403)
        self.assertEqual(self.client.get(reverse('teacher_edit', args=[self.teacher_1.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('teacher_status', args=[self.teacher_1.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('teacher_assign', args=[self.teacher_1.pk])).status_code, 403)

        # Teacher 1 can view their OWN profile
        self.client.login(username='teacher_one', password='Password123!')
        self.assertEqual(self.client.get(reverse('teacher_detail', args=[self.teacher_1.pk])).status_code, 200)

        # Teacher 2 CANNOT view Teacher 1's profile (403 Forbidden)
        self.client.login(username='teacher_two', password='Password123!')
        self.assertEqual(self.client.get(reverse('teacher_detail', args=[self.teacher_1.pk])).status_code, 403)

    # 13. Teacher "My Profile" Shortcut
    def test_teacher_my_profile_redirect(self):
        self.client.login(username='teacher_one', password='Password123!')
        response = self.client.get(reverse('teacher_my_profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Abebe Bikila Desta')
