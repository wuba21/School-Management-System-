from datetime import date, timedelta
from decimal import Decimal
from django.test import TestCase, Client
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import Role
from academics.models import AcademicYear, Grade, Section, Stream, Subject, CurriculumSubject, ClassOffering
from examinations.models import ExamType, Examination, ExamSubject
from examinations.services import ExaminationService, ExamSubjectService

User = get_user_model()


class ExaminationModelAndServiceTests(TestCase):
    def setUp(self):
        # Roles
        self.admin_role, _ = Role.objects.get_or_create(code='ADMIN', defaults={'name': 'Administrator'})
        self.teacher_role, _ = Role.objects.get_or_create(code='TEACHER', defaults={'name': 'Teacher'})

        # Academic structures
        self.year = AcademicYear.objects.create(
            name="2026/2027",
            code="AY-2026",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_current=True
        )
        self.grade9 = Grade.objects.create(name="Grade 9", level=9)
        self.section_a = Section.objects.create(name="A")
        self.class_offering = ClassOffering.objects.create(
            academic_year=self.year,
            grade=self.grade9,
            section=self.section_a,
            max_capacity=50
        )

        self.math = Subject.objects.create(name="Mathematics", code="MATH9", is_active=True)
        self.physics = Subject.objects.create(name="Physics", code="PHYS9", is_active=True)

        # Curriculum subject
        CurriculumSubject.objects.create(
            grade=self.grade9,
            subject=self.math,
            credit_hours=5,
            is_elective=False
        )

        # Exam Type
        self.midterm_type = ExamType.objects.create(
            name="Midterm Examination",
            code="MIDTERM",
            default_weight=Decimal("30.00")
        )

        # Users
        self.admin_user = User.objects.create_superuser(
            username="adminuser",
            email="admin@school.local",
            password="adminpassword123",
            role=self.admin_role
        )
        self.teacher_user = User.objects.create_user(
            username="teacheruser",
            email="teacher@school.local",
            password="teacherpassword123",
            role=self.teacher_role
        )

    def test_exam_type_creation(self):
        self.assertEqual(str(self.midterm_type), "Midterm Examination (MIDTERM)")
        self.assertEqual(self.midterm_type.default_weight, Decimal("30.00"))

    def test_examination_date_validation(self):
        """End date cannot be prior to start date."""
        exam = Examination(
            name="Invalid Date Exam",
            exam_type=self.midterm_type,
            academic_year=self.year,
            semester='SEM1',
            start_date=date(2026, 11, 20),
            end_date=date(2026, 11, 10),
            created_by=self.admin_user
        )
        with self.assertRaises(ValidationError):
            exam.full_clean()

    def test_examination_service_create_and_close(self):
        exam = ExaminationService.create_examination(
            name="Semester 1 Midterm",
            exam_type=self.midterm_type,
            academic_year=self.year,
            semester='SEM1',
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 15),
            grade=self.grade9,
            created_by=self.admin_user
        )
        self.assertEqual(exam.status, 'ACTIVE')
        self.assertFalse(exam.is_closed)

        # Close exam
        ExaminationService.close_examination(exam, user=self.admin_user)
        self.assertEqual(exam.status, 'CLOSED')
        self.assertTrue(exam.is_closed)

        # Reopen exam
        ExaminationService.reopen_examination(exam, user=self.admin_user)
        self.assertEqual(exam.status, 'ACTIVE')
        self.assertFalse(exam.is_closed)

    def test_exam_subject_configuration(self):
        exam = ExaminationService.create_examination(
            name="Grade 9 Midterm",
            exam_type=self.midterm_type,
            academic_year=self.year,
            semester='SEM1',
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 15),
            grade=self.grade9,
            created_by=self.admin_user
        )

        es = ExamSubjectService.configure_subject(
            examination=exam,
            grade=self.grade9,
            subject=self.math,
            max_marks=Decimal("100.00"),
            pass_marks=Decimal("50.00"),
            weight_percentage=Decimal("100.00")
        )
        self.assertEqual(es.max_marks, Decimal("100.00"))
        self.assertEqual(es.pass_marks, Decimal("50.00"))

        # Prevent duplicate subject configuration in same exam
        with self.assertRaises(ValidationError):
            ExamSubjectService.configure_subject(
                examination=exam,
                grade=self.grade9,
                subject=self.math,
                max_marks=Decimal("100.00"),
                pass_marks=Decimal("50.00")
            )

    def test_exam_subject_marks_bounds_validation(self):
        """Pass marks cannot exceed maximum marks."""
        exam = ExaminationService.create_examination(
            name="Grade 9 Midterm",
            exam_type=self.midterm_type,
            academic_year=self.year,
            semester='SEM1',
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 15),
            grade=self.grade9,
            created_by=self.admin_user
        )
        with self.assertRaises(ValidationError):
            es = ExamSubject(
                examination=exam,
                grade=self.grade9,
                subject=self.physics,
                max_marks=Decimal("50.00"),
                pass_marks=Decimal("60.00")
            )
            es.full_clean()

    def test_auto_populate_curriculum_subjects(self):
        exam = ExaminationService.create_examination(
            name="Grade 9 Midterm",
            exam_type=self.midterm_type,
            academic_year=self.year,
            semester='SEM1',
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 15),
            grade=self.grade9,
            created_by=self.admin_user
        )
        created_count = ExamSubjectService.auto_configure_from_curriculum(exam)
        self.assertEqual(created_count, 1)
        self.assertTrue(ExamSubject.objects.filter(examination=exam, subject=self.math).exists())


class ExaminationViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_role, _ = Role.objects.get_or_create(code='ADMIN', defaults={'name': 'Administrator'})
        self.year = AcademicYear.objects.create(
            name="2026/2027",
            code="AY-2026",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_current=True
        )
        self.grade9 = Grade.objects.create(name="Grade 9", level=9)
        self.midterm_type = ExamType.objects.create(name="Midterm Examination", code="MIDTERM")

        self.admin = User.objects.create_superuser(
            username="adminuser",
            email="admin@school.local",
            password="adminpassword123",
            role=self.admin_role
        )
        self.exam = Examination.objects.create(
            name="Semester 1 Midterm",
            exam_type=self.midterm_type,
            academic_year=self.year,
            semester='SEM1',
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 15),
            grade=self.grade9,
            created_by=self.admin
        )

    def test_dashboard_view_authenticated(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('examinations_index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Examinations Management Dashboard")
        self.assertContains(response, "Semester 1 Midterm")

    def test_examination_list_view(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('examination_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Examinations Directory")
        self.assertContains(response, "Semester 1 Midterm")

    def test_examination_detail_view(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('examination_detail', args=[self.exam.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.exam.name)

    def test_examination_create_view_post(self):
        self.client.force_login(self.admin)
        post_data = {
            'name': 'Semester 1 Final Examination',
            'exam_type': self.midterm_type.id,
            'academic_year': self.year.id,
            'semester': 'SEM1',
            'grade': self.grade9.id,
            'class_offering': '',
            'start_date': '2026-12-01',
            'end_date': '2026-12-15',
        }
        response = self.client.post(reverse('examination_create'), data=post_data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Examination.objects.filter(name='Semester 1 Final Examination').exists())
