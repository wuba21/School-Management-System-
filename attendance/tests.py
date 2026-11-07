"""
Test Suite for Attendance Management System (Step 11).
"""

from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import ValidationError

from accounts.models import User, Role
from academics.models import AcademicYear, Grade, Section, Stream, Subject, ClassOffering
from students.models import Student, StudentEnrollment
from teachers.models import Teacher, TeacherAssignment
from attendance.models import AttendanceSession, AttendanceRecord
from attendance.services import (
    AttendanceSessionService,
    AttendanceRecordService,
    AttendanceAnalyticsService,
    AttendanceExportService,
)


class AttendanceManagementTests(TestCase):

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
        self.user_teacher_1 = User.objects.create_user(
            username='teacher_1', password='Password123!', role=self.role_teacher
        )
        self.user_teacher_2 = User.objects.create_user(
            username='teacher_2', password='Password123!', role=self.role_teacher
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
        self.sec_a = Section.objects.create(name="A", is_active=True)
        self.sec_b = Section.objects.create(name="B", is_active=True)

        self.subj_math = Subject.objects.create(name="Mathematics", code="MATH101", is_active=True)
        self.subj_phy = Subject.objects.create(name="Physics", code="PHY101", is_active=True)

        # Class Offerings
        self.offering_9a = ClassOffering.objects.create(
            academic_year=self.ay_2026, grade=self.grade_9, section=self.sec_a, max_capacity=50
        )
        self.offering_10a = ClassOffering.objects.create(
            academic_year=self.ay_2026, grade=self.grade_10, section=self.sec_a, max_capacity=50
        )
        self.offering_old = ClassOffering.objects.create(
            academic_year=self.ay_2025, grade=self.grade_9, section=self.sec_a, max_capacity=50
        )

        # Teachers
        self.teacher_1 = Teacher.objects.create(
            user=self.user_teacher_1,
            employee_id="T-001",
            first_name="Abebe",
            father_name="Bikila",
            gender="M",
            employment_status="ACTIVE",
            specialization="Mathematics",
            joining_date=date(2020, 9, 1)
        )
        self.teacher_2 = Teacher.objects.create(
            user=self.user_teacher_2,
            employee_id="T-002",
            first_name="Tola",
            father_name="Gemechu",
            gender="M",
            employment_status="ACTIVE",
            specialization="Physics",
            joining_date=date(2021, 9, 1)
        )

        # Teacher Assignments: Teacher 1 -> 9A (Math); Teacher 2 -> 10A (Physics)
        TeacherAssignment.objects.create(
            teacher=self.teacher_1,
            class_offering=self.offering_9a,
            subject=self.subj_math,
            academic_year=self.ay_2026
        )
        TeacherAssignment.objects.create(
            teacher=self.teacher_2,
            class_offering=self.offering_10a,
            subject=self.subj_phy,
            academic_year=self.ay_2026
        )

        # Students (Grades 9 & 10)
        self.student_1 = Student.objects.create(
            admission_number="ST-2026-001",
            first_name="Chaltu",
            father_name="Tolessa",
            grandfather_name="Desta",
            gender="F",
            date_of_birth=date(2010, 3, 15),
            emergency_contact_name="Tolessa Desta",
            emergency_contact_phone="0911000001",
            emergency_contact_relation="Father",
            status="ACTIVE"
        )
        self.student_2 = Student.objects.create(
            admission_number="ST-2026-002",
            first_name="Amanuel",
            father_name="Kebede",
            grandfather_name="Wakgari",
            gender="M",
            date_of_birth=date(2010, 6, 20),
            emergency_contact_name="Kebede Wakgari",
            emergency_contact_phone="0911000002",
            emergency_contact_relation="Father",
            status="ACTIVE"
        )
        self.student_3 = Student.objects.create(
            admission_number="ST-2026-003",
            first_name="Derartu",
            father_name="Tulu",
            grandfather_name="Itefa",
            gender="F",
            date_of_birth=date(2010, 8, 10),
            emergency_contact_name="Tulu Itefa",
            emergency_contact_phone="0911000003",
            emergency_contact_relation="Father",
            status="ACTIVE"
        )

        # Enrollments: ST-001 & ST-002 -> 9A; ST-003 -> 10A
        self.enr_1 = StudentEnrollment.objects.create(
            student=self.student_1,
            class_offering=self.offering_9a,
            academic_year=self.ay_2026,
            status="ACTIVE"
        )
        self.enr_2 = StudentEnrollment.objects.create(
            student=self.student_2,
            class_offering=self.offering_9a,
            academic_year=self.ay_2026,
            status="ACTIVE"
        )
        self.enr_3 = StudentEnrollment.objects.create(
            student=self.student_3,
            class_offering=self.offering_10a,
            academic_year=self.ay_2026,
            status="ACTIVE"
        )

    # -------------------------------------------------------------------------
    # 1. Attendance Session Creation & Validation
    # -------------------------------------------------------------------------

    def test_attendance_session_creation_success(self):
        """Attendance session creates successfully and auto-associates academic year."""
        session = AttendanceSessionService.create_session(
            class_offering=self.offering_9a,
            session_date=date(2026, 10, 1),
            session_type='DAILY',
            recorded_by=self.teacher_1,
            created_by=self.user_teacher_1
        )
        self.assertEqual(session.class_offering, self.offering_9a)
        self.assertEqual(session.academic_year, self.ay_2026)
        self.assertEqual(session.status, 'OPEN')
        self.assertTrue(session.is_editable)

    def test_attendance_session_duplicate_rejected(self):
        """Duplicate session on same date and session type is rejected."""
        AttendanceSessionService.create_session(
            class_offering=self.offering_9a,
            session_date=date(2026, 10, 2),
            session_type='DAILY',
            recorded_by=self.teacher_1,
            created_by=self.user_teacher_1
        )
        with self.assertRaises(ValidationError):
            AttendanceSessionService.create_session(
                class_offering=self.offering_9a,
                session_date=date(2026, 10, 2),
                session_type='DAILY',
                recorded_by=self.teacher_1,
                created_by=self.user_teacher_1
            )

    def test_attendance_session_in_closed_year_rejected(self):
        """Creating an attendance session in a closed academic year raises ValidationError."""
        with self.assertRaises(ValidationError):
            AttendanceSessionService.create_session(
                class_offering=self.offering_old,
                session_date=date(2025, 10, 1),
                session_type='DAILY',
                recorded_by=self.teacher_1,
                created_by=self.user_teacher_1
            )

    # -------------------------------------------------------------------------
    # 2. Roll-Call Recording & Duplicate Marks Prevention
    # -------------------------------------------------------------------------

    def test_bulk_attendance_recording(self):
        """Teacher records roll call marks for enrolled students."""
        session = AttendanceSessionService.create_session(
            class_offering=self.offering_9a,
            session_date=date(2026, 10, 5),
            session_type='DAILY',
            recorded_by=self.teacher_1,
            created_by=self.user_teacher_1
        )

        records_data = [
            {'enrollment_id': self.enr_1.id, 'status': 'PRESENT', 'reason': ''},
            {'enrollment_id': self.enr_2.id, 'status': 'ABSENT', 'reason': 'Family emergency'},
        ]
        result = AttendanceRecordService.record_bulk_attendance(
            session=session,
            records_data=records_data,
            recorded_by_user=self.user_teacher_1
        )

        self.assertEqual(result['created'], 2)
        session.refresh_from_db()
        self.assertEqual(session.status, 'SUBMITTED')
        self.assertEqual(session.present_count, 1)
        self.assertEqual(session.absent_count, 1)
        self.assertEqual(session.attendance_percentage, 50.0)

    def test_duplicate_student_record_in_session_updates_existing(self):
        """Submitting attendance again updates existing records rather than duplicating."""
        session = AttendanceSessionService.create_session(
            class_offering=self.offering_9a,
            session_date=date(2026, 10, 6),
            session_type='DAILY',
            recorded_by=self.teacher_1,
            created_by=self.user_teacher_1
        )

        # First pass: ST-001 is ABSENT
        AttendanceRecordService.record_bulk_attendance(
            session=session,
            records_data=[{'enrollment_id': self.enr_1.id, 'status': 'ABSENT', 'reason': ''}]
        )
        self.assertEqual(AttendanceRecord.objects.filter(attendance_session=session).count(), 1)
        self.assertEqual(AttendanceRecord.objects.get(attendance_session=session, student_enrollment=self.enr_1).status, 'ABSENT')

        # Second pass (correction): ST-001 arrived LATE
        AttendanceRecordService.record_bulk_attendance(
            session=session,
            records_data=[{'enrollment_id': self.enr_1.id, 'status': 'LATE', 'reason': 'Bus delay'}]
        )
        # Count must remain 1
        self.assertEqual(AttendanceRecord.objects.filter(attendance_session=session).count(), 1)
        record = AttendanceRecord.objects.get(attendance_session=session, student_enrollment=self.enr_1)
        self.assertEqual(record.status, 'LATE')
        self.assertEqual(record.reason, 'Bus delay')

    def test_student_from_different_class_ignored_or_rejected(self):
        """Student enrolled in 10A cannot be marked in a 9A attendance session."""
        session = AttendanceSessionService.create_session(
            class_offering=self.offering_9a,
            session_date=date(2026, 10, 7),
            session_type='DAILY',
            recorded_by=self.teacher_1,
            created_by=self.user_teacher_1
        )
        # Attempting to record direct model instance raises ValidationError
        rec = AttendanceRecord(
            attendance_session=session,
            student_enrollment=self.enr_3,  # enrolled in 10A!
            status='PRESENT'
        )
        with self.assertRaises(ValidationError):
            rec.clean()

    # -------------------------------------------------------------------------
    # 3. Session Locking (Close / Reopen)
    # -------------------------------------------------------------------------

    def test_close_and_reopen_attendance_session(self):
        """Closed sessions prevent modifications until reopened by authorized staff."""
        session = AttendanceSessionService.create_session(
            class_offering=self.offering_9a,
            session_date=date(2026, 10, 8),
            session_type='DAILY',
            recorded_by=self.teacher_1,
            created_by=self.user_teacher_1
        )
        AttendanceSessionService.close_session(session, user=self.user_admin)
        self.assertTrue(session.is_closed)
        self.assertFalse(session.is_editable)

        with self.assertRaises(ValidationError):
            AttendanceRecordService.record_bulk_attendance(
                session=session,
                records_data=[{'enrollment_id': self.enr_1.id, 'status': 'PRESENT'}]
            )

        # Reopen session
        AttendanceSessionService.reopen_session(session, user=self.user_admin)
        self.assertFalse(session.is_closed)
        self.assertTrue(session.is_editable)

    # -------------------------------------------------------------------------
    # 4. Role-Based Permissions & Access Controls
    # -------------------------------------------------------------------------

    def test_teacher_can_take_attendance_for_assigned_class(self):
        """Teacher assigned to 9A can access the take-attendance page for 9A."""
        session = AttendanceSessionService.create_session(
            class_offering=self.offering_9a,
            session_date=date(2026, 10, 9),
            session_type='DAILY',
            recorded_by=self.teacher_1,
            created_by=self.user_teacher_1
        )
        self.client.force_login(self.user_teacher_1)
        resp = self.client.get(reverse('attendance_take', args=[session.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Chaltu Tolessa")

    def test_teacher_blocked_from_unassigned_class_attendance(self):
        """Teacher 1 (assigned to 9A) is blocked from taking attendance for 10A."""
        session_10a = AttendanceSessionService.create_session(
            class_offering=self.offering_10a,
            session_date=date(2026, 10, 9),
            session_type='DAILY',
            recorded_by=self.teacher_2,
            created_by=self.user_teacher_2
        )
        self.client.force_login(self.user_teacher_1)
        resp = self.client.get(reverse('attendance_take', args=[session_10a.id]))
        self.assertEqual(resp.status_code, 403)

    def test_registrar_can_manage_all_attendance_sessions(self):
        """Registrar can view and create attendance for any classroom."""
        self.client.force_login(self.user_registrar)
        resp = self.client.get(reverse('attendance_sessions'))
        self.assertEqual(resp.status_code, 200)

        # Create session via view
        resp_post = self.client.post(reverse('attendance_session_create'), {
            'class_offering': self.offering_10a.id,
            'date': '2026-10-12',
            'session_type': 'DAILY',
            'remarks': 'Registrar created'
        })
        self.assertEqual(resp_post.status_code, 302)
        self.assertTrue(AttendanceSession.objects.filter(class_offering=self.offering_10a, date='2026-10-12').exists())

    def test_principal_read_only_access_and_reporting(self):
        """Principal can view school-wide attendance summaries, reports, and alerts."""
        self.client.force_login(self.user_principal)
        resp_dash = self.client.get(reverse('attendance_index'))
        self.assertEqual(resp_dash.status_code, 200)

        resp_rep = self.client.get(reverse('attendance_reports'))
        self.assertEqual(resp_rep.status_code, 200)

        resp_alerts = self.client.get(reverse('attendance_alerts'))
        self.assertEqual(resp_alerts.status_code, 200)

    def test_unauthenticated_user_redirected(self):
        """Unauthenticated requests are redirected to login."""
        resp = self.client.get(reverse('attendance_index'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    # -------------------------------------------------------------------------
    # 5. Reports & Exports
    # -------------------------------------------------------------------------

    def test_excel_and_pdf_export_generation(self):
        """Reports can be exported to Excel (.xlsx) and PDF format."""
        session = AttendanceSessionService.create_session(
            class_offering=self.offering_9a,
            session_date=date(2026, 10, 15),
            session_type='DAILY',
            recorded_by=self.teacher_1,
            created_by=self.user_teacher_1
        )
        AttendanceRecordService.record_bulk_attendance(
            session=session,
            records_data=[{'enrollment_id': self.enr_1.id, 'status': 'PRESENT'}]
        )

        self.client.force_login(self.user_registrar)

        # Excel
        resp_excel = self.client.get(reverse('attendance_export_excel') + f"?session_id={session.id}")
        self.assertEqual(resp_excel.status_code, 200)
        self.assertEqual(
            resp_excel['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

        # PDF
        resp_pdf = self.client.get(reverse('attendance_export_pdf') + f"?session_id={session.id}")
        self.assertEqual(resp_pdf.status_code, 200)
        self.assertEqual(resp_pdf['Content-Type'], 'application/pdf')

    # -------------------------------------------------------------------------
    # 6. Student Attendance History & Early-Warning Alerts
    # -------------------------------------------------------------------------

    def test_student_longitudinal_attendance_profile(self):
        """Student attendance profile aggregates records correctly."""
        session = AttendanceSessionService.create_session(
            class_offering=self.offering_9a,
            session_date=date(2026, 10, 16),
            session_type='DAILY',
            recorded_by=self.teacher_1,
            created_by=self.user_teacher_1
        )
        AttendanceRecordService.record_bulk_attendance(
            session=session,
            records_data=[{'enrollment_id': self.enr_1.id, 'status': 'PRESENT'}]
        )

        summary = AttendanceAnalyticsService.get_student_summary(self.student_1)
        self.assertEqual(summary['total_sessions'], 1)
        self.assertEqual(summary['present'], 1)
        self.assertEqual(summary['rate'], 100.0)

        self.client.force_login(self.user_principal)
        resp = self.client.get(reverse('student_attendance_detail', args=[self.student_1.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Chaltu Tolessa")

    def test_attendance_early_warning_alerts(self):
        """Attendance alerts trigger for chronic absenteeism and missing daily sessions."""
        # Record 4 sessions for ST-002 with 3 absences and 1 present (25% rate)
        for day in range(1, 5):
            s = AttendanceSessionService.create_session(
                class_offering=self.offering_9a,
                session_date=date(2026, 10, 18 + day),
                session_type='DAILY',
                recorded_by=self.teacher_1,
                created_by=self.user_teacher_1
            )
            st_status = 'PRESENT' if day == 1 else 'ABSENT'
            AttendanceRecordService.record_bulk_attendance(
                session=s,
                records_data=[{'enrollment_id': self.enr_2.id, 'status': st_status}]
            )

        alerts = AttendanceAnalyticsService.get_attendance_alerts(academic_year=self.ay_2026, threshold_pct=75.0)
        flagged_students = [a['student'].admission_number for a in alerts['chronic_alerts']]
        self.assertIn("ST-2026-002", flagged_students)
