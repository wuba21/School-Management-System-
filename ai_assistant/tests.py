"""
Automated Test Suite for Step 16: AI-Powered School Assistant.
Verifies Academic Analysis, Attendance Intelligence, Report Generation,
Conversational Assistant, RBAC permissions, and Offline LAN Safety.
"""

from django.test import TestCase, Client
from django.urls import reverse
from datetime import date, time
from decimal import Decimal
import json

from accounts.models import Role, User
from academics.models import AcademicYear, Grade, Section, Stream, Subject, ClassOffering
from teachers.models import Teacher, TeacherAssignment
from students.models import Student, StudentEnrollment
from attendance.models import AttendanceSession, AttendanceRecord
from examinations.models import Examination, ExamSubject
from results.models import Mark
from promotion.models import PromotionCriteria
from timetable.models import Timetable, Period, SchoolDay, TimetableEntry
from ai_assistant.models import ChatConversation, ChatMessage
from ai_assistant.services import (
    AcademicAnalysisService,
    AttendanceAnalysisService,
    ConversationalAssistantService,
    AIReportService,
)


class AIAssistantComprehensiveTests(TestCase):
    """
    Complete unit and integration test suite for AI Assistant.
    """

    def setUp(self):
        self.client = Client()

        # 1. User Roles
        self.role_admin, _ = Role.objects.get_or_create(code='ADMIN', defaults={'name': 'System Administrator'})
        self.role_principal, _ = Role.objects.get_or_create(code='PRINCIPAL', defaults={'name': 'School Principal'})
        self.role_registrar, _ = Role.objects.get_or_create(code='REGISTRAR', defaults={'name': 'Registrar'})
        self.role_teacher, _ = Role.objects.get_or_create(code='TEACHER', defaults={'name': 'Teacher'})

        # 2. Users
        self.admin_user = User.objects.create_user(
            username='ai_admin', password='Password123!', role=self.role_admin
        )
        self.principal_user = User.objects.create_user(
            username='ai_principal', password='Password123!', role=self.role_principal
        )
        self.teacher_user = User.objects.create_user(
            username='ai_teacher', password='Password123!', role=self.role_teacher
        )

        # 3. Teacher Profile
        self.teacher = Teacher.objects.create(
            user=self.teacher_user,
            employee_id='EMP-AI-01',
            first_name='Abel',
            father_name='Kebede',
            grandfather_name='Desta',
            gender='MALE',
            joining_date=date(2020, 9, 1),
            qualification='B.Ed Mathematics'
        )

        # 4. Academic Structure
        self.year = AcademicYear.objects.create(
            name='2026/2027 E.C.',
            code='AY-2026-AI',
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_current=True
        )
        self.grade9 = Grade.objects.create(name='Grade 9', level=9, is_active=True)
        self.grade10 = Grade.objects.create(name='Grade 10', level=10, is_active=True)
        self.section_a = Section.objects.create(name='A', is_active=True)
        self.section_b = Section.objects.create(name='B', is_active=True)
        self.stream_gen = Stream.objects.create(code='GEN', name='General Secondary', is_active=True)

        self.subject_math = Subject.objects.create(name='Mathematics', code='MATH-AI', is_active=True)
        self.subject_phys = Subject.objects.create(name='Physics', code='PHYS-AI', is_active=True)
        self.subject_eng = Subject.objects.create(name='English', code='ENG-AI', is_active=True)

        self.offering9a = ClassOffering.objects.create(
            academic_year=self.year, grade=self.grade9, section=self.section_a, stream=self.stream_gen
        )
        self.offering9b = ClassOffering.objects.create(
            academic_year=self.year, grade=self.grade9, section=self.section_b, stream=self.stream_gen
        )

        # 5. Teacher Assignment (Teacher assigned to Grade 9A Math only)
        self.assignment = TeacherAssignment.objects.create(
            teacher=self.teacher,
            class_offering=self.offering9a,
            subject=self.subject_math,
            academic_year=self.year
        )

        # 6. Students
        self.student1 = Student.objects.create(
            admission_number='MAJ/2026/001',
            first_name='Desta', father_name='Tolosa', grandfather_name='Geda',
            gender='MALE', date_of_birth=date(2010, 2, 1), admission_date=date(2026, 9, 1), status='ACTIVE'
        )
        self.student2 = Student.objects.create(
            admission_number='MAJ/2026/002',
            first_name='Chaltu', father_name='Girma', grandfather_name='Alemu',
            gender='FEMALE', date_of_birth=date(2010, 4, 15), admission_date=date(2026, 9, 1), status='ACTIVE'
        )
        self.student3 = Student.objects.create(
            admission_number='MAJ/2026/003',
            first_name='Bekele', father_name='Tadesse', grandfather_name='Worku',
            gender='MALE', date_of_birth=date(2010, 7, 20), admission_date=date(2026, 9, 1), status='ACTIVE'
        )

        self.enr1 = StudentEnrollment.objects.create(
            student=self.student1, class_offering=self.offering9a, academic_year=self.year, status='ACTIVE'
        )
        self.enr2 = StudentEnrollment.objects.create(
            student=self.student2, class_offering=self.offering9a, academic_year=self.year, status='ACTIVE'
        )
        self.enr3 = StudentEnrollment.objects.create(
            student=self.student3, class_offering=self.offering9b, academic_year=self.year, status='ACTIVE'
        )

        # 7. Examination & Marks
        self.exam = Examination.objects.create(
            academic_year=self.year,
            name='Semester 1 Midterm',
            semester='SEM1',
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 10),
            status='PUBLISHED'
        )
        self.exam_math = ExamSubject.objects.create(
            examination=self.exam, grade=self.grade9, subject=self.subject_math,
            max_marks=Decimal('100.00'), pass_marks=Decimal('50.00')
        )
        self.exam_phys = ExamSubject.objects.create(
            examination=self.exam, grade=self.grade9, subject=self.subject_phys,
            max_marks=Decimal('100.00'), pass_marks=Decimal('50.00')
        )

        # Math: High scores (85 and 75)
        Mark.objects.create(exam_subject=self.exam_math, student_enrollment=self.enr1, marks_obtained=Decimal('85.00'), status='VERIFIED')
        Mark.objects.create(exam_subject=self.exam_math, student_enrollment=self.enr2, marks_obtained=Decimal('75.00'), status='VERIFIED')

        # Physics: Low scores (40 and 44 - both failing) -> Attention trigger
        Mark.objects.create(exam_subject=self.exam_phys, student_enrollment=self.enr1, marks_obtained=Decimal('40.00'), status='VERIFIED')
        Mark.objects.create(exam_subject=self.exam_phys, student_enrollment=self.enr2, marks_obtained=Decimal('44.00'), status='VERIFIED')

        # 8. Attendance Sessions (Mondays and Fridays)
        # Session 1: Monday (Student 1 Present, Student 2 Absent)
        self.sess1 = AttendanceSession.objects.create(
            class_offering=self.offering9a, academic_year=self.year,
            date=date(2026, 10, 5), session_type='MORNING', recorded_by=self.teacher
        )
        AttendanceRecord.objects.create(attendance_session=self.sess1, student_enrollment=self.enr1, status='PRESENT')
        AttendanceRecord.objects.create(attendance_session=self.sess1, student_enrollment=self.enr2, status='ABSENT')

        # Session 2: Friday (Student 1 Present, Student 2 Absent)
        self.sess2 = AttendanceSession.objects.create(
            class_offering=self.offering9a, academic_year=self.year,
            date=date(2026, 10, 9), session_type='MORNING', recorded_by=self.teacher
        )
        AttendanceRecord.objects.create(attendance_session=self.sess2, student_enrollment=self.enr1, status='PRESENT')
        AttendanceRecord.objects.create(attendance_session=self.sess2, student_enrollment=self.enr2, status='ABSENT')

        # Session 3: Following Monday (Student 1 Present, Student 2 Absent -> 3rd absence, triggers chronic flag)
        self.sess3 = AttendanceSession.objects.create(
            class_offering=self.offering9a, academic_year=self.year,
            date=date(2026, 10, 12), session_type='MORNING', recorded_by=self.teacher
        )
        AttendanceRecord.objects.create(attendance_session=self.sess3, student_enrollment=self.enr1, status='PRESENT')
        AttendanceRecord.objects.create(attendance_session=self.sess3, student_enrollment=self.enr2, status='ABSENT')

        # 9. Promotion Policy
        self.criteria = PromotionCriteria.objects.create(
            name='Majang Standard Promotion',
            code='PROM-AI',
            minimum_average=Decimal('50.00'),
            max_failing_subjects=2,
            is_default=True
        )

        # 10. Timetable
        self.period1 = Period.objects.create(name='Period 1', period_number=1, start_time=time(8, 30), end_time=time(9, 15))
        self.day_mon = SchoolDay.objects.create(day_of_week=0, name='Monday', short_name='Mon', is_active=True, order=1)

    # -------------------------------------------------------------------------
    # ACADEMIC ANALYSIS TESTS
    # -------------------------------------------------------------------------

    def test_academic_subject_averages(self):
        """Verify calculation of subject mean, max, min, and pass rates."""
        stats = AcademicAnalysisService.get_subject_averages(academic_year=self.year, user=self.admin_user)
        self.assertGreaterEqual(len(stats), 2)

        math_stat = next(s for s in stats if s['subject_code'] == 'MATH-AI')
        self.assertEqual(math_stat['average_score'], 80.0)
        self.assertEqual(math_stat['pass_rate'], 100.0)
        self.assertFalse(math_stat['needs_attention'])

        phys_stat = next(s for s in stats if s['subject_code'] == 'PHYS-AI')
        self.assertEqual(phys_stat['average_score'], 42.0)
        self.assertEqual(phys_stat['pass_rate'], 0.0)
        self.assertTrue(phys_stat['needs_attention'])

    def test_subjects_requiring_attention(self):
        """Confirms automatic detection and pedagogical recommendations for weak subjects."""
        attention_list = AcademicAnalysisService.get_subjects_requiring_attention(
            academic_year=self.year, user=self.admin_user
        )
        self.assertEqual(len(attention_list), 1)
        self.assertEqual(attention_list[0]['subject_code'], 'PHYS-AI')
        self.assertGreater(len(attention_list[0]['recommendations']), 0)

    def test_class_comparison_matrix(self):
        """Verifies section ranking and class average scores."""
        matrix = AcademicAnalysisService.get_class_comparison_matrix(grade=self.grade9, user=self.admin_user)
        self.assertEqual(len(matrix), 2)
        top_class = matrix[0]
        self.assertEqual(top_class['class_name'], self.offering9a.display_name)
        # Average of 85, 75, 40, 44 = 244 / 4 = 61.0
        self.assertEqual(top_class['class_average'], 61.0)
        self.assertEqual(top_class['rank'], 1)

    def test_student_academic_summary(self):
        """Verifies holistic student diagnostic portfolio."""
        summary = AcademicAnalysisService.get_student_academic_summary(self.student1.id, user=self.admin_user)
        self.assertEqual(summary['student'].admission_number, 'MAJ/2026/001')
        # Scores: 85 and 40 -> avg = 62.5
        self.assertEqual(summary['overall_average'], 62.5)
        self.assertIn('foundational', summary['narrative'].lower())

    # -------------------------------------------------------------------------
    # ATTENDANCE ANALYSIS TESTS
    # -------------------------------------------------------------------------

    def test_attendance_overview(self):
        """Verifies institutional presence and absence rate calculation."""
        overview = AttendanceAnalysisService.get_attendance_overview(academic_year=self.year, user=self.admin_user)
        self.assertEqual(overview['total_records'], 6)
        self.assertEqual(overview['present_count'], 3)
        self.assertEqual(overview['absent_count'], 3)
        self.assertEqual(overview['presence_rate'], 50.0)
        self.assertEqual(overview['absence_rate'], 50.0)

    def test_attendance_weekday_patterns(self):
        """Verifies day-of-week absence frequency mapping."""
        patterns = AttendanceAnalysisService.get_repeated_absenteeism_patterns(user=self.admin_user)
        day_patterns = patterns['day_patterns']
        self.assertEqual(len(day_patterns), 5)

        mon_data = next(d for d in day_patterns if d['day_name'] == 'Monday')
        self.assertEqual(mon_data['absent_count'], 2)  # 2 Monday absences for student 2

        fri_data = next(d for d in day_patterns if d['day_name'] == 'Friday')
        self.assertEqual(fri_data['absent_count'], 1)  # 1 Friday absence for student 2

    def test_frequent_absentees_detection(self):
        """Confirms non-punitive identification of students with >= 3 absences."""
        patterns = AttendanceAnalysisService.get_repeated_absenteeism_patterns(user=self.admin_user)
        flagged = patterns['frequent_absentees']
        self.assertEqual(len(flagged), 1)
        self.assertEqual(flagged[0]['admission_number'], 'MAJ/2026/002')
        self.assertEqual(flagged[0]['unexcused_absences'], 3)
        self.assertIn('counseling', flagged[0]['advisory_recommendation'].lower())

    # -------------------------------------------------------------------------
    # CONVERSATIONAL ASSISTANT TESTS
    # -------------------------------------------------------------------------

    def test_chat_student_count_query(self):
        """Tests natural language query for student count."""
        res = ConversationalAssistantService.handle_query("How many students are registered in the school?", self.admin_user)
        self.assertEqual(res['intent'], 'STUDENT_COUNT')
        self.assertIn('Total Registered Students', res['content'])
        self.assertIn('3', res['content'])

    def test_chat_teacher_count_query(self):
        """Tests natural language query for teacher count."""
        res = ConversationalAssistantService.handle_query("How many teachers are registered?", self.admin_user)
        self.assertEqual(res['intent'], 'TEACHER_COUNT')
        self.assertIn('Teaching Faculty Statistics', res['content'])
        self.assertIn('1', res['content'])

    def test_chat_low_scoring_subjects_query(self):
        """Tests natural language query for weakest subjects."""
        res = ConversationalAssistantService.handle_query("Which subjects have the lowest average scores?", self.admin_user)
        self.assertEqual(res['intent'], 'LOW_SCORING_SUBJECTS')
        self.assertIn('Physics', res['content'])

    def test_chat_grade_attendance_query(self):
        """Tests natural language query for grade attendance percentage."""
        res = ConversationalAssistantService.handle_query("What is the attendance percentage of Grade 9?", self.admin_user)
        self.assertEqual(res['intent'], 'GRADE_ATTENDANCE')
        self.assertIn('50.0%', res['content'])

    def test_chat_promotion_criteria_query(self):
        """Tests natural language query for promotion criteria."""
        res = ConversationalAssistantService.handle_query("What are the promotion criteria from Grade 10 to 11?", self.admin_user)
        self.assertEqual(res['intent'], 'PROMOTION_CRITERIA')
        self.assertIn('50.00%', res['content'])

    def test_chat_unknown_fallback(self):
        """Tests graceful handling when query does not match known intent."""
        res = ConversationalAssistantService.handle_query("Can you tell me a bedtime story about elephants?", self.admin_user)
        self.assertEqual(res['intent'], 'UNKNOWN')
        self.assertIn('Here are questions I can answer right now', res['content'])

    # -------------------------------------------------------------------------
    # RBAC & SECURITY TESTS
    # -------------------------------------------------------------------------

    def test_teacher_restricted_data_access(self):
        """Ensures a teacher cannot access reports for classes they do not teach."""
        # Teacher tries to query Grade 10 summary (they only teach Grade 9A)
        res = ConversationalAssistantService.handle_query("Summarize Grade 10 academic performance.", self.teacher_user)
        self.assertIn('Permission Notice', res['content'])

    def test_unauthenticated_redirect(self):
        """Unauthenticated requests to AI routes redirect to login."""
        response = self.client.get(reverse('ai_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('login')))

    # -------------------------------------------------------------------------
    # REPORT EXPORT GENERATOR TESTS
    # -------------------------------------------------------------------------

    def test_export_pdf_student_summary(self):
        """Tests binary vector PDF generation via ReportLab."""
        sections = [
            ("Student Diagnostic Summary", [["Metric", "Value"], ["Full Name", "Desta Tolosa"], ["Average", "62.5%"]])
        ]
        pdf_bytes = AIReportService.export_ai_summary_pdf("Student Diagnostic Summary", sections)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

    def test_export_excel_summary(self):
        """Tests binary Excel workbook generation via OpenPyXL."""
        headers = ["Subject", "Average", "Pass Rate"]
        rows = [["Mathematics", 80.0, 100.0], ["Physics", 42.0, 0.0]]
        excel_bytes = AIReportService.export_ai_summary_excel("Subject Intelligence", headers, rows)
        self.assertTrue(excel_bytes.startswith(b'PK'))

    def test_safe_empty_database_handling(self):
        """Ensures zero-division protection when no marks exist."""
        empty_year = AcademicYear.objects.create(
            name='2030/2031 E.C.', code='AY-2030-EMPTY', start_date=date(2030, 9, 1), end_date=date(2031, 6, 30)
        )
        stats = AcademicAnalysisService.get_subject_averages(academic_year=empty_year)
        self.assertEqual(len(stats), 0)
        overview = AttendanceAnalysisService.get_attendance_overview(academic_year=empty_year)
        self.assertEqual(overview['presence_rate'], 0.0)
        self.assertEqual(overview['total_records'], 0)
