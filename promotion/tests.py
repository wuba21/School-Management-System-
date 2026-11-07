from datetime import date
from decimal import Decimal
from django.test import TestCase, Client
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import Role
from academics.models import AcademicYear, Grade, Section, Stream, Subject, ClassOffering
from students.models import Student, StudentEnrollment
from examinations.models import ExamType, Examination, ExamSubject
from results.models import Mark, StudentResultSummary
from attendance.models import AttendanceSession, AttendanceRecord

from promotion.models import (
    PromotionCriteria,
    PromotionBatch,
    PromotionRecord,
    GraduationRecord,
    StudentStatusHistory
)
from promotion.services import (
    PromotionAssessmentService,
    PromotionBatchService,
    PromotionApprovalService,
    StudentAcademicHistoryService,
    GraduationService,
    PromotionReportService
)

User = get_user_model()


class PromotionModelAndServiceTests(TestCase):
    def setUp(self):
        # 1. Roles & Users
        self.admin_role, _ = Role.objects.get_or_create(code='ADMIN', defaults={'name': 'Administrator'})
        self.principal_role, _ = Role.objects.get_or_create(code='PRINCIPAL', defaults={'name': 'Principal'})
        self.registrar_role, _ = Role.objects.get_or_create(code='REGISTRAR', defaults={'name': 'Registrar'})

        self.admin_user = User.objects.create_superuser(
            username="adminuser",
            email="admin@school.local",
            password="adminpassword123",
            role=self.admin_role
        )
        self.principal_user = User.objects.create_user(
            username="principaluser",
            email="principal@school.local",
            password="principalpassword123",
            role=self.principal_role
        )
        self.registrar_user = User.objects.create_user(
            username="registraruser",
            email="registrar@school.local",
            password="registrarpassword123",
            role=self.registrar_role
        )

        # 2. Academic Years
        self.ay_source = AcademicYear.objects.create(
            name="2026/2027",
            code="AY-2026",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_current=True
        )
        self.ay_target = AcademicYear.objects.create(
            name="2027/2028",
            code="AY-2027",
            start_date=date(2027, 9, 1),
            end_date=date(2028, 6, 30),
            is_current=False
        )

        # 3. Grades & Sections
        self.grade9 = Grade.objects.create(name="Grade 9", level=9)
        self.grade10 = Grade.objects.create(name="Grade 10", level=10)
        self.grade12 = Grade.objects.create(name="Grade 12", level=12)

        self.sec_a = Section.objects.create(name="A")

        # Class Offerings in Source Year
        self.class_g9_source = ClassOffering.objects.create(
            academic_year=self.ay_source,
            grade=self.grade9,
            section=self.sec_a,
            max_capacity=50
        )
        self.class_g12_source = ClassOffering.objects.create(
            academic_year=self.ay_source,
            grade=self.grade12,
            section=self.sec_a,
            max_capacity=50
        )

        # Class Offerings in Target Year
        self.class_g9_target = ClassOffering.objects.create(
            academic_year=self.ay_target,
            grade=self.grade9,
            section=self.sec_a,
            max_capacity=50
        )
        self.class_g10_target = ClassOffering.objects.create(
            academic_year=self.ay_target,
            grade=self.grade10,
            section=self.sec_a,
            max_capacity=50
        )

        # 4. Students
        self.student_pass = Student.objects.create(
            admission_number="STU-001",
            first_name="Abebe",
            father_name="Kebede",
            grandfather_name="Desta",
            gender="M",
            date_of_birth=date(2010, 5, 12),
            status="ACTIVE"
        )
        self.enr_pass = StudentEnrollment.objects.create(
            student=self.student_pass,
            academic_year=self.ay_source,
            class_offering=self.class_g9_source,
            status="ACTIVE"
        )

        self.student_fail = Student.objects.create(
            admission_number="STU-002",
            first_name="Tigist",
            father_name="Haile",
            grandfather_name="Tesfaye",
            gender="F",
            date_of_birth=date(2010, 8, 20),
            status="ACTIVE"
        )
        self.enr_fail = StudentEnrollment.objects.create(
            student=self.student_fail,
            academic_year=self.ay_source,
            class_offering=self.class_g9_source,
            status="ACTIVE"
        )

        # 5. Configurable Criteria Policy
        self.criteria = PromotionCriteria.objects.create(
            name="Majang Secondary Standard Policy",
            code="SEC-TEST-CRIT",
            minimum_average=Decimal("50.00"),
            max_failing_subjects=2,
            minimum_attendance_percentage=Decimal("75.00"),
            is_active=True,
            is_default=True
        )

        # 6. Examination & Results for Testing
        self.exam_type = ExamType.objects.create(name="Final Exam", code="FINAL")
        self.exam = Examination.objects.create(
            name="Semester 2 Final Exam",
            exam_type=self.exam_type,
            academic_year=self.ay_source,
            semester='SEM2',
            start_date=date(2027, 6, 1),
            end_date=date(2027, 6, 15),
            grade=self.grade9,
            created_by=self.admin_user
        )
        self.math = Subject.objects.create(name="Mathematics", code="MATH9", is_active=True)
        self.exam_math = ExamSubject.objects.create(
            examination=self.exam,
            grade=self.grade9,
            subject=self.math,
            max_marks=Decimal("100.00"),
            pass_marks=Decimal("50.00")
        )

        # Record passing result for student_pass
        StudentResultSummary.objects.create(
            student_enrollment=self.enr_pass,
            examination=self.exam,
            total_obtained=Decimal("85.00"),
            total_max=Decimal("100.00"),
            average_mark=Decimal("85.00"),
            overall_grade="B",
            is_complete=True
        )
        Mark.objects.create(
            student_enrollment=self.enr_pass,
            exam_subject=self.exam_math,
            marks_obtained=Decimal("85.00"),
            entered_by=self.admin_user
        )

        # Record failing result for student_fail
        StudentResultSummary.objects.create(
            student_enrollment=self.enr_fail,
            examination=self.exam,
            total_obtained=Decimal("35.00"),
            total_max=Decimal("100.00"),
            average_mark=Decimal("35.00"),
            overall_grade="F",
            is_complete=True
        )
        Mark.objects.create(
            student_enrollment=self.enr_fail,
            exam_subject=self.exam_math,
            marks_obtained=Decimal("35.00"),
            entered_by=self.admin_user
        )

    def test_promotion_assessment_recommendation(self):
        """Pass student gets PROMOTED recommendation; Fail student gets REPEATED."""
        assess_pass = PromotionAssessmentService.assess_student_eligibility(self.enr_pass, self.criteria)
        self.assertEqual(assess_pass['recommended_outcome'], 'PROMOTED')
        self.assertEqual(assess_pass['academic_average'], Decimal("85.00"))
        self.assertEqual(assess_pass['failing_subjects_count'], 0)

        assess_fail = PromotionAssessmentService.assess_student_eligibility(self.enr_fail, self.criteria)
        self.assertEqual(assess_fail['recommended_outcome'], 'REPEATED')
        self.assertEqual(assess_fail['academic_average'], Decimal("35.00"))
        self.assertEqual(assess_fail['failing_subjects_count'], 1)

    def test_grade_12_graduation_recommendation(self):
        """Grade 12 passing student receives GRADUATED recommendation."""
        student_senior = Student.objects.create(
            admission_number="STU-012",
            first_name="Dawit",
            father_name="Bekele",
            grandfather_name="Tolosa",
            gender="M",
            date_of_birth=date(2007, 3, 10),
            status="ACTIVE"
        )
        enr_senior = StudentEnrollment.objects.create(
            student=student_senior,
            academic_year=self.ay_source,
            class_offering=self.class_g12_source,
            status="ACTIVE"
        )
        StudentResultSummary.objects.create(
            student_enrollment=enr_senior,
            examination=self.exam,
            total_obtained=Decimal("78.00"),
            total_max=Decimal("100.00"),
            average_mark=Decimal("78.00"),
            overall_grade="C",
            is_complete=True
        )

        assessment = PromotionAssessmentService.assess_student_eligibility(enr_senior, self.criteria)
        self.assertEqual(assessment['recommended_outcome'], 'GRADUATED')

    def test_batch_creation_and_candidate_population(self):
        """Batch correctly aggregates students and proposes next grade/class."""
        batch = PromotionBatchService.create_batch(
            name="2026/2027 Grade 9 to 10 Promotion",
            academic_year=self.ay_source,
            target_academic_year=self.ay_target,
            grade=self.grade9,
            criteria=self.criteria,
            user=self.registrar_user
        )
        self.assertEqual(batch.status, 'DRAFT')
        self.assertEqual(batch.total_candidates, 2)

        rec_pass = batch.records.get(student=self.student_pass)
        self.assertEqual(rec_pass.recommended_outcome, 'PROMOTED')
        self.assertEqual(rec_pass.next_grade, self.grade10)
        self.assertEqual(rec_pass.next_class_offering, self.class_g10_target)

        rec_fail = batch.records.get(student=self.student_fail)
        self.assertEqual(rec_fail.recommended_outcome, 'REPEATED')
        self.assertEqual(rec_fail.next_grade, self.grade9)
        self.assertEqual(rec_fail.next_class_offering, self.class_g9_target)

    def test_promotion_approval_and_atomic_finalization(self):
        """Full promotion workflow: prepare -> submit -> approve -> finalize enrollments."""
        batch = PromotionBatchService.create_batch(
            name="Grade 9 Promotion Batch",
            academic_year=self.ay_source,
            target_academic_year=self.ay_target,
            grade=self.grade9,
            criteria=self.criteria,
            user=self.registrar_user
        )

        # 1. Submit for review
        PromotionApprovalService.submit_for_review(batch, user=self.registrar_user)
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'SUBMITTED')

        # 2. Committee Review & Approval
        PromotionApprovalService.review_batch(
            batch=batch,
            decision='APPROVED',
            reviewer_user=self.principal_user,
            comments="Approved after faculty board review."
        )
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'APPROVED')
        self.assertEqual(batch.approved_by, self.principal_user)

        # 3. Finalize promotions (atomic execution)
        result = PromotionApprovalService.finalize_promotions(batch, user=self.principal_user)
        self.assertEqual(result['promoted'], 1)
        self.assertEqual(result['repeated'], 1)
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'FINALIZED')

        # Verify Student 1 (Promoted)
        self.enr_pass.refresh_from_db()
        self.assertEqual(self.enr_pass.status, 'PROMOTED')
        new_enr_pass = StudentEnrollment.objects.get(student=self.student_pass, academic_year=self.ay_target)
        self.assertEqual(new_enr_pass.class_offering.grade, self.grade10)
        self.assertEqual(new_enr_pass.status, 'ACTIVE')

        # Verify Student 2 (Repeated)
        self.enr_fail.refresh_from_db()
        self.assertEqual(self.enr_fail.status, 'RETAINED')
        new_enr_fail = StudentEnrollment.objects.get(student=self.student_fail, academic_year=self.ay_target)
        self.assertEqual(new_enr_fail.class_offering.grade, self.grade9)
        self.assertEqual(new_enr_fail.status, 'ACTIVE')

    def test_duplicate_target_enrollment_prevention(self):
        """Prevents duplicate enrollment in target year with atomic transaction safety."""
        batch = PromotionBatchService.create_batch(
            name="Duplicate Test Batch",
            academic_year=self.ay_source,
            target_academic_year=self.ay_target,
            grade=self.grade9,
            criteria=self.criteria,
            user=self.registrar_user
        )
        PromotionApprovalService.submit_for_review(batch)
        PromotionApprovalService.review_batch(batch, 'APPROVED', self.principal_user)

        # Manually create existing enrollment for student_pass in target year
        StudentEnrollment.objects.create(
            student=self.student_pass,
            academic_year=self.ay_target,
            class_offering=self.class_g10_target,
            status="ACTIVE"
        )

        with self.assertRaises(ValidationError):
            PromotionApprovalService.finalize_promotions(batch)

        # Ensure batch status remains APPROVED (rolled back, not finalized)
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'APPROVED')

    def test_student_status_history_transfer_and_withdrawal(self):
        """Records student transfer out, updates student status, and preserves history."""
        history = StudentStatusHistory.objects.create(
            student=self.student_pass,
            status_type='TRANSFER_OUT',
            effective_date=date(2027, 2, 1),
            reason="Family relocation to Gambella town.",
            destination_school="Gambella Comprehensive High School",
            documents_issued="Official Clearance Slip #104",
            authorized_by=self.registrar_user,
            previous_status="ACTIVE",
            new_status="TRANSFERRED"
        )
        self.student_pass.status = 'TRANSFERRED'
        self.student_pass.save()

        # Transcript history preserves everything
        transcript = StudentAcademicHistoryService.get_student_academic_history(self.student_pass)
        self.assertEqual(len(transcript['history_rows']), 1)
        self.assertEqual(transcript['status_changes'].count(), 1)
        self.assertEqual(transcript['status_changes'].first().destination_school, "Gambella Comprehensive High School")

    def test_pdf_and_excel_export_generation(self):
        """Generates valid PDF and Excel files for promotion batch."""
        batch = PromotionBatchService.create_batch(
            name="Export Test Batch",
            academic_year=self.ay_source,
            target_academic_year=self.ay_target,
            grade=self.grade9,
            criteria=self.criteria,
            user=self.registrar_user
        )

        # PDF Roster
        pdf_response = PromotionReportService.export_promotion_batch_pdf(batch)
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response['Content-Type'], 'application/pdf')
        self.assertGreater(len(pdf_response.content), 500)

        # Excel Gradebook
        excel_response = PromotionReportService.export_promotion_batch_excel(batch)
        self.assertEqual(excel_response.status_code, 200)
        self.assertEqual(
            excel_response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        self.assertGreater(len(excel_response.content), 500)


class PromotionViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_role, _ = Role.objects.get_or_create(code='ADMIN', defaults={'name': 'Administrator'})
        self.principal_role, _ = Role.objects.get_or_create(code='PRINCIPAL', defaults={'name': 'Principal'})

        self.admin_user = User.objects.create_superuser(
            username="adminuser",
            email="admin@school.local",
            password="adminpassword123",
            role=self.admin_role
        )

        self.ay1 = AcademicYear.objects.create(
            name="2026/2027",
            code="AY-2026",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_current=True
        )
        self.ay2 = AcademicYear.objects.create(
            name="2027/2028",
            code="AY-2027",
            start_date=date(2027, 9, 1),
            end_date=date(2028, 6, 30),
            is_current=False
        )
        self.grade9 = Grade.objects.create(name="Grade 9", level=9)
        self.sec_a = Section.objects.create(name="A")
        self.class_offering = ClassOffering.objects.create(
            academic_year=self.ay1,
            grade=self.grade9,
            section=self.sec_a,
            max_capacity=50
        )

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
            academic_year=self.ay1,
            class_offering=self.class_offering,
            status="ACTIVE"
        )

        self.batch = PromotionBatch.objects.create(
            name="Grade 9 Promotion Cohort",
            academic_year=self.ay1,
            target_academic_year=self.ay2,
            grade=self.grade9,
            created_by=self.admin_user,
            status='DRAFT'
        )

    def test_promotion_dashboard_view(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('promotion_index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student Promotion & Progression Hub")

    def test_promotion_prepare_view(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('promotion_prepare'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assemble Promotion Evaluation Cohort")

    def test_promotion_batch_detail_view(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('promotion_batch_detail', args=[self.batch.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.batch.name)

    def test_student_academic_history_view(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('student_academic_history', args=[self.student.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Abebe Kebede")
        self.assertContains(response, "STU-001")

    def test_graduation_management_view(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('graduation_management'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Grade 12 Graduation Registry")

    def test_promotion_criteria_view(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('promotion_criteria'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Promotion Criteria & Threshold Policies")
