from datetime import date
from decimal import Decimal
import io
from django.test import TestCase, Client
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import Role
from academics.models import AcademicYear, Grade, Section, Subject, ClassOffering
from students.models import Student, StudentEnrollment
from teachers.models import Teacher
from examinations.models import ExamType, Examination, ExamSubject
from results.models import GradingScale, GradingRange, Mark, ResultApproval, StudentResultSummary
from results.services import MarksService, ResultCalculationService, ReportCardService

User = get_user_model()


class ResultsModelAndServiceTests(TestCase):
    def setUp(self):
        # 1. Academic structures
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
        self.english = Subject.objects.create(name="English", code="ENG9", is_active=True)

        # 2. Students & Enrollments
        self.student1 = Student.objects.create(
            admission_number="STU-001",
            first_name="Abebe",
            father_name="Kebede",
            grandfather_name="Desta",
            gender="M",
            date_of_birth=date(2010, 5, 12),
            status="ACTIVE"
        )
        self.enr1 = StudentEnrollment.objects.create(
            student=self.student1,
            academic_year=self.year,
            class_offering=self.class_offering,
            status="ACTIVE"
        )

        self.student2 = Student.objects.create(
            admission_number="STU-002",
            first_name="Tigist",
            father_name="Haile",
            grandfather_name="Tesfaye",
            gender="F",
            date_of_birth=date(2010, 8, 20),
            status="ACTIVE"
        )
        self.enr2 = StudentEnrollment.objects.create(
            student=self.student2,
            academic_year=self.year,
            class_offering=self.class_offering,
            status="ACTIVE"
        )

        # 3. Roles & Users
        self.admin_role, _ = Role.objects.get_or_create(code='ADMIN', defaults={'name': 'Administrator'})
        self.teacher_role, _ = Role.objects.get_or_create(code='TEACHER', defaults={'name': 'Teacher'})

        self.admin = User.objects.create_superuser(
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

        # 4. Grading Policy
        self.scale = GradingScale.objects.create(
            name="Ethiopian Secondary Standard Scale",
            code="ETH-SEC-TEST",
            is_default=True
        )
        GradingRange.objects.create(grading_scale=self.scale, grade_label="A", min_score=90.0, max_score=100.0, gpa_point=4.0, is_passing=True)
        GradingRange.objects.create(grading_scale=self.scale, grade_label="B", min_score=80.0, max_score=89.99, gpa_point=3.0, is_passing=True)
        GradingRange.objects.create(grading_scale=self.scale, grade_label="C", min_score=60.0, max_score=79.99, gpa_point=2.0, is_passing=True)
        GradingRange.objects.create(grading_scale=self.scale, grade_label="D", min_score=50.0, max_score=59.99, gpa_point=1.0, is_passing=True)
        GradingRange.objects.create(grading_scale=self.scale, grade_label="F", min_score=0.0, max_score=49.99, gpa_point=0.0, is_passing=False)

        # 5. Examination
        self.exam_type = ExamType.objects.create(name="Midterm Exam", code="MIDTERM")
        self.exam = Examination.objects.create(
            name="Semester 1 Midterm",
            exam_type=self.exam_type,
            academic_year=self.year,
            semester='SEM1',
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 15),
            grade=self.grade9,
            created_by=self.admin
        )

        self.exam_math = ExamSubject.objects.create(
            examination=self.exam,
            grade=self.grade9,
            subject=self.math,
            max_marks=Decimal("100.00"),
            pass_marks=Decimal("50.00"),
            weight_percentage=Decimal("100.00")
        )
        self.exam_eng = ExamSubject.objects.create(
            examination=self.exam,
            grade=self.grade9,
            subject=self.english,
            max_marks=Decimal("100.00"),
            pass_marks=Decimal("50.00"),
            weight_percentage=Decimal("100.00")
        )

    def test_grading_scale_score_mapping(self):
        self.assertEqual(self.scale.get_grade_for_score(95).grade_label, "A")
        self.assertEqual(self.scale.get_grade_for_score(85).grade_label, "B")
        self.assertEqual(self.scale.get_grade_for_score(72).grade_label, "C")
        self.assertEqual(self.scale.get_grade_for_score(55).grade_label, "D")
        self.assertEqual(self.scale.get_grade_for_score(35).grade_label, "F")

    def test_marks_bounds_validation(self):
        """Negative marks and marks exceeding maximum are blocked."""
        with self.assertRaises(ValidationError):
            mk_neg = Mark(
                student_enrollment=self.enr1,
                exam_subject=self.exam_math,
                marks_obtained=Decimal("-5.00"),
                entered_by=self.teacher_user
            )
            mk_neg.full_clean()

        with self.assertRaises(ValidationError):
            mk_over = Mark(
                student_enrollment=self.enr1,
                exam_subject=self.exam_math,
                marks_obtained=Decimal("105.00"),
                entered_by=self.teacher_user
            )
            mk_over.full_clean()

    def test_bulk_marks_recording_and_missing_marks_preserved(self):
        """Missing marks must not automatically become 0."""
        entries = [
            {
                'enrollment_id': self.enr1.id,
                'marks_obtained': Decimal("92.50"),
                'is_absent': False,
                'remarks': 'Outstanding'
            },
            {
                'enrollment_id': self.enr2.id,
                'marks_obtained': None, # Unentered/missing
                'is_absent': False,
                'remarks': ''
            }
        ]
        created = MarksService.record_bulk_marks(
            exam_subject=self.exam_math,
            marks_data=entries,
            entered_by_user=self.teacher_user
        )
        self.assertEqual(len(created), 2)

        m1 = Mark.objects.get(student_enrollment=self.enr1, exam_subject=self.exam_math)
        self.assertEqual(m1.marks_obtained, Decimal("92.50"))
        self.assertTrue(m1.is_passing)

        m2 = Mark.objects.get(student_enrollment=self.enr2, exam_subject=self.exam_math)
        self.assertIsNone(m2.marks_obtained)
        self.assertFalse(m2.is_absent)

    def test_marks_workflow_submit_and_verify(self):
        """Teacher submits -> Exam Officer verifies and approves."""
        entries = [
            {'enrollment_id': self.enr1.id, 'marks_obtained': Decimal("85.00"), 'is_absent': False, 'remarks': ''},
            {'enrollment_id': self.enr2.id, 'marks_obtained': Decimal("70.00"), 'is_absent': False, 'remarks': ''},
        ]
        MarksService.record_bulk_marks(self.exam_math, entries, self.teacher_user)

        # Teacher submits
        MarksService.submit_marks_for_review(self.exam_math, self.teacher_user)
        self.exam_math.refresh_from_db()
        self.assertEqual(self.exam_math.status, 'SUBMITTED')

        # Registrar approves
        MarksService.review_and_verify_marks(
            exam_subject=self.exam_math,
            reviewer_user=self.admin,
            decision='APPROVED',
            comments='All scores verified against physical scripts.'
        )
        self.exam_math.refresh_from_db()
        self.assertEqual(self.exam_math.status, 'VERIFIED')
        self.assertEqual(self.exam_math.approvals.count(), 1)

    def test_result_calculations_and_ranking(self):
        """Calculates accurate percentages, averages, grades, and class ranks."""
        # Enter Math marks
        MarksService.record_bulk_marks(
            self.exam_math,
            [
                {'enrollment_id': self.enr1.id, 'marks_obtained': Decimal("90.00"), 'is_absent': False},
                {'enrollment_id': self.enr2.id, 'marks_obtained': Decimal("60.00"), 'is_absent': False},
            ],
            self.teacher_user
        )
        # Enter English marks
        MarksService.record_bulk_marks(
            self.exam_eng,
            [
                {'enrollment_id': self.enr1.id, 'marks_obtained': Decimal("94.00"), 'is_absent': False},
                {'enrollment_id': self.enr2.id, 'marks_obtained': Decimal("80.00"), 'is_absent': False},
            ],
            self.teacher_user
        )

        summaries = ResultCalculationService.calculate_examination_results(
            examination=self.exam,
            grading_scale=self.scale
        )
        self.assertEqual(len(summaries), 2)

        # Student 1: 90 + 94 = 184 / 200 => 92% => Rank 1, Grade A
        s1_summary = StudentResultSummary.objects.get(student_enrollment=self.enr1, examination=self.exam)
        self.assertEqual(s1_summary.total_obtained, Decimal("184.00"))
        self.assertEqual(s1_summary.average_mark, Decimal("92.00"))
        self.assertEqual(s1_summary.overall_grade, "A")
        self.assertEqual(s1_summary.rank, 1)

        # Student 2: 60 + 80 = 140 / 200 => 70% => Rank 2, Grade C
        s2_summary = StudentResultSummary.objects.get(student_enrollment=self.enr2, examination=self.exam)
        self.assertEqual(s2_summary.total_obtained, Decimal("140.00"))
        self.assertEqual(s2_summary.average_mark, Decimal("70.00"))
        self.assertEqual(s2_summary.overall_grade, "C")
        self.assertEqual(s2_summary.rank, 2)

    def test_pdf_report_card_export(self):
        """Generates valid non-empty PDF bytes for student report card."""
        # Set up marks and summary
        MarksService.record_bulk_marks(
            self.exam_math,
            [{'enrollment_id': self.enr1.id, 'marks_obtained': Decimal("95.00"), 'is_absent': False}],
            self.teacher_user
        )
        ResultCalculationService.calculate_examination_results(self.exam, self.scale)

        report_data = ReportCardService.get_report_card_data(self.enr1, self.exam)
        response = ReportCardService.export_report_card_pdf(report_data, filename="test_card.pdf")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertGreater(len(response.content), 500)

    def test_excel_gradebook_export(self):
        """Generates valid Excel spreadsheet response with openpyxl."""
        MarksService.record_bulk_marks(
            self.exam_math,
            [{'enrollment_id': self.enr1.id, 'marks_obtained': Decimal("95.00"), 'is_absent': False}],
            self.teacher_user
        )
        ResultCalculationService.calculate_examination_results(self.exam, self.scale)

        response = ReportCardService.export_class_results_excel(self.exam)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        self.assertGreater(len(response.content), 500)


