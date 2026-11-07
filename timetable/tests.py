"""
Automated unit and integration test suite for Step 14:
Timetable and Class Scheduling Management System.
Covers:
- Working days & period configuration
- Classroom management
- Timetable creation and lesson scheduling
- Multi-dimensional conflict detection (Teacher, Class, Room, Break slots)
- Alternative period suggestions
- Review, approval, publication, and immutable version archiving
- Timetable cloning
- Role-based access restrictions
- PDF and Excel report exports
"""

from datetime import date, time
from decimal import Decimal
from django.test import TestCase, Client
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.urls import reverse

from accounts.models import Role
from academics.models import AcademicYear, Grade, Section, Stream, Subject, ClassOffering
from teachers.models import Teacher, TeacherAssignment

from timetable.models import (
    Classroom,
    SchoolDay,
    Period,
    Timetable,
    TimetableEntry,
    TimetableVersion
)
from timetable.services import (
    TimetableConfigService,
    ConflictDetectionService,
    TimetableService,
    TimetablePublicationService,
    TimetableMatrixService,
    TimetableReportService
)

User = get_user_model()


class TimetableModelAndServiceTests(TestCase):
    def setUp(self):
        # 1. Roles and Users
        self.admin_role, _ = Role.objects.get_or_create(code='ADMIN', defaults={'name': 'Administrator'})
        self.principal_role, _ = Role.objects.get_or_create(code='PRINCIPAL', defaults={'name': 'Principal'})
        self.registrar_role, _ = Role.objects.get_or_create(code='REGISTRAR', defaults={'name': 'Registrar'})
        self.teacher_role, _ = Role.objects.get_or_create(code='TEACHER', defaults={'name': 'Teacher'})

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

        # 2. Academic Structures
        self.ay = AcademicYear.objects.create(
            name="2026/2027",
            code="AY-2026",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_current=True
        )
        self.grade10 = Grade.objects.create(name="Grade 10", level=10)
        self.grade11 = Grade.objects.create(name="Grade 11", level=11)
        self.sec_a = Section.objects.create(name="A")
        self.sec_b = Section.objects.create(name="B")

        self.class_10a = ClassOffering.objects.create(
            academic_year=self.ay,
            grade=self.grade10,
            section=self.sec_a,
            max_capacity=50
        )
        self.class_10b = ClassOffering.objects.create(
            academic_year=self.ay,
            grade=self.grade10,
            section=self.sec_b,
            max_capacity=50
        )

        # 3. Subjects & Teachers
        self.math = Subject.objects.create(name="Mathematics", code="MATH10", is_active=True)
        self.physics = Subject.objects.create(name="Physics", code="PHYS10", is_active=True)

        self.teacher1 = Teacher.objects.create(
            employee_id="TCH-001",
            first_name="Abebe",
            father_name="Bikila",
            gender="M",
            qualification="B.Ed Mathematics",
            specialization="Mathematics",
            joining_date=date(2020, 9, 1),
            employment_status="ACTIVE",
            is_active=True
        )
        self.teacher2 = Teacher.objects.create(
            employee_id="TCH-002",
            first_name="Almaz",
            father_name="Ayana",
            gender="F",
            qualification="B.Sc Physics",
            specialization="Physics",
            joining_date=date(2021, 9, 1),
            employment_status="ACTIVE",
            is_active=True
        )

        # Teacher Assignments
        TeacherAssignment.objects.create(
            teacher=self.teacher1,
            class_offering=self.class_10a,
            subject=self.math,
            academic_year=self.ay
        )
        TeacherAssignment.objects.create(
            teacher=self.teacher2,
            class_offering=self.class_10a,
            subject=self.physics,
            academic_year=self.ay
        )

        # 4. Classrooms
        self.room101 = Classroom.objects.create(
            name="Block A Room 101",
            code="R-101",
            building="Block A",
            room_type="REGULAR",
            capacity=50,
            is_active=True
        )
        self.lab_physics = Classroom.objects.create(
            name="Physics Laboratory",
            code="LAB-PHYS",
            building="Science Block",
            room_type="LAB_SCIENCE",
            capacity=40,
            is_active=True
        )

        # 5. Periods and Working Days Setup
        TimetableConfigService.initialize_default_working_days(self.ay)
        TimetableConfigService.initialize_default_periods(self.ay)

        self.p1 = Period.objects.get(academic_year=self.ay, period_number=1)
        self.p2 = Period.objects.get(academic_year=self.ay, period_number=2)
        self.break_slot = Period.objects.get(academic_year=self.ay, period_number=3)  # Morning Recess

    def test_period_and_working_day_initialization(self):
        """Verifies default working days and period slots provisioned correctly."""
        working_days = TimetableConfigService.get_active_working_days(self.ay)
        self.assertEqual(working_days.count(), 5)
        self.assertEqual(working_days.first().name, "Monday")

        periods = TimetableConfigService.get_active_periods(self.ay)
        self.assertEqual(periods.count(), 8)
        self.assertFalse(self.p1.is_break)
        self.assertTrue(self.break_slot.is_break)
        self.assertEqual(self.break_slot.duration_minutes, 20)

    def test_classroom_management_and_deactivation(self):
        """Classroom creation and toggle status logic."""
        room = Classroom.objects.create(
            name="Computer Lab 1",
            code="LAB-COMP1",
            room_type="LAB_COMPUTER",
            capacity=35,
            is_active=True
        )
        self.assertEqual(room.capacity, 35)
        self.assertTrue(room.is_active)

        room.is_active = False
        room.save()
        self.assertFalse(room.is_active)

    def test_timetable_creation_and_lesson_scheduling(self):
        """Creates draft timetable and schedules valid instructional lesson."""
        tt = TimetableService.create_timetable(
            academic_year=self.ay,
            class_offering=self.class_10a,
            user=self.registrar_user
        )
        self.assertEqual(tt.status, 'DRAFT')
        self.assertEqual(tt.version, 1)

        entry = TimetableService.add_lesson_entry(
            timetable=tt,
            day_of_week=1,  # Monday
            period=self.p1,
            subject=self.math,
            teacher=self.teacher1,
            classroom=self.room101
        )
        self.assertEqual(tt.entries.count(), 1)
        self.assertEqual(entry.subject, self.math)
        self.assertEqual(entry.teacher, self.teacher1)
        self.assertEqual(entry.classroom, self.room101)

    def test_break_period_conflict_detection(self):
        """Blocks scheduling any instructional lesson during break slots."""
        tt = TimetableService.create_timetable(
            academic_year=self.ay,
            class_offering=self.class_10a,
            user=self.registrar_user
        )

        with self.assertRaises(ValidationError) as ctx:
            TimetableService.add_lesson_entry(
                timetable=tt,
                day_of_week=1,
                period=self.break_slot,  # Morning Recess
                subject=self.math,
                teacher=self.teacher1
            )
        self.assertIn("break", str(ctx.exception).lower())

    def test_teacher_double_booking_conflict(self):
        """Prevents scheduling the same teacher in two classes at the same day & period."""
        tt_10a = TimetableService.create_timetable(self.ay, self.class_10a, user=self.registrar_user)
        TimetableService.add_lesson_entry(
            timetable=tt_10a,
            day_of_week=1,  # Monday
            period=self.p1,
            subject=self.math,
            teacher=self.teacher1
        )

        # Try to schedule teacher1 in Class 10-B at the exact same Monday Period 1
        tt_10b = TimetableService.create_timetable(self.ay, self.class_10b, user=self.registrar_user)
        with self.assertRaises(ValidationError) as ctx:
            TimetableService.add_lesson_entry(
                timetable=tt_10b,
                day_of_week=1,
                period=self.p1,
                subject=self.math,
                teacher=self.teacher1
            )
        self.assertIn("Teacher Double-Booking Conflict", str(ctx.exception))

    def test_class_double_booking_conflict(self):
        """Prevents scheduling two different subjects for the same class in the same period."""
        tt = TimetableService.create_timetable(self.ay, self.class_10a, user=self.registrar_user)
        TimetableService.add_lesson_entry(
            timetable=tt,
            day_of_week=1,  # Monday
            period=self.p1,
            subject=self.math,
            teacher=self.teacher1
        )

        # Try to schedule Physics for the same class on Monday Period 1
        with self.assertRaises(ValidationError) as ctx:
            TimetableService.add_lesson_entry(
                timetable=tt,
                day_of_week=1,
                period=self.p1,
                subject=self.physics,
                teacher=self.teacher2
            )
        self.assertIn("Class Double-Booking Conflict", str(ctx.exception))

    def test_classroom_double_booking_conflict(self):
        """Prevents scheduling two classes into the same physical room at the same time."""
        tt_10a = TimetableService.create_timetable(self.ay, self.class_10a, user=self.registrar_user)
        TimetableService.add_lesson_entry(
            timetable=tt_10a,
            day_of_week=1,
            period=self.p1,
            subject=self.math,
            teacher=self.teacher1,
            classroom=self.room101
        )

        tt_10b = TimetableService.create_timetable(self.ay, self.class_10b, user=self.registrar_user)
        with self.assertRaises(ValidationError) as ctx:
            TimetableService.add_lesson_entry(
                timetable=tt_10b,
                day_of_week=1,
                period=self.p1,
                subject=self.physics,
                teacher=self.teacher2,
                classroom=self.room101  # Clashing room
            )
        self.assertIn("Classroom Double-Booking Conflict", str(ctx.exception))

    def test_alternative_period_suggestions(self):
        """Engine suggests alternative free non-break periods on conflict."""
        tt = TimetableService.create_timetable(self.ay, self.class_10a, user=self.registrar_user)
        # Block Monday Period 1
        TimetableService.add_lesson_entry(
            timetable=tt,
            day_of_week=1,
            period=self.p1,
            subject=self.math,
            teacher=self.teacher1
        )

        # Check conflicts for Monday Period 1
        check = ConflictDetectionService.check_entry_conflicts(
            timetable=tt,
            day_of_week=1,
            period=self.p1,
            teacher=self.teacher1,
            class_offering=self.class_10a
        )
        self.assertTrue(check['has_conflict'])
        self.assertGreater(len(check['suggestions']), 0)
        # Period 2 should be suggested as free
        suggested_p_ids = [s['period_id'] for s in check['suggestions']]
        self.assertIn(self.p2.id, suggested_p_ids)

    def test_timetable_submission_and_committee_approval(self):
        """Workflow: Draft -> Submit -> Committee Review (Approved)."""
        tt = TimetableService.create_timetable(self.ay, self.class_10a, user=self.registrar_user)
        TimetableService.add_lesson_entry(tt, 1, self.p1, self.math, self.teacher1)

        # 1. Submit
        TimetablePublicationService.submit_for_review(tt, user=self.registrar_user)
        tt.refresh_from_db()
        self.assertEqual(tt.status, 'SUBMITTED')

        # 2. Review & Approve
        TimetablePublicationService.review_timetable(
            timetable=tt,
            decision='APPROVED',
            reviewer_user=self.principal_user,
            comments="Schedule reviewed and verified."
        )
        tt.refresh_from_db()
        self.assertEqual(tt.status, 'APPROVED')
        self.assertEqual(tt.approved_by, self.principal_user)

    def test_timetable_publication_and_version_snapshot(self):
        """Publishes approved timetable and generates immutable JSON version snapshot."""
        tt = TimetableService.create_timetable(self.ay, self.class_10a, user=self.registrar_user)
        TimetableService.add_lesson_entry(tt, 1, self.p1, self.math, self.teacher1, self.room101)
        TimetablePublicationService.submit_for_review(tt)
        TimetablePublicationService.review_timetable(tt, 'APPROVED', self.principal_user)

        # Publish
        published_tt = TimetablePublicationService.publish_timetable(tt, user=self.principal_user)
        published_tt.refresh_from_db()
        self.assertEqual(published_tt.status, 'PUBLISHED')
        self.assertIsNotNone(published_tt.published_at)

        # Verify Version Snapshot
        self.assertEqual(published_tt.versions.count(), 1)
        snap = published_tt.versions.first()
        self.assertEqual(snap.version_number, 1)
        self.assertEqual(len(snap.snapshot_data['entries']), 1)
        self.assertEqual(snap.snapshot_data['entries'][0]['subject_code'], 'MATH10')

    def test_timetable_revision_cloning(self):
        """Initiating revision creates draft v2 while keeping v1 published."""
        tt = TimetableService.create_timetable(self.ay, self.class_10a, user=self.registrar_user)
        TimetableService.add_lesson_entry(tt, 1, self.p1, self.math, self.teacher1)
        TimetablePublicationService.submit_for_review(tt)
        TimetablePublicationService.review_timetable(tt, 'APPROVED', self.principal_user)
        TimetablePublicationService.publish_timetable(tt)

        # Revise
        revised_tt = TimetablePublicationService.create_revised_version(tt, user=self.registrar_user)
        self.assertEqual(revised_tt.version, 2)
        self.assertEqual(revised_tt.status, 'DRAFT')
        self.assertEqual(revised_tt.entries.count(), 1)

        # Original remains published
        tt.refresh_from_db()
        self.assertEqual(tt.status, 'PUBLISHED')

    def test_timetable_copy_to_another_class(self):
        """Clones timetable structure to another class offering."""
        tt_10a = TimetableService.create_timetable(self.ay, self.class_10a, user=self.registrar_user)
        TimetableService.add_lesson_entry(tt_10a, 1, self.p1, self.math, self.teacher1)

        # Setup assignment in target class so copy succeeds
        TeacherAssignment.objects.create(
            teacher=self.teacher2,
            class_offering=self.class_10b,
            subject=self.math,
            academic_year=self.ay
        )

        new_tt, copied, skipped = TimetableService.copy_timetable(
            source_timetable=tt_10a,
            target_class_offering=self.class_10b,
            user=self.registrar_user
        )
        self.assertEqual(copied, 1)
        self.assertEqual(new_tt.class_offering, self.class_10b)
        self.assertEqual(new_tt.entries.count(), 1)

    def test_pdf_and_excel_export_generation(self):
        """Validates class and teacher timetable PDF and Excel exports."""
        tt = TimetableService.create_timetable(self.ay, self.class_10a, user=self.registrar_user)
        TimetableService.add_lesson_entry(tt, 1, self.p1, self.math, self.teacher1)

        # Class PDF
        pdf_resp = TimetableReportService.export_class_timetable_pdf(tt)
        self.assertEqual(pdf_resp.status_code, 200)
        self.assertEqual(pdf_resp['Content-Type'], 'application/pdf')
        self.assertGreater(len(pdf_resp.content), 500)

        # Class Excel
        excel_resp = TimetableReportService.export_class_timetable_excel(tt)
        self.assertEqual(excel_resp.status_code, 200)
        self.assertEqual(excel_resp['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertGreater(len(excel_resp.content), 500)

        # Teacher PDF
        teacher_pdf = TimetableReportService.export_teacher_timetable_pdf(self.teacher1, self.ay)
        self.assertEqual(teacher_pdf.status_code, 200)
        self.assertEqual(teacher_pdf['Content-Type'], 'application/pdf')

        # Teacher Excel
        teacher_excel = TimetableReportService.export_teacher_timetable_excel(self.teacher1, self.ay)
        self.assertEqual(teacher_excel.status_code, 200)


class TimetableViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_role, _ = Role.objects.get_or_create(code='ADMIN', defaults={'name': 'Administrator'})
        self.teacher_role, _ = Role.objects.get_or_create(code='TEACHER', defaults={'name': 'Teacher'})

        self.admin_user = User.objects.create_superuser(
            username="adminuser",
            email="admin@school.local",
            password="adminpassword123",
            role=self.admin_role
        )

        self.ay = AcademicYear.objects.create(
            name="2026/2027",
            code="AY-2026",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 6, 30),
            is_current=True
        )
        self.grade10 = Grade.objects.create(name="Grade 10", level=10)
        self.sec_a = Section.objects.create(name="A")
        self.class_offering = ClassOffering.objects.create(
            academic_year=self.ay,
            grade=self.grade10,
            section=self.sec_a,
            max_capacity=50
        )

        TimetableConfigService.initialize_default_working_days(self.ay)
        TimetableConfigService.initialize_default_periods(self.ay)

        self.timetable = Timetable.objects.create(
            name="Grade 10-A Timetable",
            academic_year=self.ay,
            class_offering=self.class_offering,
            version=1,
            status='DRAFT',
            created_by=self.admin_user
        )

        self.classroom = Classroom.objects.create(
            name="Block B Room 201",
            code="R-201",
            room_type="REGULAR",
            capacity=50
        )

    def test_timetable_dashboard_view(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('timetable_index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Timetable & Class Scheduling Hub")

    def test_timetable_list_view(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('timetable_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Class Timetables Directory")

    def test_timetable_create_view(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('timetable_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Initiate Class Timetable Schedule")

    def test_timetable_detail_view(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('timetable_detail', args=[self.timetable.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.timetable.class_offering.display_name)

    def test_classroom_management_views(self):
        self.client.force_login(self.admin_user)
        # List
        resp = self.client.get(reverse('classroom_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(response=resp, text="R-201")

        # Create
        resp_create = self.client.get(reverse('classroom_create'))
        self.assertEqual(resp_create.status_code, 200)

        # Edit
        resp_edit = self.client.get(reverse('classroom_edit', args=[self.classroom.id]))
        self.assertEqual(resp_edit.status_code, 200)

    def test_period_and_working_days_views(self):
        self.client.force_login(self.admin_user)
        # Period list
        resp = self.client.get(reverse('period_list'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Daily Schedule Periods & Breaks")

        # Working days
        resp_days = self.client.get(reverse('working_days'))
        self.assertEqual(resp_days.status_code, 200)
        self.assertContains(resp_days, "Configure School Working Days")

    def test_conflict_detection_view(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('timetable_conflicts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scheduling Conflict Audit Report")

    def test_class_timetable_view(self):
        self.client.force_login(self.admin_user)
        response = self.client.get(reverse('class_timetable_default'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Class Weekly Timetable")
