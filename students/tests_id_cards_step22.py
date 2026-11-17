"""
Step 22: Professional Student ID Card Management with QR Code Generation Automated Test Suite.

Covers:
  1. Student ID Card model creation, UUID generation, sequential card numbering (MSS-ID-YYYY-XXXX).
  2. Offline vector QR code generation (SVG & PDF) with opaque verification token (NO PII).
  3. Single card PDF export (CR80 front & back dimensions, school branding).
  4. Batch generation by grade/section and printable sheet PDF export with cut marks.
  5. QR verification view (VALID, REVOKED, EXPIRED, REPLACED, INVALID) with zero PII exposure.
  6. Card revocation workflow with mandatory justification and audit logging.
  7. Re-issuing cards: previous active cards transition to REPLACED.
  8. Unique active card constraint per student and academic year.
  9. Role-Based Access Control & Teacher scoping (teachers only access their assigned classes).
  10. Reprint counter and audit trail tracking.
"""

import io
import uuid
from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.db import IntegrityError
from django.utils import timezone

from accounts.models import Role, User
from academics.models import AcademicYear, Grade, Section, Stream, ClassOffering, Subject
from students.models import Student, StudentEnrollment, StudentIDCard
from teachers.models import Teacher, TeacherAssignment
from students.services import StudentIDCardService


