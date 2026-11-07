from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import ValidationError

from accounts.models import User, Role
from academics.models import (
    AcademicYear,
    Grade,
    Section,
    Stream,
    Subject,
    ClassOffering,
    CurriculumSubject,
)
from academics.services import (
    AcademicYearService,
    StructureService,
    ClassOfferingService,
    CurriculumService,
    ClassEnrollmentService,
)
from academics.forms import (
    AcademicYearForm,
    SubjectForm,
    ClassOfferingForm,
)
from students.models import Student, StudentEnrollment
from teachers.models import Teacher, TeacherAssignment


class AcademicManagementTests(TestCase):

    def setUp(self):
        self.client = Client()

        # Roles
        self.role_admin = Role.objects.create(code='ADMIN', name='System Administrator')
        self.role_principal = Role.objects.create(code='PRINCIPAL', name='School Principal')
        self.role_registrar = Role.objects.create(code='REGISTRAR', name='Registrar')
        self.role_teacher = Role.objects.create(code='TEACHER', name='Teacher')

        # Users
        self.user_admin = User.objects.create_user(
            username='admin_test', password='Password123!',
            role=self.role_admin, is_staff=True, is_superuser=True
        )
        self.user_principal = User.objects.create_user(
            username='principal_test', password='Password123!', role=self.role_principal
        )
        self.user_registrar = User.objects.create_user(
            username='registrar_test', password='Password123!', role=self.role_registrar
        )
        self.user_teacher = User.objects.create_user(
            username='teacher_test', password='Password123!', role=self.role_teacher
        )
        self.user_other_teacher = User.objects.create_user(
            username='teacher_other', password='Password123!', role=self.role_teacher
        )

        # Academic Years
        self.ay_2026 = AcademicYear.objects.create(
            name="2026/2027 Academic Year", code="2026-2027",
            start_date=date(2026, 9, 1), end_date=date(2027, 6, 30),
            is_current=True, is_closed=False
        )
        self.ay_2025 = AcademicYear.objects.create(
            name="2025/2026 Academic Year", code="2025-2026",
            start_date=date(2025, 9, 1), end_date=date(2026, 6, 30),
            is_current=False, is_closed=True
        )

        # Structure
        self.grade_9 = Grade.objects.create(name="Grade 9", level=9, is_active=True)
        self.grade_10 = Grade.objects.create(name="Grade 10", level=10, is_active=True)
        self.grade_11 = Grade.objects.create(name="Grade 11", level=11, is_active=True)

        self.sec_a = Section.objects.create(name="A", is_active=True)
        self.sec_b = Section.objects.create(name="B", is_active=True)

        self.stream_nat = Stream.objects.create(name="Natural Science", code="NAT", is_active=True)
        self.stream_soc = Stream.objects.create(name="Social Science", code="SOC", is_active=True)

        self.subj_math = Subject.objects.create(name="Mathematics", code="MATH101", is_active=True)
        self.subj_eng = Subject.objects.create(name="English", code="ENG101", is_active=True)
        self.subj_phy = Subject.objects.create(name="Physics", code="PHY101", is_active=True)

        # Teacher Profile â€” use actual Teacher model field names
        self.teacher_profile = Teacher.objects.create(
            user=self.user_teacher,
            employee_id="T-2026-0001",
            first_name="Abebe",
            father_name="Bikila",
            grandfather_name="Itefa",
            gender="M",
            employment_status="ACTIVE",
            specialization="Mathematics",
            qualification="B.Ed in Mathematics",
            joining_date=date(2020, 9, 1),
        )

        # Student Profiles â€” use actual Student model field names
        self.student_1 = Student.objects.create(
            admission_number="ST-2026-0001",
            first_name="Chala",
            father_name="Tadesse",
            grandfather_name="Olkeba",
            gender="M",
            date_of_birth=date(2010, 5, 12),
            emergency_contact_name="Tadesse Olkeba",
            emergency_contact_phone="0911000001",
            emergency_contact_relation="Father",
            status="ACTIVE"
        )
        self.student_2 = Student.objects.create(
            admission_number="ST-2026-0002",
            first_name="Almaz",
            father_name="Kebede",
            grandfather_name="Hirpa",
            gender="F",
            date_of_birth=date(2010, 8, 20),
            emergency_contact_name="Kebede Hirpa",
            emergency_contact_phone="0911000002",
            emergency_contact_relation="Father",
            status="ACTIVE"
        )

    # -------------------------------------------------------------------------
    # 1. Academic Year Tests
    # -------------------------------------------------------------------------

    def test_academic_year_date_validation_form(self):
        """Form rejects end date before start date."""
        form = AcademicYearForm(data={
            'name': 'Form Invalid Year',
            'code': 'FORM-INV',
            'start_date': '2026-10-01',
            'end_date': '2026-09-01',
            'is_current': False,
            'is_closed': False,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('end_date', form.errors)

    def test_academic_year_model_clean_validation(self):
        """Model clean() rejects start >= end date."""
        yr = AcademicYear(
            name="Bad Dates Year", code="BAD-01",
            start_date=date(2026, 12, 1), end_date=date(2026, 5, 1)
        )
        with self.assertRaises(ValidationError):
            yr.clean()

    def test_single_active_academic_year_enforcement(self):
        """Activating a year via model.save() deactivates all others."""
        self.assertTrue(self.ay_2026.is_current)

        ay_new = AcademicYear.objects.create(
            name="2027/2028 Academic Year", code="2027-2028",
            start_date=date(2027, 9, 1), end_date=date(2028, 6, 30),
            is_current=False
        )

        # Activate via service (passes AcademicYear object directly)
        AcademicYearService.activate_year(ay_new, request=None)

        self.ay_2026.refresh_from_db()
        ay_new.refresh_from_db()

        self.assertFalse(self.ay_2026.is_current)
        self.assertTrue(ay_new.is_current)
        self.assertEqual(AcademicYearService.get_current_year(), ay_new)

    def test_academic_year_close_and_reopen(self):
        """Closing a year locks it; reopening it removes the lock."""
        AcademicYearService.close_year(self.ay_2026, request=None)
        self.ay_2026.refresh_from_db()

        self.assertTrue(self.ay_2026.is_closed)
        self.assertFalse(self.ay_2026.is_current)

        AcademicYearService.reopen_year(self.ay_2026, request=None)
        self.ay_2026.refresh_from_db()
        self.assertFalse(self.ay_2026.is_closed)

    # -------------------------------------------------------------------------
    # 2. Structure Tests (Grades, Sections, Streams)
    # -------------------------------------------------------------------------

    def test_grade_toggle_active(self):
        """Toggle grade active state without deleting the grade record."""
        self.assertTrue(self.grade_9.is_active)
        StructureService.toggle_active_state(Grade, self.grade_9.id, request=None)
        self.grade_9.refresh_from_db()
        self.assertFalse(self.grade_9.is_active)

        StructureService.toggle_active_state(Grade, self.grade_9.id, request=None)
        self.grade_9.refresh_from_db()
        self.assertTrue(self.grade_9.is_active)

    def test_section_toggle_active(self):
        """Toggle section active state."""
        self.assertTrue(self.sec_a.is_active)
        StructureService.toggle_active_state(Section, self.sec_a.id, request=None)
        self.sec_a.refresh_from_db()
        self.assertFalse(self.sec_a.is_active)

    def test_stream_toggle_active(self):
        """Toggle stream active state."""
        self.assertTrue(self.stream_nat.is_active)
        StructureService.toggle_active_state(Stream, self.stream_nat.id, request=None)
        self.stream_nat.refresh_from_db()
        self.assertFalse(self.stream_nat.is_active)

    # -------------------------------------------------------------------------
    # 3. Subject Tests
    # -------------------------------------------------------------------------

    def test_subject_unique_code_enforcement(self):
        """Duplicate subject code rejected by form."""
        form = SubjectForm(data={
            'name': 'Another Mathematics',
            'code': 'MATH101',
            'description': 'Duplicate test',
            'is_active': True,
        })
        self.assertFalse(form.is_valid())
        self.assertIn('code', form.errors)

    def test_subject_toggle_active(self):
        """Toggle subject active state preserves historical curriculum data."""
        self.assertTrue(self.subj_math.is_active)
        StructureService.toggle_active_state(Subject, self.subj_math.id, request=None)
        self.subj_math.refresh_from_db()
        self.assertFalse(self.subj_math.is_active)

    # -------------------------------------------------------------------------
    # 4. Class Offering Tests
    # -------------------------------------------------------------------------

    def test_class_offering_creation_and_duplicate_prevention(self):
        """Duplicate class offering for same year/grade/section/stream is rejected."""
        offering1 = ClassOfferingService.create_offering(
            academic_year=self.ay_2026, grade=self.grade_9,
            section=self.sec_a, stream=None, max_capacity=50
        )
        self.assertIn("Grade 9", offering1.display_name)
        self.assertIn("Section A", offering1.display_name)

        with self.assertRaises(ValidationError):
            ClassOfferingService.create_offering(
                academic_year=self.ay_2026, grade=self.grade_9,
                section=self.sec_a, stream=None, max_capacity=50
            )

    def test_class_offering_form_duplicate_validation(self):
        """ClassOfferingForm rejects duplicate via clean()."""
        ClassOffering.objects.create(
            academic_year=self.ay_2026, grade=self.grade_9,
            section=self.sec_a, max_capacity=50
        )
        form = ClassOfferingForm(data={
            'academic_year': self.ay_2026.id, 'grade': self.grade_9.id,
            'section': self.sec_a.id, 'stream': '', 'max_capacity': 50,
        })
        self.assertFalse(form.is_valid())

    def test_class_offering_capacity_and_full_flag(self):
        """Capacity checks update correctly after enrollment."""
        offering = ClassOffering.objects.create(
            academic_year=self.ay_2026, grade=self.grade_9,
            section=self.sec_b, max_capacity=1
        )
        self.assertEqual(offering.enrolled_students_count, 0)
        self.assertFalse(offering.is_full)

        ClassEnrollmentService.enroll_student(
            student=self.student_1, class_offering=offering
        )

        self.assertEqual(offering.enrolled_students_count, 1)
        self.assertTrue(offering.is_full)

        with self.assertRaises(ValidationError):
            ClassEnrollmentService.enroll_student(
                student=self.student_2, class_offering=offering
            )

    # -------------------------------------------------------------------------
    # 5. Curriculum Matrix Tests
    # -------------------------------------------------------------------------

    def test_curriculum_assignment_and_duplicate_prevention(self):
        """Curriculum subject mapping prevents duplicate grade/stream/subject combo."""
        cur = CurriculumService.assign_curriculum_subject(
            grade=self.grade_9, subject=self.subj_math,
            stream=None, credit_hours=5, is_elective=False
        )
        self.assertEqual(cur.credit_hours, 5)

        with self.assertRaises(ValidationError):
            CurriculumService.assign_curriculum_subject(
                grade=self.grade_9, subject=self.subj_math, stream=None, credit_hours=4
            )

    def test_curriculum_stream_specific_assignment(self):
        """A subject can be assigned to a grade+stream combo independently."""
        cur_nat = CurriculumService.assign_curriculum_subject(
            grade=self.grade_11, subject=self.subj_phy,
            stream=self.stream_nat, credit_hours=4
        )
        self.assertEqual(cur_nat.stream, self.stream_nat)

    # -------------------------------------------------------------------------
    # 6. Student Enrollment Tests
    # -------------------------------------------------------------------------

    def test_student_duplicate_enrollment_in_same_year_rejected(self):
        """Student cannot enroll in two classes in the same academic year."""
        offering_1 = ClassOffering.objects.create(
            academic_year=self.ay_2026, grade=self.grade_9,
            section=self.sec_a, max_capacity=50
        )
        offering_2 = ClassOffering.objects.create(
            academic_year=self.ay_2026, grade=self.grade_9,
            section=self.sec_b, max_capacity=50
        )
        ClassEnrollmentService.enroll_student(
            student=self.student_1, class_offering=offering_1
        )
        with self.assertRaises(ValidationError) as ctx:
            ClassEnrollmentService.enroll_student(
                student=self.student_1, class_offering=offering_2
            )
        self.assertIn("already enrolled", str(ctx.exception).lower())

    def test_student_enrollment_persisted_correctly(self):
        """Enrollment record is created and associated to student + offering."""
        offering = ClassOffering.objects.create(
            academic_year=self.ay_2026, grade=self.grade_9,
            section=self.sec_a, max_capacity=50
        )
        enrollment = ClassEnrollmentService.enroll_student(
            student=self.student_1, class_offering=offering
        )
        self.assertEqual(enrollment.student, self.student_1)
        self.assertEqual(enrollment.class_offering, offering)
        self.assertEqual(enrollment.status, 'ACTIVE')

    # -------------------------------------------------------------------------
    # 7. View RBAC Tests
    # -------------------------------------------------------------------------

    def test_principal_read_only_access(self):
        """Principal can list all academic management views (read-only)."""
        self.client.force_login(self.user_principal)
        for url_name in ['academics_years', 'academics_grades', 'academics_subjects', 'class_offering_list']:
            resp = self.client.get(reverse(url_name))
            self.assertEqual(resp.status_code, 200, f"Principal should access {url_name}")

    def test_principal_cannot_create_academic_year(self):
        """Principal is blocked from POST creating an academic year."""
        self.client.force_login(self.user_principal)
        resp = self.client.post(reverse('academic_year_create'), {
            'name': 'Unauthorized Year', 'code': 'UNAUTH',
            'start_date': '2028-09-01', 'end_date': '2029-06-30'
        })
        self.assertEqual(resp.status_code, 403)

    def test_registrar_can_create_academic_year(self):
        """Registrar successfully creates an academic year."""
        self.client.force_login(self.user_registrar)
        resp = self.client.post(reverse('academic_year_create'), {
            'name': '2029/2030 Academic Year', 'code': '2029-2030',
            'start_date': '2029-09-01', 'end_date': '2030-06-30',
            'is_current': False, 'is_closed': False,
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(AcademicYear.objects.filter(code='2029-2030').exists())

    def test_teacher_can_view_assigned_class_cockpit(self):
        """Teacher can view cockpit of a class they are assigned to."""
        offering = ClassOffering.objects.create(
            academic_year=self.ay_2026, grade=self.grade_9,
            section=self.sec_a, max_capacity=50
        )
        TeacherAssignment.objects.create(
            teacher=self.teacher_profile,
            class_offering=offering,
            subject=self.subj_math,
            academic_year=self.ay_2026
        )
        self.client.force_login(self.user_teacher)
        resp = self.client.get(reverse('class_offering_detail', args=[offering.id]))
        self.assertEqual(resp.status_code, 200)

    def test_teacher_blocked_from_unassigned_class_cockpit(self):
        """Teacher is blocked from a class they are NOT assigned to."""
        offering_unassigned = ClassOffering.objects.create(
            academic_year=self.ay_2026, grade=self.grade_10,
            section=self.sec_b, max_capacity=50
        )
        self.client.force_login(self.user_teacher)
        resp = self.client.get(reverse('class_offering_detail', args=[offering_unassigned.id]))
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_user_redirected_to_login(self):
        """Unauthenticated requests are redirected to the login page."""
        resp = self.client.get(reverse('academics_years'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)
