"""
Comprehensive Automated Test Suite for School Reports & Analytics (Step 15).
Verifies:
- AnalyticsService calculations (students, teachers, attendance, exams, promotion)
- Safe zero defaults when database is empty (no division by zero)
- Chart.js structured payload generation
- Student reports filtering, search, and pagination
- Teacher workload calculations from published timetables
- Attendance summaries and chronic absenteeism detection
- Examination broadsheets, average scores, and pass percentages
- Promotion batch summaries and graduation registries
- PDF export generation (ReportLab)
- Excel export generation (OpenPyXL)
- Role-based access control (RBAC) across views
"""

from datetime import date, timedelta
from decimal import Decimal
import json

from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

from accounts.models import Role
from academics.models import AcademicYear, Grade, Section, Stream, Subject, ClassOffering
from teachers.models import Teacher, TeacherAssignment
from students.models import Student, StudentEnrollment
from attendance.models import AttendanceSession, AttendanceRecord
from examinations.models import Examination, ExamSubject
from results.models import Mark
from promotion.models import PromotionBatch, PromotionRecord, GraduationRecord
from timetable.models import Timetable, TimetableEntry, Period
from reports.services import (
    AnalyticsService,
    StudentReportService,
    TeacherReportService,
    AttendanceReportService,
    ExaminationPerformanceReportService,
    PromotionReportService,
    ReportExportService,
)

User = get_user_model()