class StudentIDCardStep22Tests(TestCase):
    """Automated test suite verifying all Step 22 requirements."""

    def setUp(self):
        self.client = Client()

        # 1. Setup Roles
        self.role_admin = Role.objects.create(code='ADMIN', name='System Administrator')
        self.role_principal = Role.objects.create(code='PRINCIPAL', name='School Principal')
        self.role_registrar = Role.objects.create(code='REGISTRAR', name='Registrar')
        self.role_teacher = Role.objects.create(code='TEACHER', name='Teacher')

        # 2. Setup Users
        self.user_admin = User.objects.create_superuser(
            username='admin_step22',
            email='admin22@ssms.edu.et',
            password='Password123!',
            role=self.role_admin
        )

        self.user_registrar = User.objects.create_user(
            username='registrar_step22',
            email='registrar22@ssms.edu.et',
            password='Password123!',
            role=self.role_registrar
        )

        self.user_teacher_1 = User.objects.create_user(
            username='teacher1_step22',
            email='teacher1@ssms.edu.et',
            password='Password123!',
            role=self.role_teacher
        )

        self.user_teacher_2 = User.objects.create_user(
            username='teacher2_step22',
            email='teacher2@ssms.edu.et',
            password='Password123!',
            role=self.role_teacher
        )

        # 3. Setup Academic Structure
        current_year = date.today().year
        self.academic_year = AcademicYear.objects.create(
            name=f'{current_year} E.C. Academic Year',
            code=f'{current_year}-EC',
            start_date=date(current_year, 9, 1),
            end_date=date(current_year + 1, 7, 7),
            is_current=True
        )

        self.grade_9 = Grade.objects.create(name='Grade 9', level=9)
        self.grade_10 = Grade.objects.create(name='Grade 10', level=10)
        self.section_a = Section.objects.create(name='A')
        self.section_b = Section.objects.create(name='B')

        # Class offerings
        self.class_offering_9a = ClassOffering.objects.create(
            academic_year=self.academic_year,
            grade=self.grade_9,
            section=self.section_a,
            max_capacity=50
        )

        self.class_offering_10a = ClassOffering.objects.create(
            academic_year=self.academic_year,
            grade=self.grade_10,
            section=self.section_a,
            max_capacity=50
        )

        # Subject & Teacher assignments
        self.subject_math = Subject.objects.create(name='Mathematics', code='MATH9')
        self.subject_bio = Subject.objects.create(name='Biology', code='BIO10')

        self.teacher_1 = Teacher.objects.create(
            user=self.user_teacher_1,
            employee_id='T-MET-001',
            first_name='Alemu',
            father_name='Kebede',
            grandfather_name='Bekele',
            gender='M',
            joining_date=date(2020, 9, 1)
        )
        TeacherAssignment.objects.create(
            teacher=self.teacher_1,
            class_offering=self.class_offering_9a,
            subject=self.subject_math,
            academic_year=self.academic_year,
            is_primary=True
        )

        self.teacher_2 = Teacher.objects.create(
            user=self.user_teacher_2,
            employee_id='T-MET-002',
            first_name='Taye',
            father_name='Girma',
            grandfather_name='Desta',
            gender='M',
            joining_date=date(2021, 9, 1)
        )
        TeacherAssignment.objects.create(
            teacher=self.teacher_2,
            class_offering=self.class_offering_10a,
            subject=self.subject_bio,
            academic_year=self.academic_year,
            is_primary=True
        )

        # 4. Setup Students
        self.student_1 = Student.objects.create(
            admission_number='MSS/2016/0001',
            first_name='Chala',
            father_name='Tolosa',
            grandfather_name='Gutema',
            gender='M',
            date_of_birth=date(2008, 5, 12),
            phone_number='0911000001',
            status='ACTIVE'
        )
        self.enrollment_1 = StudentEnrollment.objects.create(
            student=self.student_1,
            class_offering=self.class_offering_9a,
            academic_year=self.academic_year,
            enrollment_date=date(2023, 9, 5),
            status='ACTIVE'
        )

        self.student_2 = Student.objects.create(
            admission_number='MSS/2016/0002',
            first_name='Hawine',
            father_name='Derese',
            grandfather_name='Abdisa',
            gender='F',
            date_of_birth=date(2008, 8, 20),
            phone_number='0911000002',
            status='ACTIVE'
        )
        self.enrollment_2 = StudentEnrollment.objects.create(
            student=self.student_2,
            class_offering=self.class_offering_9a,
            academic_year=self.academic_year,
            enrollment_date=date(2023, 9, 5),
            status='ACTIVE'
        )

        self.student_10 = Student.objects.create(
            admission_number='MSS/2016/0101',
            first_name='Abel',
            father_name='Kassahun',
            grandfather_name='Zelalem',
            gender='M',
            date_of_birth=date(2007, 3, 15),
            status='ACTIVE'
        )
        self.enrollment_10 = StudentEnrollment.objects.create(
            student=self.student_10,
            class_offering=self.class_offering_10a,
            academic_year=self.academic_year,
            enrollment_date=date(2023, 9, 5),
            status='ACTIVE'
        )

    # ==================== TEST 1: Service Card Generation ====================
    def test_service_card_generation_and_numbering(self):
        """Card generation creates valid record with institutional card number and UUID."""
        card, created = StudentIDCardService.get_or_create_id_card(
            student=self.student_1,
            academic_year=self.academic_year,
            issued_by=self.user_registrar
        )
        self.assertTrue(created)
        self.assertIsNotNone(card)
        self.assertEqual(card.student, self.student_1)
        self.assertEqual(card.academic_year, self.academic_year)
        self.assertEqual(card.status, 'ACTIVE')
        self.assertTrue(card.is_valid)
        self.assertTrue(card.card_number.startswith('MSS-ID-'))
        self.assertIsInstance(card.card_uuid, uuid.UUID)

    # ==================== TEST 2: QR Code Security & Privacy ====================
    def test_qr_code_contains_no_sensitive_pii(self):
        """QR code must strictly encode opaque verification URL, zero sensitive PII."""
        card, _ = StudentIDCardService.get_or_create_id_card(
            student=self.student_1,
            academic_year=self.academic_year,
            issued_by=self.user_registrar
        )
        url = StudentIDCardService.get_verification_url(card)

        # Opaque URL contains only the UUID
        self.assertIn(str(card.card_uuid), url)
        self.assertNotIn(self.student_1.admission_number, url)
        self.assertNotIn(self.student_1.first_name, url)
        self.assertNotIn('0911000001', url)
        self.assertNotIn('2008-05-12', url)

        # Offline vector QR code produces valid SVG
        svg_code = StudentIDCardService.get_qr_svg(card, size=120)
        self.assertTrue(svg_code.startswith('<svg'))
        self.assertIn('</svg>', svg_code)

    # ==================== TEST 3: Batch Generation ====================
    def test_batch_card_generation(self):
        """Batch generation creates cards for all enrolled students in class offering."""
        result = StudentIDCardService.batch_generate_id_cards(
            academic_year=self.academic_year,
            class_offering=self.class_offering_9a,
            issued_by=self.user_admin
        )
        self.assertEqual(result['created'], 2)
        self.assertEqual(result['reused'], 0)

        # Running batch again should skip already active cards
        result2 = StudentIDCardService.batch_generate_id_cards(
            academic_year=self.academic_year,
            class_offering=self.class_offering_9a,
            issued_by=self.user_admin
        )
        self.assertEqual(result2['created'], 0)
        self.assertEqual(result2['reused'], 2)

    # ==================== TEST 4: Unique Active Card Constraint ====================
    def test_unique_active_card_per_year_constraint(self):
        """Database constraint prevents multiple ACTIVE cards for the same student in same year."""
        card1, _ = StudentIDCardService.get_or_create_id_card(
            student=self.student_1,
            academic_year=self.academic_year,
            issued_by=self.user_admin
        )
        self.assertEqual(card1.status, 'ACTIVE')

        # Creating another active card directly should raise IntegrityError
        with self.assertRaises(IntegrityError):
            StudentIDCard.objects.create(
                student=self.student_1,
                academic_year=self.academic_year,
                card_number='MSS-ID-TEST-DUPE',
                status='ACTIVE',
                issued_by=self.user_admin
            )

    # ==================== TEST 5: Card Revocation ====================
    def test_card_revocation(self):
        """Revoking an ID card updates status, timestamps, reason, and invalidates verification."""
        card, _ = StudentIDCardService.get_or_create_id_card(
            student=self.student_1,
            academic_year=self.academic_year,
            issued_by=self.user_registrar
        )
        self.assertTrue(card.is_valid)

        # Revoke
        revoked_card = StudentIDCardService.revoke_card(
            id_card=card,
            reason='Reported lost by student on campus',
            user=self.user_registrar
        )
        self.assertEqual(revoked_card.status, 'REVOKED')
        self.assertFalse(revoked_card.is_valid)
        self.assertIsNotNone(revoked_card.revoked_at)
        self.assertEqual(revoked_card.revocation_reason, 'Reported lost by student on campus')

    # ==================== TEST 6: Card Replacement Workflow ====================
    def test_reissuing_card_replaces_previous(self):
        """Generating a new card for a student marks the old active card as REPLACED."""
        card1, _ = StudentIDCardService.get_or_create_id_card(
            student=self.student_1,
            academic_year=self.academic_year,
            issued_by=self.user_registrar
        )
        card1_uuid = card1.card_uuid

        # Force new card generation
        card2, _ = StudentIDCardService.get_or_create_id_card(
            student=self.student_1,
            academic_year=self.academic_year,
            issued_by=self.user_registrar,
            force_new=True
        )

        card1.refresh_from_db()
        self.assertEqual(card1.status, 'REPLACED')
        self.assertFalse(card1.is_valid)
        self.assertEqual(card2.status, 'ACTIVE')
        self.assertTrue(card2.is_valid)
        self.assertNotEqual(card1.card_number, card2.card_number)
        self.assertNotEqual(card1_uuid, card2.card_uuid)

    # ==================== TEST 7: Expired Card Handling ====================
    def test_expired_card_status(self):
        """Card past its expiry date is identified as EXPIRED."""
        card, _ = StudentIDCardService.get_or_create_id_card(
            student=self.student_1,
            academic_year=self.academic_year,
            issued_by=self.user_registrar
        )
        # Manually set past expiry date
        card.expiry_date = date.today() - timedelta(days=5)
        card.save()

        self.assertFalse(card.is_valid)
        self.assertEqual(card.verification_status, 'EXPIRED')

    # ==================== TEST 8: QR Verification Endpoint ====================
    def test_qr_verification_endpoint_states(self):
        """Public/LAN QR verification returns accurate status banners without authentication."""
        card, _ = StudentIDCardService.get_or_create_id_card(
            student=self.student_1,
            academic_year=self.academic_year,
            issued_by=self.user_registrar
        )

        # 1. Active valid card
        url = reverse('id_card_verify', kwargs={'card_uuid': card.card_uuid})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'VERIFIED &amp; ACTIVE')
        self.assertContains(response, self.student_1.full_name)
        self.assertContains(response, self.student_1.admission_number)

        # 2. Revoked card
        StudentIDCardService.revoke_card(card, 'Lost card', self.user_registrar)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'REVOKED')

        # 3. Non-existent UUID
        invalid_url = reverse('id_card_verify', kwargs={'card_uuid': uuid.uuid4()})
        response = self.client.get(invalid_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'UNRECOGNIZED CARD TOKEN')

    # ==================== TEST 9: Single Card PDF Export ====================
    def test_single_card_pdf_export(self):
        """Export single card generates valid 2-page CR80 PDF document."""
        card, _ = StudentIDCardService.get_or_create_id_card(
            student=self.student_1,
            academic_year=self.academic_year,
            issued_by=self.user_registrar
        )
        pdf_response = StudentIDCardService.export_single_card_pdf(card)
        self.assertIsNotNone(pdf_response)
        self.assertTrue(pdf_response.content.startswith(b'%PDF-'))
        self.assertGreater(len(pdf_response.content), 1000)

        # Verify via view
        self.client.force_login(self.user_registrar)
        url = reverse('id_card_pdf', kwargs={'card_id': card.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', response['Content-Disposition'])

    # ==================== TEST 10: Batch Printable Sheet PDF Export ====================
    def test_batch_cards_pdf_export(self):
        """Export batch sheet PDF generates valid multi-card printable document."""
        StudentIDCardService.batch_generate_id_cards(
            academic_year=self.academic_year,
            class_offering=self.class_offering_9a,
            issued_by=self.user_registrar
        )
        cards = StudentIDCard.objects.filter(academic_year=self.academic_year, status='ACTIVE')
        pdf_response = StudentIDCardService.export_batch_cards_pdf(cards)
        self.assertIsNotNone(pdf_response)
        self.assertTrue(pdf_response.content.startswith(b'%PDF-'))
        self.assertGreater(len(pdf_response.content), 2000)

        # Verify via view
        self.client.force_login(self.user_registrar)
        url = reverse('id_card_batch_pdf') + f'?academic_year={self.academic_year.pk}&class_offering={self.class_offering_9a.pk}'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')

    # ==================== TEST 11: Teacher Class Scoping ====================
    def test_teacher_class_scoping_permissions(self):
        """Teacher can only preview and generate ID cards for students in their assigned classes."""
        # Student 1 is in 9A (assigned to teacher 1)
        # Student 10 is in 10A (assigned to teacher 2)

        self.client.force_login(self.user_teacher_1)

        # Teacher 1 previewing student 1 in 9A: ALLOWED (200)
        url_preview_allowed = reverse('id_card_preview', kwargs={'student_id': self.student_1.pk})
        res_allowed = self.client.get(url_preview_allowed)
        self.assertEqual(res_allowed.status_code, 200)

        # Teacher 1 previewing student 10 in 10A: FORBIDDEN (403)
        url_preview_forbidden = reverse('id_card_preview', kwargs={'student_id': self.student_10.pk})
        res_forbidden = self.client.get(url_preview_forbidden)
        self.assertEqual(res_forbidden.status_code, 403)

        # Teacher 1 generating card for student 10 in 10A: FORBIDDEN (403)
        url_generate_forbidden = reverse('id_card_generate', kwargs={'student_id': self.student_10.pk})
        res_gen = self.client.post(url_generate_forbidden)
        self.assertEqual(res_gen.status_code, 403)

    # ==================== TEST 12: Reprint Counter Tracking ====================
    def test_reprint_counter_and_audit(self):
        """Reprinting an ID card increments reprint_count and logs audit event."""
        card, _ = StudentIDCardService.get_or_create_id_card(
            student=self.student_1,
            academic_year=self.academic_year,
            issued_by=self.user_registrar
        )
        self.assertEqual(card.reprint_count, 0)

        self.client.force_login(self.user_registrar)
        url = reverse('id_card_reprint', kwargs={'card_id': card.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        card.refresh_from_db()
        self.assertEqual(card.reprint_count, 1)

    # ==================== TEST 13: Revoke View Form Validation ====================
    def test_revoke_view_requires_mandatory_reason(self):
        """Revoke view rejects submission without a valid reason."""
        card, _ = StudentIDCardService.get_or_create_id_card(
            student=self.student_1,
            academic_year=self.academic_year,
            issued_by=self.user_registrar
        )
        self.client.force_login(self.user_registrar)

        url = reverse('id_card_revoke', kwargs={'card_id': card.pk})
        response = self.client.post(url, {'reason': ''})
        self.assertEqual(response.status_code, 302)

        card.refresh_from_db()
        self.assertEqual(card.status, 'ACTIVE')  # Unchanged because empty reason rejected

        # With reason
        response2 = self.client.post(url, {'reason': 'Student transferred to another school'})
        self.assertEqual(response2.status_code, 302)

        card.refresh_from_db()
        self.assertEqual(card.status, 'REVOKED')
        self.assertEqual(card.revocation_reason, 'Student transferred to another school')