class ResultsViewTests(TestCase):
    def setUp(self):
        self.client = Client()
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

        self.student = Student.objects.create(
            admission_number="STU-001",
            first_name="Abebe",
            father_name="Kebede",
            grandfather_name="Desta",
            gender="M",
            date_of_birth=date(2010, 5, 12),
            status="ACTIVE"
        )
        self.enr = StudentEnrollment.objects.create(
            student=self.student,
            academic_year=self.year,
            class_offering=self.class_offering,
            status="ACTIVE"
        )

        self.admin_role, _ = Role.objects.get_or_create(code='ADMIN', defaults={'name': 'Administrator'})
        self.admin = User.objects.create_superuser(
            username="adminuser",
            email="admin@school.local",
            password="adminpassword123",
            role=self.admin_role
        )

        self.exam_type = ExamType.objects.create(name="Midterm Exam", code="MIDTERM")
        self.exam = Examination.objects.create(
            name="Semester 1 Midterm",
            exam_type=self.exam_type,
            academic_year=self.year,
            semester='SEM1',
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 15),
            grade=self.grade9,
            created_by=self.admin
        )
        self.exam_subject = ExamSubject.objects.create(
            examination=self.exam,
            grade=self.grade9,
            subject=self.math,
            max_marks=Decimal("100.00"),
            pass_marks=Decimal("50.00")
        )

    def test_results_dashboard_view(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('results_index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Results & Assessment Operations")

    def test_marks_entry_view_get(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('marks_entry', args=[self.exam_subject.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Marks Entry: Mathematics (Grade 9)")
        self.assertContains(response, "STU-001")

    def test_marks_entry_save_draft_post(self):
        self.client.force_login(self.admin)
        post_data = {
            f'marks_{self.enr.id}': '88.50',
            f'remarks_{self.enr.id}': 'Good work',
            'save_draft': 'true'
        }
        response = self.client.post(reverse('marks_entry', args=[self.exam_subject.id]), data=post_data)
        self.assertEqual(response.status_code, 302)
        mark = Mark.objects.get(student_enrollment=self.enr, exam_subject=self.exam_subject)
        self.assertEqual(mark.marks_obtained, Decimal("88.50"))
        self.assertEqual(mark.remarks, 'Good work')

    def test_published_results_view(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('published_results', args=[self.exam.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Master Gradebook & Rankings")

    def test_student_report_card_view_html_and_pdf(self):
        self.client.force_login(self.admin)
        # Save marks and calculate
        MarksService.record_bulk_marks(
            self.exam_subject,
            [{'enrollment_id': self.enr.id, 'marks_obtained': Decimal("90.00"), 'is_absent': False}],
            self.admin
        )
        ResultCalculationService.calculate_examination_results(self.exam)

        # HTML report card
        response_html = self.client.get(reverse('student_report_card', args=[self.exam.id, self.student.id]))
        self.assertEqual(response_html.status_code, 200)
        self.assertContains(response_html, "Official Academic Report Card")
        self.assertContains(response_html, "Abebe Kebede")

        # PDF download
        response_pdf = self.client.get(reverse('student_report_card', args=[self.exam.id, self.student.id]) + "?format=pdf")
        self.assertEqual(response_pdf.status_code, 200)
        self.assertEqual(response_pdf['Content-Type'], 'application/pdf')
