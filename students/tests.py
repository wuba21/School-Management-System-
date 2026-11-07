"""
Comprehensive Automated Test Suite for Student Management System (SSMS).

Covers:
  - Student registration (auto & manual admission numbers)
  - Duplicate admission number rejection
  - Student profile rendering & data display
  - Student profile updates & audit logging
  - Classroom enrollment
  - Duplicate enrollment prevention in same academic year
  - Student status transitions (Active -> Transferred/Withdrawn)
  - Search, multi-criteria filtering, and pagination
  - File upload security validation (valid images vs spoofed files)
  - Role-based access control (Registrar, Principal, Teacher, Admin, Anonymous)
"""

import io
from datetime import date
from PIL import Image

from django.test import TestCase, Client
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.urls import reverse

from accounts.models import Role, User
from academics.models import AcademicYear, Grade, Section, Stream, ClassOffering, Subject
from students.models import Student, StudentEnrollment, PromotionRecord
from teachers.models import Teacher, TeacherAssignment
from core.models import AuditLog
from students.services import AdmissionNumberService, FileUploadSecurityService


class StudentManagementTests(TestCase):
    """
    Test suite verifying all functional and security requirements of Step 8:
    Student Management System.
    """

    def setUp(self):
        self.client = Client()

        # 1. Setup Roles
        self.role_admin = Role.objects.create(code='ADMIN', name='System Administrator')
        self.role_principal = Role.objects.create(code='PRINCIPAL', name='School Principal')
        self.role_registrar = Role.objects.create(code='REGISTRAR', name='Registrar')
        self.role_teacher = Role.objects.create(code='TEACHER', name='Teacher')

        # 2. Setup Users
        self.user_admin = User.objects.create_superuser(
            username='admin_user',
            password='TestPassword123!',
            email='admin@school.local',
            role=self.role_admin
        )
        self.user_principal = User.objects.create_user(
            username='principal_user',
            password='TestPassword123!',
            email='principal@school.local',
            role=self.role_principal
        )
        self.user_registrar = User.objects.create_user(
            username='registrar_user',
            password='TestPassword123!',
            email='registrar@school.local',
            role=self.role_registrar
        )
        self.user_teacher_1 = User.objects.create_user(
            username='teacher_math',
            password='TestPassword123!',
            email='math_teacher@school.local',
            role=self.role_teacher
        )
        self.user_teacher_2 = User.objects.create_user(
            username='teacher_english',
            password='TestPassword123!',
            email='english_teacher@school.local',
            role=self.role_teacher
        )

        # 3. Setup Academic Structure
        self.ay_2026 = AcademicYear.objects.create(
            name='2026/2027 (2018/2019 E.C.)',
            code='AY-2026',
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_current=True
        )
        self.ay_2027 = AcademicYear.objects.create(
            name='2027/2028 (2019/2020 E.C.)',
            code='AY-2027',
            start_date=date(2027, 9, 1),
            end_date=date(2028, 6, 30),
            is_current=False
        )

        self.grade_9 = Grade.objects.create(name='Grade 9', level=9)
        self.grade_10 = Grade.objects.create(name='Grade 10', level=10)

        self.section_a = Section.objects.create(name='A')
        self.section_b = Section.objects.create(name='B')

        self.stream_gen = Stream.objects.create(code='GENERAL', name='General Secondary')

        self.class_9a = ClassOffering.objects.create(
            academic_year=self.ay_2026,
            grade=self.grade_9,
            section=self.section_a,
            stream=self.stream_gen,
            max_capacity=50
        )
        self.class_9b = ClassOffering.objects.create(
            academic_year=self.ay_2026,
            grade=self.grade_9,
            section=self.section_b,
            stream=self.stream_gen,
            max_capacity=50
        )
        self.class_10a = ClassOffering.objects.create(
            academic_year=self.ay_2026,
            grade=self.grade_10,
            section=self.section_a,
            stream=self.stream_gen,
            max_capacity=50
        )

        self.subject_math = Subject.objects.create(code='MATH-09', name='Mathematics')

        # 4. Setup Teacher Profiles & Assignment
        self.teacher_1 = Teacher.objects.create(
            user=self.user_teacher_1,
            employee_id='TCH-001',
            first_name='Abebe',
            father_name='Bikila',
            gender='M',
            qualification='B.Ed in Math',
            specialization='Mathematics',
            joining_date=date(2020, 9, 1)
        )
        # Teacher 1 teaches in Class 9-A
        TeacherAssignment.objects.create(
            teacher=self.teacher_1,
            class_offering=self.class_9a,
            subject=self.subject_math
        )

        self.teacher_2 = Teacher.objects.create(
            user=self.user_teacher_2,
            employee_id='TCH-002',
            first_name='Derartu',
            father_name='Tulu',
            gender='F',
            qualification='B.Ed in English',
            specialization='English',
            joining_date=date(2021, 9, 1)
        )
        # Teacher 2 teaches in Class 10-A
        TeacherAssignment.objects.create(
            teacher=self.teacher_2,
            class_offering=self.class_10a,
            subject=self.subject_math
        )

        # 5. Setup Base Student
        self.student_1 = Student.objects.create(
            admission_number='SSMS/2026/0001',
            first_name='Chaltu',
            father_name='Tolessa',
            grandfather_name='Gemechu',
            gender='F',
            date_of_birth=date(2010, 5, 12),
            phone_number='0911223344',
            address='Godere Woreda, Majang Zone',
            emergency_contact_name='Tolessa Gemechu',
            emergency_contact_phone='0911223344',
            emergency_contact_relation='Father',
            status='ACTIVE'
        )
        # Enrolled in Class 9-A
        self.enrollment_1 = StudentEnrollment.objects.create(
            student=self.student_1,
            class_offering=self.class_9a,
            academic_year=self.ay_2026,
            status='ACTIVE'
        )

    def _create_test_image(self, filename="portrait.jpg", format="JPEG"):
        """Helper to create a genuine, safe in-memory image for upload testing."""
        file_obj = io.BytesIO()
        image = Image.new("RGB", (100, 100), color=(73, 109, 137))
        image.save(file_obj, format=format)
        file_obj.seek(0)
        return SimpleUploadedFile(filename, file_obj.read(), content_type=f"image/{format.lower()}")

    def test_student_registration_by_registrar(self):
        """Verify that a Registrar can register a new student with auto-generated admission number."""
        self.client.login(username='registrar_user', password='TestPassword123!')
        
        post_data = {
            'auto_generate_admission_number': True,
            'admission_number': '',
            'first_name': 'Amanuel',
            'father_name': 'Kebede',
            'grandfather_name': 'Desta',
            'gender': 'M',
            'date_of_birth': '2011-04-15',
            'phone_number': '0922334455',
            'address': 'Metu Road, Majang Zone',
            'emergency_contact_name': 'Kebede Desta',
            'emergency_contact_phone': '0922334455',
            'emergency_contact_relation': 'Father',
            'academic_year': self.ay_2026.id,
            'class_offering': self.class_9a.id,
        }
        response = self.client.post(reverse('student_register'), post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        # Verify student exists in DB
        new_student = Student.objects.filter(first_name='Amanuel', father_name='Kebede').first()
        self.assertIsNotNone(new_student)
        self.assertEqual(new_student.admission_number, 'SSMS/2026/0002')
        self.assertEqual(new_student.full_name, 'Amanuel Kebede Desta')

        # Verify immediate enrollment was created
        enrollment = StudentEnrollment.objects.filter(student=new_student, academic_year=self.ay_2026).first()
        self.assertIsNotNone(enrollment)
        self.assertEqual(enrollment.class_offering, self.class_9a)

        # Verify AuditLog creation
        audit_entry = AuditLog.objects.filter(entity_name='Student', action='CREATE').first()
        self.assertIsNotNone(audit_entry)
        self.assertEqual(audit_entry.actor, self.user_registrar)

    def test_duplicate_admission_number_rejected(self):
        """Verify that attempting to register with an existing admission number is rejected."""
        self.client.login(username='registrar_user', password='TestPassword123!')

        post_data = {
            'auto_generate_admission_number': False,
            'admission_number': 'SSMS/2026/0001',  # Already exists!
            'first_name': 'Almaz',
            'father_name': 'Hailu',
            'grandfather_name': 'Tadesse',
            'gender': 'F',
            'date_of_birth': '2010-08-20',
            'emergency_contact_name': 'Hailu Tadesse',
            'emergency_contact_phone': '0933445566',
            'emergency_contact_relation': 'Father',
        }
        response = self.client.post(reverse('student_register'), post_data)
        self.assertEqual(response.status_code, 200)
        self.assertFormError(response.context['form'], 'admission_number', "Admission number 'SSMS/2026/0001' is already registered to another student.")

    def test_custom_admission_number_policy(self):
        """Verify that authorized staff can enter a custom formatted admission number."""
        self.client.login(username='registrar_user', password='TestPassword123!')

        post_data = {
            'auto_generate_admission_number': False,
            'admission_number': 'MAJ-SEC/2026/8888',
            'first_name': 'Tariku',
            'father_name': 'Bekele',
            'grandfather_name': 'Woldie',
            'gender': 'M',
            'date_of_birth': '2010-01-10',
            'emergency_contact_name': 'Bekele Woldie',
            'emergency_contact_phone': '0944556677',
            'emergency_contact_relation': 'Father',
        }
        response = self.client.post(reverse('student_register'), post_data, follow=True)
        self.assertEqual(response.status_code, 200)

        student = Student.objects.filter(admission_number='MAJ-SEC/2026/8888').first()
        self.assertIsNotNone(student)
        self.assertEqual(student.full_name, 'Tariku Bekele Woldie')

    def test_student_profile_view(self):
        """Verify that student profile displays full demographic and guardian info."""
        self.client.login(username='principal_user', password='TestPassword123!')

        response = self.client.get(reverse('student_detail', kwargs={'student_id': self.student_1.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Chaltu Tolessa Gemechu')
        self.assertContains(response, 'SSMS/2026/0001')
        self.assertContains(response, 'Tolessa Gemechu')
        self.assertContains(response, 'Grade 9')
        self.assertContains(response, 'Section A')

    def test_student_update_by_registrar(self):
        """Verify that a Registrar can update student information and the diff is logged."""
        self.client.login(username='registrar_user', password='TestPassword123!')

        post_data = {
            'admission_number': self.student_1.admission_number,
            'first_name': 'Chaltu',
            'father_name': 'Tolessa',
            'grandfather_name': 'Gemechu',
            'gender': 'F',
            'date_of_birth': '2010-05-12',
            'phone_number': '0977889900',  # Updated phone
            'address': 'New Kebele Address, Majang Zone',  # Updated address
            'emergency_contact_name': 'Tolessa Gemechu',
            'emergency_contact_phone': '0977889900',
            'emergency_contact_relation': 'Father',
            'status': 'ACTIVE',
        }
        response = self.client.post(
            reverse('student_edit', kwargs={'student_id': self.student_1.pk}),
            post_data,
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        self.student_1.refresh_from_db()
        self.assertEqual(self.student_1.phone_number, '0977889900')
        self.assertEqual(self.student_1.address, 'New Kebele Address, Majang Zone')

        # Verify audit log diff was captured
        audit_entry = AuditLog.objects.filter(entity_name='Student', action='UPDATE').latest('timestamp')
        self.assertIn('address', audit_entry.changes_json)
        self.assertEqual(audit_entry.actor, self.user_registrar)

    def test_student_enrollment_in_new_academic_year(self):
        """Verify enrolling a student in a subsequent academic year preserves previous records."""
        self.client.login(username='registrar_user', password='TestPassword123!')

        class_10_next_year = ClassOffering.objects.create(
            academic_year=self.ay_2027,
            grade=self.grade_10,
            section=self.section_a,
            stream=self.stream_gen
        )

        post_data = {
            'academic_year': self.ay_2027.id,
            'class_offering': class_10_next_year.id,
            'status': 'ACTIVE',
        }
        response = self.client.post(
            reverse('student_enroll', kwargs={'student_id': self.student_1.pk}),
            post_data,
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        # Student now has 2 historical enrollments
        enrollments = StudentEnrollment.objects.filter(student=self.student_1).order_by('academic_year__start_date')
        self.assertEqual(enrollments.count(), 2)
        self.assertEqual(enrollments.first().academic_year, self.ay_2026)
        self.assertEqual(enrollments.last().academic_year, self.ay_2027)

    def test_duplicate_enrollment_in_same_year_rejected(self):
        """Verify that enrolling a student into two class offerings in the same academic year is blocked."""
        self.client.login(username='registrar_user', password='TestPassword123!')

        # Student 1 is already enrolled in 2026 Class 9-A. Attempt to enroll in 2026 Class 9-B.
        post_data = {
            'academic_year': self.ay_2026.id,
            'class_offering': self.class_9b.id,
            'status': 'ACTIVE',
        }
        response = self.client.post(
            reverse('student_enroll', kwargs={'student_id': self.student_1.pk}),
            post_data
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'already enrolled in')

    def test_student_status_transition_preserves_records(self):
        """Verify student status transitions (e.g. Transferred) do not delete historical data."""
        self.client.login(username='registrar_user', password='TestPassword123!')

        post_data = {
            'status': 'TRANSFERRED',
            'remarks': 'Transferred to Gambella Comprehensive Secondary School, Letter Ref: #104/2026',
        }
        response = self.client.post(
            reverse('student_status', kwargs={'student_id': self.student_1.pk}),
            post_data,
            follow=True
        )
        self.assertEqual(response.status_code, 200)

        self.student_1.refresh_from_db()
        self.assertEqual(self.student_1.status, 'TRANSFERRED')

        # Academic enrollment was updated to WITHDRAWN, but NOT deleted
        self.enrollment_1.refresh_from_db()
        self.assertEqual(self.enrollment_1.status, 'WITHDRAWN')
        self.assertEqual(Student.objects.filter(pk=self.student_1.pk).count(), 1)

        # Audit log captured the status transition
        audit_entry = AuditLog.objects.filter(entity_name='Student', action='STATUS_CHANGE').latest('timestamp')
        self.assertEqual(audit_entry.changes_json['new_status'], 'TRANSFERRED')
        self.assertIn('#104/2026', audit_entry.changes_json['remarks'])

    def test_search_and_filtering(self):
        """Verify student search by name/admission number and filtering by grade and status."""
        self.client.login(username='principal_user', password='TestPassword123!')

        # Create second student in Grade 10
        student_2 = Student.objects.create(
            admission_number='SSMS/2026/0002',
            first_name='Dawit',
            father_name='Solomon',
            grandfather_name='Kassahun',
            gender='M',
            date_of_birth=date(2009, 3, 10),
            emergency_contact_name='Solomon Kassahun',
            emergency_contact_phone='0955667788',
            emergency_contact_relation='Father',
            status='ACTIVE'
        )
        StudentEnrollment.objects.create(
            student=student_2,
            class_offering=self.class_10a,
            academic_year=self.ay_2026,
            status='ACTIVE'
        )

        # 1. Search by name 'Dawit'
        res_search = self.client.get(reverse('students_list'), {'q': 'Dawit'})
        self.assertEqual(res_search.status_code, 200)
        self.assertContains(res_search, 'Dawit Solomon Kassahun')
        self.assertNotContains(res_search, 'Chaltu Tolessa Gemechu')

        # 2. Filter by Grade 9
        res_grade9 = self.client.get(reverse('students_list'), {'grade': self.grade_9.id})
        self.assertContains(res_grade9, 'Chaltu Tolessa Gemechu')
        self.assertNotContains(res_grade9, 'Dawit Solomon Kassahun')

        # 3. Filter by Grade 10
        res_grade10 = self.client.get(reverse('students_list'), {'grade': self.grade_10.id})
        self.assertContains(res_grade10, 'Dawit Solomon Kassahun')
        self.assertNotContains(res_grade10, 'Chaltu Tolessa Gemechu')

    def test_pagination(self):
        """Verify student directory paginates correctly when student count exceeds 20."""
        self.client.login(username='principal_user', password='TestPassword123!')

        # Bulk create 24 additional students
        for i in range(2, 26):
            Student.objects.create(
                admission_number=f'SSMS/2026/{i:04d}',
                first_name=f'Student{i}',
                father_name='TestFather',
                grandfather_name='TestGrandfather',
                gender='M' if i % 2 == 0 else 'F',
                date_of_birth=date(2010, 1, 1),
                emergency_contact_name='Guardian Name',
                emergency_contact_phone='0911000000',
                emergency_contact_relation='Parent'
            )

        # Page 1: 20 students
        res_page1 = self.client.get(reverse('students_list'))
        self.assertEqual(res_page1.status_code, 200)
        self.assertEqual(len(res_page1.context['page_obj']), 20)
        self.assertTrue(res_page1.context['page_obj'].has_next())

        # Page 2: 5 students (total 25)
        res_page2 = self.client.get(reverse('students_list'), {'page': 2})
        self.assertEqual(res_page2.status_code, 200)
        self.assertEqual(len(res_page2.context['page_obj']), 5)
        self.assertFalse(res_page2.context['page_obj'].has_next())

    def test_file_upload_security(self):
        """Verify image file upload validation: accepts genuine images, rejects non-image files."""
        # 1. Valid JPEG image
        valid_img = self._create_test_image("portrait.jpg", "JPEG")
        validated = FileUploadSecurityService.validate_student_photo(valid_img)
        self.assertIsNotNone(validated)

        # 2. Fake executable disguised as an image
        fake_executable = SimpleUploadedFile("malware.exe", b"MZ\x90\x00\x03\x00\x00\x00", content_type="application/x-msdownload")
        with self.assertRaises(ValidationError):
            FileUploadSecurityService.validate_student_photo(fake_executable)

        # 3. Oversized file (> 2MB)
        oversized_data = b"X" * (3 * 1024 * 1024)
        oversized_file = SimpleUploadedFile("large_image.jpg", oversized_data, content_type="image/jpeg")
        with self.assertRaises(ValidationError):
            FileUploadSecurityService.validate_student_photo(oversized_file)

    def test_role_based_access_control(self):
        """Verify role permissions across Teacher, Registrar, Principal, and Anonymous users."""
        # 1. Anonymous user redirected to login
        res_anon = self.client.get(reverse('students_list'))
        self.assertEqual(res_anon.status_code, 302)
        self.assertIn('/login/', res_anon.url)

        # 2. Principal can view list and profile, but CANNOT access registration page
        self.client.login(username='principal_user', password='TestPassword123!')
        res_prin_list = self.client.get(reverse('students_list'))
        self.assertEqual(res_prin_list.status_code, 200)
        res_prin_detail = self.client.get(reverse('student_detail', kwargs={'student_id': self.student_1.pk}))
        self.assertEqual(res_prin_detail.status_code, 200)
        res_prin_reg = self.client.get(reverse('student_register'))
        self.assertEqual(res_prin_reg.status_code, 403)  # Registrar only!

        # 3. Teacher 1 (assigned to Class 9-A) CAN view Student 1 (in Class 9-A)
        self.client.login(username='teacher_math', password='TestPassword123!')
        res_t1_list = self.client.get(reverse('students_list'))
        self.assertEqual(res_t1_list.status_code, 200)
        self.assertContains(res_t1_list, 'Chaltu Tolessa Gemechu')

        res_t1_detail = self.client.get(reverse('student_detail', kwargs={'student_id': self.student_1.pk}))
        self.assertEqual(res_t1_detail.status_code, 200)

        # Teacher CANNOT register students
        res_t1_reg = self.client.get(reverse('student_register'))
        self.assertEqual(res_t1_reg.status_code, 403)

        # 4. Teacher 2 (assigned only to Class 10-A) is BLOCKED (403) from viewing Student 1
        self.client.login(username='teacher_english', password='TestPassword123!')
        res_t2_list = self.client.get(reverse('students_list'))
        self.assertEqual(res_t2_list.status_code, 200)
        self.assertNotContains(res_t2_list, 'Chaltu Tolessa Gemechu')  # Filtered out from directory

        res_t2_detail = self.client.get(reverse('student_detail', kwargs={'student_id': self.student_1.pk}))
        self.assertEqual(res_t2_detail.status_code, 403)  # Blocked: not in assigned class!