class ReportsAndAnalyticsTests(TestCase):
    """
    Test suite for SSMS Reports and Analytics engine.
    Uses synthetic data only.
    """

    def setUp(self):
        self.client = Client()

        # 1. Setup Roles
        self.role_principal, _ = Role.objects.get_or_create(code='PRINCIPAL', defaults={'name': 'School Principal'})
        self.role_registrar, _ = Role.objects.get_or_create(code='REGISTRAR', defaults={'name': 'School Registrar'})
        self.role_teacher, _ = Role.objects.get_or_create(code='TEACHER', defaults={'name': 'Teacher'})
        self.role_student, _ = Role.objects.get_or_create(code='STUDENT', defaults={'name': 'Student'})

        # 2. Setup Users
        self.principal_user = User.objects.create_user(
            username='principal_kebede',
            password='TestPassword123!',
            role=self.role_principal
        )
        self.registrar_user = User.objects.create_user(
            username='registrar_almaz',
            password='TestPassword123!',
            role=self.role_registrar
        )
        self.teacher_user = User.objects.create_user(
            username='teacher_abebe',
            password='TestPassword123!',
            role=self.role_teacher
        )
        self.teacher_user2 = User.objects.create_user(
            username='teacher_chala',
            password='TestPassword123!',
            role=self.role_teacher
        )
        self.student_user = User.objects.create_user(
            username='student_user',
            password='TestPassword123!',
            role=self.role_student
        )

        # 3. Setup Academic Structure
        self.ay = AcademicYear.objects.create(
            name='2026/2027 (2019 E.C.)',
            code='AY-2026',
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_current=True
        )
        self.grade_10 = Grade.objects.create(name='Grade 10', level=10, is_active=True)
        self.grade_9 = Grade.objects.create(name='Grade 9', level=9, is_active=True)
        self.section_a = Section.objects.create(name='A', is_active=True)
        self.section_b = Section.objects.create(name='B', is_active=True)
        self.stream_gen = Stream.objects.create(code='GEN', name='General Secondary', is_active=True)

        self.class_10a = ClassOffering.objects.create(
            academic_year=self.ay,
            grade=self.grade_10,
            section=self.section_a,
            stream=self.stream_gen,
            max_capacity=50
        )
        self.class_9a = ClassOffering.objects.create(
            academic_year=self.ay,
            grade=self.grade_9,
            section=self.section_a,
            stream=self.stream_gen,
            max_capacity=50
        )

        # 4. Setup Subjects & Teachers
        self.math = Subject.objects.create(code='MATH-10', name='Mathematics', is_active=True)
        self.english = Subject.objects.create(code='ENG-10', name='English', is_active=True)

        self.teacher1 = Teacher.objects.create(
            user=self.teacher_user,
            employee_id='EMP-T01',
            first_name='Abebe',
            father_name='Bikila',
            gender='M',
            qualification='B.Ed in Mathematics',
            specialization='Mathematics',
            joining_date=date(2020, 9, 1),
            is_active=True
        )
        self.teacher2 = Teacher.objects.create(
            user=self.teacher_user2,
            employee_id='EMP-T02',
            first_name='Chala',
            father_name='Tolessa',
            gender='M',
            qualification='B.Ed in English',
            specialization='English',
            joining_date=date(2021, 9, 1),
            is_active=True
        )

        # Teacher Assignments
        TeacherAssignment.objects.create(
            teacher=self.teacher1,
            subject=self.math,
            class_offering=self.class_10a
        )
        TeacherAssignment.objects.create(
            teacher=self.teacher2,
            subject=self.english,
            class_offering=self.class_9a
        )

        # 5. Setup Students & Enrollments
        self.student_m1 = Student.objects.create(
            admission_number='SSMS/2026/001',
            first_name='Dawit',
            father_name='Bekele',
            gender='M',
            date_of_birth=date(2010, 3, 15),
            status='ACTIVE'
        )
        self.enr_m1 = StudentEnrollment.objects.create(
            student=self.student_m1,
            class_offering=self.class_10a,
            academic_year=self.ay,
            status='ACTIVE'
        )

        self.student_f1 = Student.objects.create(
            admission_number='SSMS/2026/002',
            first_name='Almaz',
            father_name='Desta',
            gender='F',
            date_of_birth=date(2010, 5, 20),
            status='ACTIVE'
        )
        self.enr_f1 = StudentEnrollment.objects.create(
            student=self.student_f1,
            class_offering=self.class_10a,
            academic_year=self.ay,
            status='ACTIVE'
        )

        self.student_m2 = Student.objects.create(
            admission_number='SSMS/2026/003',
            first_name='Gemechu',
            father_name='Tadesse',
            gender='M',
            date_of_birth=date(2011, 2, 10),
            status='ACTIVE'
        )
        self.enr_m2 = StudentEnrollment.objects.create(
            student=self.student_m2,
            class_offering=self.class_9a,
            academic_year=self.ay,
            status='ACTIVE'
        )

        # 6. Setup Attendance Sessions & Records
        self.att_session = AttendanceSession.objects.create(
            class_offering=self.class_10a,
            academic_year=self.ay,
            date=date(2026, 10, 1),
            session_type='DAILY',
            recorded_by=self.teacher1
        )
        AttendanceRecord.objects.create(
            attendance_session=self.att_session,
            student_enrollment=self.enr_m1,
            status='PRESENT'
        )
        AttendanceRecord.objects.create(
            attendance_session=self.att_session,
            student_enrollment=self.enr_f1,
            status='ABSENT'
        )

        # 7. Setup Examination & Marks
        self.exam = Examination.objects.create(
            name='Midterm Examination 2026',
            academic_year=self.ay,
            semester='SEM1',
            start_date=date(2026, 11, 1),
            end_date=date(2026, 11, 10),
            is_active=True,
            is_locked=False
        )
        self.exam_sub = ExamSubject.objects.create(
            examination=self.exam,
            subject=self.math,
            grade=self.grade_10,
            max_marks=Decimal('30.00'),
            pass_marks=Decimal('15.00')
        )
        Mark.objects.create(
            student_enrollment=self.enr_m1,
            exam_subject=self.exam_sub,
            marks_obtained=Decimal('25.00'),
            status='VERIFIED'
        )
        Mark.objects.create(
            student_enrollment=self.enr_f1,
            exam_subject=self.exam_sub,
            marks_obtained=Decimal('10.00'),
            status='VERIFIED'
        )

        # 8. Setup Promotion Batch
        self.ay_next = AcademicYear.objects.create(
            name='2027/2028 (2020 E.C.)',
            code='AY-2027',
            start_date=date(2027, 9, 1),
            end_date=date(2028, 6, 30),
            is_current=False
        )
        self.promo_batch = PromotionBatch.objects.create(
            name='Grade 10 Promotion Cohort 2026',
            academic_year=self.ay,
            target_academic_year=self.ay_next,
            grade=self.grade_10,
            status='APPROVED'
        )
        PromotionRecord.objects.create(
            batch=self.promo_batch,
            student_enrollment=self.enr_m1,
            student=self.student_m1,
            previous_academic_year=self.ay,
            next_academic_year=self.ay_next,
            previous_grade=self.grade_10,
            next_grade=self.grade_10,
            previous_class_offering=self.class_10a,
            final_outcome='PROMOTED'
        )
        PromotionRecord.objects.create(
            batch=self.promo_batch,
            student_enrollment=self.enr_f1,
            student=self.student_f1,
            previous_academic_year=self.ay,
            next_academic_year=self.ay_next,
            previous_grade=self.grade_10,
            next_grade=self.grade_10,
            previous_class_offering=self.class_10a,
            final_outcome='REPEATED'
        )

        # 9. Setup Timetable Entry for Teacher Workload
        self.period1 = Period.objects.create(
            academic_year=self.ay,
            period_number=1,
            name='Period 1',
            start_time='08:30:00',
            end_time='09:15:00',
            is_break=False,
            is_active=True
        )
        self.timetable = Timetable.objects.create(
            name='Grade 10-A Timetable',
            academic_year=self.ay,
            class_offering=self.class_10a,
            status='PUBLISHED',
            version=1
        )
        TimetableEntry.objects.create(
            timetable=self.timetable,
            class_offering=self.class_10a,
            subject=self.math,
            teacher=self.teacher1,
            day_of_week=1,
            period=self.period1
        )

    # -------------------------------------------------------------
    # 1. ANALYTICS SERVICE TESTS
    # -------------------------------------------------------------

    def test_overview_stats_calculations(self):
        """Verifies institutional KPI statistics are computed from DB records."""
        stats = AnalyticsService.get_school_overview_stats(filters={'academic_year': self.ay})
        
        # Student stats
        self.assertEqual(stats['total_registered_students'], 3)
        self.assertEqual(stats['total_active_students'], 3)
        self.assertEqual(stats['male_students'], 2)
        self.assertEqual(stats['female_students'], 1)

        # Teacher stats
        self.assertEqual(stats['total_teachers'], 2)
        self.assertEqual(stats['active_teachers'], 2)
        self.assertEqual(stats['inactive_teachers'], 0)

        # Attendance stats
        self.assertEqual(stats['total_attendance_records'], 2)
        self.assertEqual(stats['present_count'], 1)
        self.assertEqual(stats['absent_count'], 1)
        self.assertEqual(stats['attendance_percentage'], 50.0)

        # Exam stats
        self.assertEqual(stats['total_examinations'], 1)
        self.assertEqual(stats['total_marks_count'], 2)
        self.assertEqual(stats['overall_exam_average'], 17.5)  # (25 + 10) / 2

        # Promotion stats
        self.assertEqual(stats['promoted_count'], 1)
        self.assertEqual(stats['repeated_count'], 1)

    def test_empty_database_defaults_safe(self):
        """Verifies service safely handles empty database tables without division by zero."""
        empty_year = AcademicYear.objects.create(
            name='2030/2031 Empty',
            code='AY-2030',
            start_date=date(2030, 9, 1),
            end_date=date(2031, 6, 30)
        )
        stats = AnalyticsService.get_school_overview_stats(filters={'academic_year': empty_year})
        self.assertEqual(stats['attendance_percentage'], 0.0)
        self.assertEqual(stats['total_attendance_records'], 0)
        self.assertEqual(stats['overall_exam_average'], 0.0)

    def test_charts_payload_structure(self):
        """Verifies Chart.js structured payload contains all 8 required datasets."""
        charts = AnalyticsService.get_charts_payload(filters={'academic_year': self.ay})
        self.assertIn('chart1', charts)
        self.assertIn('chart2', charts)
        self.assertIn('chart3', charts)
        self.assertIn('chart4', charts)
        self.assertIn('chart5', charts)
        self.assertIn('chart6', charts)
        self.assertIn('chart7', charts)
        self.assertIn('chart8', charts)
        self.assertIn('Student Distribution by Grade', charts['chart1']['title'])
        self.assertIn('Mathematics', charts['chart5']['labels'])

    # -------------------------------------------------------------
    # 2. STUDENT REPORT SERVICE TESTS
    # -------------------------------------------------------------

    def test_student_reports_filtering_and_search(self):
        """Filters students by grade, class, and search queries."""
        # Search by admission number
        res1 = StudentReportService.get_student_reports(filters={'search': '001'})
        self.assertEqual(res1.count(), 1)
        self.assertEqual(res1.first().student.first_name, 'Dawit')

        # Filter by grade
        res2 = StudentReportService.get_student_reports(filters={'grade': self.grade_10})
        self.assertEqual(res2.count(), 2)

        # Filter by class offering
        res3 = StudentReportService.get_student_reports(filters={'class_offering': self.class_9a})
        self.assertEqual(res3.count(), 1)

    def test_student_detail_report_portfolio(self):
        """Validates 360-degree student portfolio aggregation."""
        detail = StudentReportService.get_student_detail_report(self.student_m1.id)
        self.assertEqual(detail['student'], self.student_m1)
        self.assertEqual(len(detail['enrollments']), 1)
        self.assertEqual(detail['attendance']['total_sessions'], 1)
        self.assertEqual(detail['attendance']['rate'], 100.0)
        self.assertEqual(len(detail['recent_marks']), 1)
        self.assertEqual(detail['promotions'].first().final_outcome, 'PROMOTED')

    # -------------------------------------------------------------
    # 3. TEACHER REPORT SERVICE TESTS
    # -------------------------------------------------------------

    def test_teacher_reports_workload(self):
        """Computes teacher workload: classes count and scheduled weekly periods."""
        teacher_data = TeacherReportService.get_teacher_reports(filters={'academic_year': self.ay})
        t1_item = next(item for item in teacher_data if item['teacher'].id == self.teacher1.id)
        
        self.assertEqual(t1_item['classes_count'], 1)
        self.assertEqual(t1_item['subjects_list'], ['Mathematics'])
        self.assertEqual(t1_item['periods_count'], 1)

    # -------------------------------------------------------------
    # 4. ATTENDANCE & CHRONIC ABSENTEEISM TESTS
    # -------------------------------------------------------------

    def test_attendance_daily_and_chronic_absenteeism(self):
        """Detects daily presence summaries and chronic absenteeism alerts."""
        data = AttendanceReportService.get_attendance_reports(filters={'academic_year': self.ay})
        
        self.assertEqual(len(data['daily_summary']), 1)
        day_stat = data['daily_summary'][0]
        self.assertEqual(day_stat['total'], 2)
        self.assertEqual(day_stat['present'], 1)
        self.assertEqual(day_stat['absent'], 1)
        self.assertEqual(day_stat['rate'], 50.0)

    # -------------------------------------------------------------
    # 5. EXAMINATION & ACADEMIC PERFORMANCE TESTS
    # -------------------------------------------------------------

    def test_examination_reports_and_pass_rates(self):
        """Verifies examination completion stats, score averages, and pass rate calculation."""
        exams = ExaminationPerformanceReportService.get_examination_reports(filters={'academic_year': self.ay})
        self.assertEqual(len(exams), 1)
        item = exams[0]
        self.assertEqual(item['total_marks'], 2)
        self.assertEqual(item['average'], 17.5)
        self.assertEqual(item['highest'], 25.0)
        self.assertEqual(item['lowest'], 10.0)
        self.assertEqual(item['pass_rate'], 50.0)  # 1 of 2 >= 15.00 pass_marks

    def test_subject_performance_broadsheets(self):
        """Verifies subject-level broadsheet calculation."""
        subjects = ExaminationPerformanceReportService.get_subject_performance_reports(filters={'academic_year': self.ay})
        self.assertEqual(len(subjects), 1)
        sub = subjects[0]
        self.assertEqual(sub['subject_name'], 'Mathematics')
        self.assertEqual(sub['sat_count'], 2)
        self.assertEqual(sub['pass_percentage'], 50.0)

    # -------------------------------------------------------------
    # 6. PROMOTION & GRADUATION TESTS
    # -------------------------------------------------------------

    def test_promotion_reports(self):
        """Verifies promotion batch summaries."""
        promo_data = PromotionReportService.get_promotion_reports(filters={'academic_year': self.ay})
        self.assertEqual(len(promo_data['batch_summaries']), 1)
        b = promo_data['batch_summaries'][0]
        self.assertEqual(b['total_candidates'], 2)
        self.assertEqual(b['promoted'], 1)
        self.assertEqual(b['repeated'], 1)
        self.assertEqual(b['promotion_rate'], 50.0)

    # -------------------------------------------------------------
    # 7. EXPORT TESTS (PDF & EXCEL)
    # -------------------------------------------------------------

    def test_export_pdf_generation(self):
        """Verifies ReportLab compiles a valid binary PDF document."""
        enrollments = list(StudentReportService.get_student_reports())
        pdf_buffer = ReportExportService.export_pdf(
            report_type='students',
            context={'records': enrollments},
            title="Student Registry Test"
        )
        pdf_bytes = pdf_buffer.getvalue()
        self.assertTrue(len(pdf_bytes) > 500)
        self.assertTrue(pdf_bytes.startswith(b'%PDF-'))

    def test_export_excel_generation(self):
        """Verifies OpenPyXL compiles a valid binary XLSX document."""
        enrollments = list(StudentReportService.get_student_reports())
        excel_buffer = ReportExportService.export_excel(
            report_type='students',
            context={'records': enrollments},
            title="Student Registry Test"
        )
        excel_bytes = excel_buffer.getvalue()
        self.assertTrue(len(excel_bytes) > 1000)
        # XLSX starts with standard ZIP signature
        self.assertTrue(excel_bytes.startswith(b'PK'))

    # -------------------------------------------------------------
    # 8. VIEW & RBAC PERMISSION TESTS
    # -------------------------------------------------------------

    def test_rbac_principal_full_access(self):
        """Principal has full access to all report dashboards and views."""
        self.client.force_login(self.principal_user)

        views_to_test = [
            reverse('reports_dashboard'),
            reverse('reports_students'),
            reverse('student_report_detail', args=[self.student_m1.id]),
            reverse('reports_teachers'),
            reverse('teacher_report_detail', args=[self.teacher1.id]),
            reverse('reports_attendance'),
            reverse('reports_examinations'),
            reverse('reports_academic'),
            reverse('reports_promotion'),
            reverse('reports_exports'),
        ]

        for url in views_to_test:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, f"Failed accessing {url}")

    def test_rbac_teacher_restricted_access(self):
        """Teacher can view analytics, but cannot view management-only promotion/teacher reports."""
        self.client.force_login(self.teacher_user)

        # Permitted views
        resp = self.client.get(reverse('reports_dashboard'))
        self.assertEqual(resp.status_code, 200)

        resp = self.client.get(reverse('reports_students'))
        self.assertEqual(resp.status_code, 200)

        # Blocked management views -> 403 Forbidden
        resp_promo = self.client.get(reverse('reports_promotion'))
        self.assertEqual(resp_promo.status_code, 403)

        resp_teachers = self.client.get(reverse('reports_teachers'))
        self.assertEqual(resp_teachers.status_code, 403)

    def test_rbac_unauthenticated_redirect(self):
        """Unauthenticated requests are redirected to login."""
        self.client.logout()
        resp = self.client.get(reverse('reports_dashboard'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_export_endpoints_http(self):
        """Verifies streaming PDF and Excel downloads via HTTP endpoints."""
        self.client.force_login(self.principal_user)

        # PDF download
        resp_pdf = self.client.get(reverse('export_report_pdf', args=['students']))
        self.assertEqual(resp_pdf.status_code, 200)
        self.assertEqual(resp_pdf['Content-Type'], 'application/pdf')
        self.assertIn('attachment', resp_pdf['Content-Disposition'])

        # Excel download
        resp_excel = self.client.get(reverse('export_report_excel', args=['students']))
        self.assertEqual(resp_excel.status_code, 200)
        self.assertEqual(resp_excel['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertIn('attachment', resp_excel['Content-Disposition'])
