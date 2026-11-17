"""
Unit and Integration Tests for Step 20:
Professional English-Only Student Report Card Management in SSMS.

Tests:
1. English-only report card HTML rendering and label verification
2. Accurate database marks and weighted score calculations
3. Multi-grade and curriculum stream handling (Grades 9-10 General, 11-12 Natural/Social Science)
4. Role-Based Access Control (Admin, Principal, Registrar, Assigned Teacher vs Unassigned Teacher)
5. Vector PDF generation with ReportLab (valid bytes, headers, tables, signatures)
6. Dual calendar representation (Gregorian and Ethiopian calendar notation)
7. Missing academic records / unentered marks handled gracefully
8. Report card printing parameters and Hub filtering
"""

from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import translation
from django.core.exceptions import PermissionDenied

from accounts.models import Role
from academics.models import AcademicYear, Grade, Section, Stream, Subject, ClassOffering
from students.models import Student, StudentEnrollment
from teachers.models import Teacher, TeacherAssignment
from examinations.models import Examination, ExamType, ExamSubject
from results.models import GradingScale, GradingRange, Mark, StudentResultSummary
from results.services import ReportCardService, ResultCalculationService, MarksService
from attendance.models import AttendanceSession, AttendanceRecord
from promotion.models import PromotionBatch, PromotionRecord

User = get_user_model()


class Step20ReportCardComprehensiveTests(TestCase):
    """Rigorous test suite for English-only student report card management."""

    @classmethod
    def setUpTestData(cls):
        # 1. User Roles
        cls.admin_role, _ = Role.objects.get_or_create(code='ADMIN', defaults={'name': 'System Administrator'})
        cls.principal_role, _ = Role.objects.get_or_create(code='PRINCIPAL', defaults={'name': 'School Principal'})
        cls.registrar_role, _ = Role.objects.get_or_create(code='REGISTRAR', defaults={'name': 'Registrar Officer'})
        cls.teacher_role, _ = Role.objects.get_or_create(code='TEACHER', defaults={'name': 'Teacher'})

        # 2. Staff Accounts
        cls.admin_user = User.objects.create_user(
            username='admin_step20', password='password123', role=cls.admin_role, is_staff=True, is_superuser=True
        )
        cls.principal_user = User.objects.create_user(
            username='principal_step20', password='password123', role=cls.principal_role
        )
        cls.registrar_user = User.objects.create_user(
            username='registrar_step20', password='password123', role=cls.registrar_role
        )

        cls.teacher1_user = User.objects.create_user(
            username='teacher1_step20', password='password123', role=cls.teacher_role
        )
        cls.teacher2_user = User.objects.create_user(
            username='teacher2_step20', password='password123', role=cls.teacher_role
        )
        cls.unassigned_user = User.objects.create_user(
            username='unassigned_step20', password='password123', role=None
        )

        cls.teacher1 = Teacher.objects.create(
            user=cls.teacher1_user,
            first_name='Ayele',
            father_name='Mulu',
            employee_id='T-MET-01',
            joining_date=date(2020, 9, 1)
        )
        cls.teacher2 = Teacher.objects.create(
            user=cls.teacher2_user,
            first_name='Chala',
            father_name='Tolosa',
            employee_id='T-MET-02',
            joining_date=date(2021, 9, 1)
        )

        # 3. Academic Structure
        cls.academic_year = AcademicYear.objects.create(
            name='2026/2027',
            code='AY2026',
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_current=True
        )

        cls.grade10 = Grade.objects.create(name='Grade 10', level=10)
        cls.grade11 = Grade.objects.create(name='Grade 11', level=11)
        cls.grade12 = Grade.objects.create(name='Grade 12', level=12)

        cls.stream_natural = Stream.objects.create(name='Natural Science', code='NAT')
        cls.stream_social = Stream.objects.create(name='Social Science', code='SOC')

        cls.sec_a = Section.objects.create(name='A')
        cls.sec_b = Section.objects.create(name='B')

        # Class Offerings:
        # Grade 10-A (General Secondary, No Stream)
        cls.offering_10a = ClassOffering.objects.create(
            academic_year=cls.academic_year,
            grade=cls.grade10,
            section=cls.sec_a,
            stream=None
        )
        # Grade 11-A (Natural Science)
        cls.offering_11a = ClassOffering.objects.create(
            academic_year=cls.academic_year,
            grade=cls.grade11,
            section=cls.sec_a,
            stream=cls.stream_natural
        )
        # Grade 12-B (Social Science)
        cls.offering_12b = ClassOffering.objects.create(
            academic_year=cls.academic_year,
            grade=cls.grade12,
            section=cls.sec_b,
            stream=cls.stream_social
        )

        # Subjects
        cls.subj_eng = Subject.objects.create(name='English Language', code='ENG10')
        cls.subj_math = Subject.objects.create(name='Mathematics', code='MAT10')
        cls.subj_phy = Subject.objects.create(name='Physics', code='PHY11')

        # Teacher 1 teaches in Grade 10-A; Teacher 2 teaches in Grade 11-A
        TeacherAssignment.objects.create(
            teacher=cls.teacher1,
            class_offering=cls.offering_10a,
            subject=cls.subj_eng,
            academic_year=cls.academic_year
        )
        TeacherAssignment.objects.create(
            teacher=cls.teacher2,
            class_offering=cls.offering_11a,
            subject=cls.subj_phy,
            academic_year=cls.academic_year
        )

        # 4. Students & Enrollments
        cls.student1 = Student.objects.create(
            admission_number='MSS/2026/001',
            first_name='Abebe',
            father_name='Kebede',
            grandfather_name='Wolde',
            gender='M',
            date_of_birth=date(2010, 5, 12)
        )
        cls.enr1 = StudentEnrollment.objects.create(
            student=cls.student1,
            academic_year=cls.academic_year,
            class_offering=cls.offering_10a,
            status='ACTIVE'
        )

        cls.student2 = Student.objects.create(
            admission_number='MSS/2026/002',
            first_name='Derartu',
            father_name='Tulu',
            grandfather_name='Bekele',
            gender='F',
            date_of_birth=date(2009, 3, 20)
        )
        cls.enr2 = StudentEnrollment.objects.create(
            student=cls.student2,
            academic_year=cls.academic_year,
            class_offering=cls.offering_11a,
            status='ACTIVE'
        )

        # 5. Examination Setup
        cls.exam_type, _ = ExamType.objects.get_or_create(name='Final Exam', defaults={'code': 'FINAL'})
        cls.exam = Examination.objects.create(
            name='Semester 1 Final Examination',
            academic_year=cls.academic_year,
            exam_type=cls.exam_type,
            semester='SEM1',
            start_date=date(2026, 12, 10),
            end_date=date(2026, 12, 24),
            status='PUBLISHED'
        )

        cls.es_eng = ExamSubject.objects.create(
            examination=cls.exam,
            grade=cls.grade10,
            subject=cls.subj_eng,
            max_marks=Decimal('100.00'),
            pass_marks=Decimal('50.00'),
            status='PENDING'
        )
        cls.es_math = ExamSubject.objects.create(
            examination=cls.exam,
            grade=cls.grade10,
            subject=cls.subj_math,
            max_marks=Decimal('100.00'),
            pass_marks=Decimal('50.00'),
            status='PENDING'
        )
        cls.es_phy = ExamSubject.objects.create(
            examination=cls.exam,
            grade=cls.grade11,
            subject=cls.subj_phy,
            max_marks=Decimal('100.00'),
            pass_marks=Decimal('50.00'),
            status='PENDING'
        )

        # 6. Default Grading Scale
        cls.scale = GradingScale.objects.create(name='Ethiopian Secondary Standard', is_default=True)
        GradingRange.objects.create(grading_scale=cls.scale, grade_label='A', min_score=Decimal('85.0'), max_score=Decimal('100.0'), description='Excellent', is_passing=True)
        GradingRange.objects.create(grading_scale=cls.scale, grade_label='B', min_score=Decimal('70.0'), max_score=Decimal('84.99'), description='Very Good', is_passing=True)
        GradingRange.objects.create(grading_scale=cls.scale, grade_label='C', min_score=Decimal('50.0'), max_score=Decimal('69.99'), description='Satisfactory', is_passing=True)
        GradingRange.objects.create(grading_scale=cls.scale, grade_label='F', min_score=Decimal('0.0'), max_score=Decimal('49.99'), description='Failing', is_passing=False)

        # 7. Marks Entry & Calculations for Student 1
        MarksService.record_bulk_marks(
            cls.es_eng,
            [{'enrollment_id': cls.enr1.id, 'marks_obtained': Decimal('92.00'), 'is_absent': False, 'remarks': 'Outstanding command'}],
            cls.teacher1_user
        )
        MarksService.record_bulk_marks(
            cls.es_math,
            [{'enrollment_id': cls.enr1.id, 'marks_obtained': Decimal('88.00'), 'is_absent': False, 'remarks': 'Great problem solving'}],
            cls.teacher1_user
        )
        cls.es_eng.status = 'PUBLISHED'
        cls.es_eng.save()
        cls.es_math.status = 'PUBLISHED'
        cls.es_math.save()
        cls.es_phy.status = 'PUBLISHED'
        cls.es_phy.save()

        ResultCalculationService.calculate_examination_results(cls.exam, cls.scale)

        # 8. Attendance Profile for Student 1
        att_session = AttendanceSession.objects.create(
            academic_year=cls.academic_year,
            class_offering=cls.offering_10a,
            date=date(2026, 10, 5),
            session_type='DAILY',
            status='OPEN'
        )
        AttendanceRecord.objects.create(
            attendance_session=att_session,
            student_enrollment=cls.enr1,
            status='PRESENT'
        )
        att_session.status = 'CLOSED'
        att_session.save()

        # 9. Official Promotion Record for Student 1
        next_ay = AcademicYear.objects.create(
            name='2027/2028',
            code='AY2027',
            start_date=date(2027, 9, 1),
            end_date=date(2028, 6, 30),
            is_current=False
        )
        promo_batch = PromotionBatch.objects.create(
            name='Grade 10 Promotion Batch 2026/2027',
            academic_year=cls.academic_year,
            target_academic_year=next_ay,
            grade=cls.grade10,
            status='APPROVED'
        )
        PromotionRecord.objects.create(
            batch=promo_batch,
            student_enrollment=cls.enr1,
            student=cls.student1,
            previous_academic_year=cls.academic_year,
            next_academic_year=next_ay,
            previous_grade=cls.grade10,
            next_grade=cls.grade11,
            previous_class_offering=cls.offering_10a,
            final_outcome='PROMOTED',
            decision_status='APPROVED',
            remarks='Promoted to Grade 11 based on academic excellence.'
        )

    def test_english_only_report_card_data_compilation(self):
        """Verifies report card dictionary contains complete English-only academic metadata."""
        data = ReportCardService.get_report_card_data(self.enr1, self.exam)

        # Student & School Information
        self.assertEqual(data['student'].full_name, 'Abebe Kebede Wolde')
        self.assertEqual(data['student'].admission_number, 'MSS/2026/001')
        self.assertEqual(data['school_info']['name'], 'METTI SECONDARY SCHOOL')
        self.assertIn('Majang Zone, Gambella Region', data['school_info']['location'])

        # Dual Calendar Displays
        self.assertIn('2026/2027 G.C.', data['academic_year_display'])
        self.assertIn('E.C.', data['academic_year_display'])
        self.assertIn('G.C.', data['issued_date_display'])
        self.assertIn('E.C.', data['issued_date_display'])

        # Stream
        self.assertEqual(data['stream_name'], 'General Secondary')

        # Academic Metrics
        self.assertEqual(len(data['subjects']), 2)
        self.assertEqual(data['metrics']['total_obtained'], Decimal('180.00'))
        self.assertEqual(data['metrics']['total_max'], Decimal('200.00'))
        self.assertEqual(data['metrics']['percentage'], Decimal('90.00'))
        self.assertEqual(data['metrics']['overall_grade'], 'A')
        self.assertEqual(data['metrics']['standing'], 'Pass / Promoted in Good Standing')

        # Attendance Record
        self.assertEqual(data['attendance']['total_sessions'], 1)
        self.assertEqual(data['attendance']['present'], 1)
        self.assertEqual(data['attendance']['rate'], 100.0)

        # Officially Approved Promotion Status
        self.assertTrue(data['promotion']['is_approved'])
        self.assertIn('Promoted', data['promotion']['status'])
        self.assertEqual(data['promotion']['next_grade'], 'Grade 11')

    def test_different_grades_and_curriculum_streams(self):
        """Verifies Grade 11 Natural Science student displays correct stream and pending promotion."""
        data = ReportCardService.get_report_card_data(self.enr2, self.exam)

        self.assertEqual(data['grade_name'], 'Grade 11')
        self.assertEqual(data['stream_name'], 'Natural Science')
        # Student 2 has no promotion record yet
        self.assertFalse(data['promotion']['is_approved'])
        self.assertEqual(data['promotion']['status'], 'Pending Official Committee Evaluation')

    def test_html_report_card_view_english_rendering(self):
        """Verifies the Web HTML report card renders all English headings and tables."""
        self.client.force_login(self.admin_user)
        url = reverse('student_report_card', args=[self.exam.id, self.student1.id])
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Check English headings
        self.assertContains(response, "METTI SECONDARY SCHOOL")
        self.assertContains(response, "Official Academic Report Card")
        self.assertContains(response, "Subject Description")
        self.assertContains(response, "Teacher Remarks")
        self.assertContains(response, "Academic Performance Summary")
        self.assertContains(response, "Student Attendance Record")
        self.assertContains(response, "Homeroom Teacher")
        self.assertContains(response, "Exam Officer / Registrar")
        self.assertContains(response, "School Principal")
        # Check student data
        self.assertContains(response, "MSS/2026/001")
        self.assertContains(response, "Abebe Kebede Wolde")
        self.assertContains(response, "English Language")
        self.assertContains(response, "Mathematics")

    def test_pdf_report_card_export_generation(self):
        """Verifies PDF report card returns valid application/pdf binary with headers."""
        self.client.force_login(self.admin_user)
        url = reverse('student_report_card', args=[self.exam.id, self.student1.id]) + "?format=pdf"
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('ReportCard_MSS_2026_001', response['Content-Disposition'])
        # Valid PDF begins with %PDF- header
        self.assertTrue(response.content.startswith(b'%PDF-'))
        self.assertGreater(len(response.content), 2000)

    def test_rbac_unauthorized_access_prevented(self):
        """Verifies role permissions: unassigned users and unassigned teachers are blocked."""
        url = reverse('student_report_card', args=[self.exam.id, self.student1.id])

        # 1. Unassigned staff has no permission
        self.client.force_login(self.unassigned_user)
        response_unassigned = self.client.get(url)
        self.assertEqual(response_unassigned.status_code, 403)

        # 2. Teacher 2 (assigned to Grade 11-A) cannot view Student 1 (Grade 10-A)
        self.client.force_login(self.teacher2_user)
        response_teacher2 = self.client.get(url)
        self.assertEqual(response_teacher2.status_code, 403)

        # 3. Teacher 1 (assigned to Grade 10-A) CAN view Student 1
        self.client.force_login(self.teacher1_user)
        response_teacher1 = self.client.get(url)
        self.assertEqual(response_teacher1.status_code, 200)

        # 4. Principal and Registrar can view any student
        self.client.force_login(self.principal_user)
        self.assertEqual(self.client.get(url).status_code, 200)

        self.client.force_login(self.registrar_user)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_report_card_hub_view_and_filtering(self):
        """Verifies report card management hub search and filter capabilities."""
        self.client.force_login(self.admin_user)
        hub_url = reverse('report_card_hub')

        # 1. Basic hub rendering
        response = self.client.get(hub_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Student Report Card Management")
        self.assertContains(response, "Abebe Kebede Wolde")
        self.assertContains(response, "Derartu Tulu Bekele")

        # 2. Search query filter
        response_search = self.client.get(hub_url, {'search': 'Abebe'})
        self.assertContains(response_search, "Abebe Kebede Wolde")
        self.assertNotContains(response_search, "Derartu Tulu Bekele")

        # 3. Grade/Class offering filter
        response_class = self.client.get(hub_url, {'class_offering': self.offering_11a.id})
        self.assertContains(response_class, "Derartu Tulu Bekele")
        self.assertNotContains(response_class, "Abebe Kebede Wolde")

    def test_missing_academic_records_handled_cleanly(self):
        """Verifies student without marks or calculated summary renders safely without errors."""
        self.client.force_login(self.admin_user)
        # Student 2 in Grade 11 has no marks entered yet
        url = reverse('student_report_card', args=[self.exam.id, self.student2.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No subject marks have been recorded")

        # PDF also builds cleanly
        response_pdf = self.client.get(url + "?format=pdf")
        self.assertEqual(response_pdf.status_code, 200)
        self.assertTrue(response_pdf.content.startswith(b'%PDF-'))

    def test_report_card_auto_print_mode(self):
        """Verifies report card print flag embeds print trigger script."""
        self.client.force_login(self.admin_user)
        url = reverse('student_report_card', args=[self.exam.id, self.student1.id]) + "?print=1"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "window.print()")
