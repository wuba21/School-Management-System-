"""
Step 23: Student Transfer and Leaving Certificate Management Automated Test Suite.

Covers:
  1. Transfer and Leaving Certificate creation and auto-population from student enrollment.
  2. Destination school validation on transfer certificates.
  3. Unique active certificate constraint per student, certificate type, and academic year.
  4. Multi-level Approval Workflow: DRAFT -> SUBMITTED -> APPROVED -> ISSUED (plus REJECTED and REVOKED).
  5. Strict RBAC enforcement: Teachers cannot approve/reject; only Principal or Admin can approve/reject.
  6. Sequential institutional reference numbering (MSS-TC-YYYY-XXXX and MSS-LC-YYYY-XXXX).
  7. Student academic history preservation: Master records and historical enrollments are never deleted.
  8. Revocation workflow with mandatory justification and audit logging.
  9. English-only A4 ReportLab PDF generation with double borders and security watermark for drafts.
  10. Internal-only verification portal requiring authentication and handling active, revoked, and nonexistent records.
  11. Dual Gregorian and Ethiopian calendar date formatting.
"""

import io
import uuid
from datetime import date, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.db import IntegrityError
from django.core.exceptions import PermissionDenied, ValidationError

from accounts.models import Role, User
from academics.models import AcademicYear, Grade, Section, Stream, ClassOffering, Subject
from students.models import Student, StudentEnrollment, StudentCertificate
from students.services import CertificateService


class StudentCertificateStep23Tests(TestCase):
    """Automated test suite verifying all Step 23 requirements."""

    def setUp(self):
        self.client = Client()

        # 1. Setup Roles
        self.role_admin = Role.objects.create(code='ADMIN', name='System Administrator')
        self.role_principal = Role.objects.create(code='PRINCIPAL', name='School Principal')
        self.role_registrar = Role.objects.create(code='REGISTRAR', name='Registrar')
        self.role_teacher = Role.objects.create(code='TEACHER', name='Teacher')

        # 2. Setup Users
        self.user_admin = User.objects.create_superuser(
            username='admin_step23',
            email='admin23@ssms.edu.et',
            password='Password123!',
            role=self.role_admin
        )

        self.user_principal = User.objects.create_user(
            username='principal_step23',
            email='principal23@ssms.edu.et',
            password='Password123!',
            role=self.role_principal
        )

        self.user_registrar = User.objects.create_user(
            username='registrar_step23',
            email='registrar23@ssms.edu.et',
            password='Password123!',
            role=self.role_registrar
        )

        self.user_teacher = User.objects.create_user(
            username='teacher_step23',
            email='teacher23@ssms.edu.et',
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

        self.grade_10 = Grade.objects.create(name='Grade 10', level=10)
        self.grade_12 = Grade.objects.create(name='Grade 12', level=12)
        self.section_a = Section.objects.create(name='A')
        self.stream_natural = Stream.objects.create(name='Natural Science', code='NAT')

        self.offering_10a = ClassOffering.objects.create(
            academic_year=self.academic_year,
            grade=self.grade_10,
            section=self.section_a
        )

        self.offering_12a = ClassOffering.objects.create(
            academic_year=self.academic_year,
            grade=self.grade_12,
            section=self.section_a,
            stream=self.stream_natural
        )

        # 4. Setup Students
        self.student_1 = Student.objects.create(
            first_name='Abel',
            father_name='Bekele',
            grandfather_name='Tesfaye',
            admission_number='MSS/2023/001',
            date_of_birth=date(2007, 3, 15),
            gender='M',
            status='ACTIVE',
            emergency_contact_name='Bekele Tesfaye',
            emergency_contact_phone='0911223344',
            emergency_contact_relation='Father'
        )

        self.enrollment_1 = StudentEnrollment.objects.create(
            student=self.student_1,
            class_offering=self.offering_10a,
            academic_year=self.academic_year,
            status='ACTIVE'
        )

        self.student_2 = Student.objects.create(
            first_name='Hiwot',
            father_name='Tadesse',
            grandfather_name='Girma',
            admission_number='MSS/2023/002',
            date_of_birth=date(2005, 8, 20),
            gender='F',
            status='ACTIVE',
            emergency_contact_name='Tadesse Girma',
            emergency_contact_phone='0911223355',
            emergency_contact_relation='Father'
        )

        self.enrollment_2 = StudentEnrollment.objects.create(
            student=self.student_2,
            class_offering=self.offering_12a,
            academic_year=self.academic_year,
            status='ACTIVE'
        )

    # -------------------------------------------------------------------------
    # 1. Model & Auto-Population Tests
    # -------------------------------------------------------------------------
    def test_create_transfer_certificate_request_auto_population(self):
        """Verify CertificateService auto-populates details from the student's active enrollment."""
        cert = CertificateService.create_certificate_request(
            student=self.student_1,
            certificate_type='TRANSFER',
            requested_by=self.user_registrar,
            effective_date=date.today(),
            destination_school='Gambella Comprehensive Secondary School',
            reason='Family relocation to Gambella town',
            academic_standing='Promoted to Grade 11',
            conduct='Excellent'
        )

        self.assertIsNotNone(cert.pk)
        self.assertIsNotNone(cert.certificate_uuid)
        self.assertEqual(cert.status, 'DRAFT')
        self.assertEqual(cert.certificate_type, 'TRANSFER')
        self.assertEqual(cert.student, self.student_1)
        self.assertEqual(cert.enrollment, self.enrollment_1)
        self.assertEqual(cert.academic_year, self.academic_year)
        self.assertEqual(cert.last_grade, self.grade_10)
        self.assertIn('A', cert.section_name)
        self.assertEqual(cert.admission_date, self.student_1.admission_date)
        self.assertEqual(cert.destination_school, 'Gambella Comprehensive Secondary School')
        self.assertIsNone(cert.certificate_number)  # Number assigned only upon issue

    def test_create_leaving_certificate_request(self):
        """Verify creation of leaving certificate for graduating Grade 12 student."""
        cert = CertificateService.create_certificate_request(
            student=self.student_2,
            certificate_type='LEAVING',
            requested_by=self.user_registrar,
            effective_date=date.today(),
            reason='Completion of Grade 12 National Secondary Education',
            academic_standing='Completed Grade 12 Curriculum',
            conduct='Very Good',
            remarks='Eligible for higher education entrance examination.'
        )

        self.assertEqual(cert.certificate_type, 'LEAVING')
        self.assertEqual(cert.last_grade, self.grade_12)
        self.assertEqual(cert.stream_name, 'Natural Science')
        self.assertEqual(cert.status, 'DRAFT')
        self.assertEqual(cert.destination_school, '')

    def test_destination_school_required_for_transfer_certificate(self):
        """Transfer certificate requests without destination school should raise ValidationError."""
        with self.assertRaises(ValidationError):
            CertificateService.create_certificate_request(
                student=self.student_1,
                certificate_type='TRANSFER',
                requested_by=self.user_registrar,
                destination_school='',  # Empty destination school
                reason='Relocation'
            )

    def test_duplicate_active_certificate_prevention(self):
        """Verify that a student cannot have multiple active certificates of the same type in the same year."""
        CertificateService.create_certificate_request(
            student=self.student_1,
            certificate_type='TRANSFER',
            requested_by=self.user_registrar,
            destination_school='Jimma High School',
            reason='Transfer'
        )

        # Attempting second transfer request should raise ValidationError
        with self.assertRaises(ValidationError):
            CertificateService.create_certificate_request(
                student=self.student_1,
                certificate_type='TRANSFER',
                requested_by=self.user_registrar,
                destination_school='Addis Ketema High School',
                reason='Transfer attempt 2'
            )

    # -------------------------------------------------------------------------
    # 2. Multi-Level Approval Workflow State Machine Tests
    # -------------------------------------------------------------------------
    def test_full_approval_workflow_lifecycle(self):
        """Verify DRAFT -> SUBMITTED -> APPROVED -> ISSUED transitions."""
        # 1. Draft
        cert = CertificateService.create_certificate_request(
            student=self.student_1,
            certificate_type='TRANSFER',
            requested_by=self.user_registrar,
            destination_school='Hawassa Comprehensive High School',
            reason='Relocation'
        )
        self.assertEqual(cert.status, 'DRAFT')

        # 2. Submit
        cert = CertificateService.submit_certificate(cert, submitted_by=self.user_registrar)
        self.assertEqual(cert.status, 'SUBMITTED')
        self.assertEqual(cert.reviewed_by, self.user_registrar)
        self.assertIsNotNone(cert.reviewed_at)

        # 3. Approve (Principal)
        cert = CertificateService.approve_certificate(
            cert,
            approved_by=self.user_principal,
            remarks='Approved following verified clearance.'
        )
        self.assertEqual(cert.status, 'APPROVED')
        self.assertEqual(cert.approved_by, self.user_principal)
        self.assertIsNotNone(cert.approved_at)

        # 4. Issue (Registrar / Admin)
        cert = CertificateService.issue_certificate(cert, issued_by=self.user_registrar)
        self.assertEqual(cert.status, 'ISSUED')
        self.assertEqual(cert.issued_by, self.user_registrar)
        self.assertIsNotNone(cert.issue_date)
        self.assertTrue(cert.certificate_number.startswith('MSS-TC-'))

        # Verify Student Master Status updated to TRANSFERRED
        self.student_1.refresh_from_db()
        self.assertEqual(self.student_1.status, 'TRANSFERRED')

        # Verify Student Academic History is preserved
        enrollment_count = StudentEnrollment.objects.filter(student=self.student_1).count()
        self.assertEqual(enrollment_count, 1)

    def test_cannot_issue_unapproved_certificate(self):
        """Certificates cannot be issued directly from DRAFT or SUBMITTED status."""
        cert = CertificateService.create_certificate_request(
            student=self.student_1,
            certificate_type='TRANSFER',
            requested_by=self.user_registrar,
            destination_school='Mizan High School',
            reason='Relocation'
        )
        # Attempt to issue draft
        with self.assertRaises(ValidationError):
            CertificateService.issue_certificate(cert, issued_by=self.user_admin)

    def test_rejection_workflow_with_mandatory_justification(self):
        """Principal rejecting a certificate requires justification and sets REJECTED status."""
        cert = CertificateService.create_certificate_request(
            student=self.student_1,
            certificate_type='TRANSFER',
            requested_by=self.user_registrar,
            destination_school='Metu High School',
            reason='Relocation'
        )
        CertificateService.submit_certificate(cert, submitted_by=self.user_registrar)

        # Reject without reason fails
        with self.assertRaises(ValidationError):
            CertificateService.reject_certificate(cert, rejected_by=self.user_principal, reason='')

        # Reject with reason succeeds
        cert = CertificateService.reject_certificate(
            cert,
            rejected_by=self.user_principal,
            reason='Library books not returned. Clearance incomplete.'
        )
        self.assertEqual(cert.status, 'REJECTED')
        self.assertEqual(cert.rejection_reason, 'Library books not returned. Clearance incomplete.')

    def test_revocation_workflow_with_mandatory_justification(self):
        """Revoking an issued certificate requires reason, marks REVOKED, and keeps record."""
        cert = CertificateService.create_certificate_request(
            student=self.student_1,
            certificate_type='TRANSFER',
            requested_by=self.user_registrar,
            destination_school='Bonga Secondary School',
            reason='Relocation'
        )
        CertificateService.submit_certificate(cert, submitted_by=self.user_registrar)
        CertificateService.approve_certificate(cert, approved_by=self.user_principal)
        CertificateService.issue_certificate(cert, issued_by=self.user_registrar)

        # Revoke without reason fails
        with self.assertRaises(ValidationError):
            CertificateService.revoke_certificate(cert, revoked_by=self.user_principal, reason='')

        # Revoke with reason succeeds
        cert = CertificateService.revoke_certificate(
            cert,
            revoked_by=self.user_principal,
            reason='Issued under clerical error; student remains enrolled.'
        )
        self.assertEqual(cert.status, 'REVOKED')
        self.assertEqual(cert.revoked_by, self.user_principal)
        self.assertIsNotNone(cert.revoked_at)
        self.assertEqual(cert.revocation_reason, 'Issued under clerical error; student remains enrolled.')

    # -------------------------------------------------------------------------
    # 3. RBAC Enforcement Tests
    # -------------------------------------------------------------------------
    def test_teacher_cannot_approve_or_reject_certificates(self):
        """Teachers must be prohibited from approving or rejecting certificate requests (RBAC)."""
        cert = CertificateService.create_certificate_request(
            student=self.student_1,
            certificate_type='TRANSFER',
            requested_by=self.user_registrar,
            destination_school='Tepi Secondary School',
            reason='Relocation'
        )
        CertificateService.submit_certificate(cert, submitted_by=self.user_registrar)

        # Teacher attempt via service layer
        with self.assertRaises(PermissionDenied):
            CertificateService.approve_certificate(cert, approved_by=self.user_teacher)

        with self.assertRaises(PermissionDenied):
            CertificateService.reject_certificate(cert, rejected_by=self.user_teacher, reason='No permission')

        # Teacher attempt via HTTP POST
        self.client.login(username='teacher_step23', password='Password123!')
        response = self.client.post(reverse('certificate_approve', args=[cert.id]), {
            'action': 'APPROVE',
            'remarks': 'Unauthorized approval attempt'
        })
        self.assertEqual(response.status_code, 403)

    def test_principal_can_approve_via_http(self):
        """Principal has authorized permission to approve certificates via web interface."""
        cert = CertificateService.create_certificate_request(
            student=self.student_1,
            certificate_type='TRANSFER',
            requested_by=self.user_registrar,
            destination_school='Tepi Secondary School',
            reason='Relocation'
        )
        CertificateService.submit_certificate(cert, submitted_by=self.user_registrar)

        self.client.login(username='principal_step23', password='Password123!')
        response = self.client.post(reverse('certificate_approve', args=[cert.id]), {
            'action': 'APPROVE',
            'remarks': 'Approved by principal.'
        })
        self.assertEqual(response.status_code, 302)
        cert.refresh_from_db()
        self.assertEqual(cert.status, 'APPROVED')

    # -------------------------------------------------------------------------
    # 4. Sequential Institutional Reference Numbering Tests
    # -------------------------------------------------------------------------
    def test_sequential_reference_number_generation(self):
        """Transfer certificates format MSS-TC-YYYY-XXXX and Leaving MSS-LC-YYYY-XXXX sequentially."""
        current_year = date.today().year

        num1 = CertificateService.generate_certificate_number('TRANSFER')
        self.assertEqual(num1, f'MSS-TC-{current_year}-0001')

        # Assign num1 to a certificate in DB
        cert1 = CertificateService.create_certificate_request(
            student=self.student_1,
            certificate_type='TRANSFER',
            requested_by=self.user_registrar,
            destination_school='Gore High School',
            reason='Relocation'
        )
        cert1.certificate_number = num1
        cert1.status = 'ISSUED'
        cert1.save()

        # Next transfer number should be 0002
        num2 = CertificateService.generate_certificate_number('TRANSFER')
        self.assertEqual(num2, f'MSS-TC-{current_year}-0002')

        # Leaving certificate numbering has separate sequence
        num_leaving = CertificateService.generate_certificate_number('LEAVING')
        self.assertEqual(num_leaving, f'MSS-LC-{current_year}-0001')

    # -------------------------------------------------------------------------
    # 5. Dual Calendar Date Formatting Tests
    # -------------------------------------------------------------------------
    def test_dual_calendar_date_formatting(self):
        """Verify format_dual_date produces clear English Gregorian date with Ethiopian calendar subtitle."""
        test_date = date(2023, 10, 15)
        formatted = CertificateService.format_dual_date(test_date)
        self.assertIn('Oct 15, 2023', formatted)
        self.assertIn('E.C.', formatted)

    # -------------------------------------------------------------------------
    # 6. ReportLab A4 English-Only PDF Generation Tests
    # -------------------------------------------------------------------------
    def test_pdf_generation_for_draft_and_issued_certificates(self):
        """Generate PDF for draft (watermarked) and issued certificate; verify valid PDF bytes."""
        cert = CertificateService.create_certificate_request(
            student=self.student_1,
            certificate_type='TRANSFER',
            requested_by=self.user_registrar,
            destination_school='Bedele Secondary School',
            reason='Relocation',
            academic_standing='Eligible for Grade 11',
            conduct='Good'
        )

        # PDF for DRAFT certificate
        pdf_draft = CertificateService.export_certificate_pdf(cert)
        self.assertEqual(pdf_draft.status_code, 200)
        self.assertEqual(pdf_draft['Content-Type'], 'application/pdf')
        self.assertTrue(pdf_draft.content.startswith(b'%PDF-'))
        self.assertGreater(len(pdf_draft.content), 1000)

        # Progress to ISSUED
        CertificateService.submit_certificate(cert, submitted_by=self.user_registrar)
        CertificateService.approve_certificate(cert, approved_by=self.user_principal)
        CertificateService.issue_certificate(cert, issued_by=self.user_registrar)

        # PDF for ISSUED certificate
        pdf_issued = CertificateService.export_certificate_pdf(cert)
        self.assertEqual(pdf_issued.status_code, 200)
        self.assertEqual(pdf_issued['Content-Type'], 'application/pdf')
        self.assertTrue(pdf_issued.content.startswith(b'%PDF-'))
        self.assertGreater(len(pdf_issued.content), 1000)

    # -------------------------------------------------------------------------
    # 7. Internal Verification Portal Tests
    # -------------------------------------------------------------------------
    def test_verification_portal_requires_authentication(self):
        """Unauthenticated requests to verification portal must be redirected to login (Zero PII leakage)."""
        response = self.client.get(reverse('certificate_verify'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_verification_portal_search_by_reference_number_and_uuid(self):
        """Authenticated staff can verify issued certificate by reference number or UUID."""
        cert = CertificateService.create_certificate_request(
            student=self.student_1,
            certificate_type='TRANSFER',
            requested_by=self.user_registrar,
            destination_school='Jimma High School',
            reason='Transfer'
        )
        CertificateService.submit_certificate(cert, submitted_by=self.user_registrar)
        CertificateService.approve_certificate(cert, approved_by=self.user_principal)
        CertificateService.issue_certificate(cert, issued_by=self.user_registrar)

        self.client.login(username='registrar_step23', password='Password123!')

        # 1. Search by reference number
        response = self.client.get(reverse('certificate_verify'), {'query': cert.certificate_number})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Authentic &amp; Valid Certificate')
        self.assertContains(response, cert.student.get_full_name())
        self.assertContains(response, cert.certificate_number)

        # 2. Search by UUID
        response_uuid = self.client.get(reverse('certificate_verify'), {'query': str(cert.certificate_uuid)})
        self.assertEqual(response_uuid.status_code, 200)
        self.assertContains(response_uuid, 'Authentic &amp; Valid Certificate')

        # 3. Search for non-existent reference number
        response_none = self.client.get(reverse('certificate_verify'), {'query': 'MSS-TC-9999-9999'})
        self.assertEqual(response_none.status_code, 200)
        self.assertContains(response_none, 'No Matching Certificate Record Found')

    def test_verification_portal_displays_revocation_notice(self):
        """Verification of a revoked certificate highlights the revocation banner and justification."""
        cert = CertificateService.create_certificate_request(
            student=self.student_1,
            certificate_type='TRANSFER',
            requested_by=self.user_registrar,
            destination_school='Aman High School',
            reason='Transfer'
        )
        CertificateService.submit_certificate(cert, submitted_by=self.user_registrar)
        CertificateService.approve_certificate(cert, approved_by=self.user_principal)
        CertificateService.issue_certificate(cert, issued_by=self.user_registrar)
        CertificateService.revoke_certificate(cert, revoked_by=self.user_principal, reason='Student cancelled transfer request.')

        self.client.login(username='admin_step23', password='Password123!')
        response = self.client.get(reverse('certificate_verify'), {'query': cert.certificate_number})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Revoked Certificate')
        self.assertContains(response, 'Student cancelled transfer request.')

    # -------------------------------------------------------------------------
    # 8. Web Views & Hub Functionality Tests
    # -------------------------------------------------------------------------
    def test_certificate_hub_view(self):
        """Verify the Certificate Management Hub loads KPI cards and search filters."""
        self.client.login(username='registrar_step23', password='Password123!')
        response = self.client.get(reverse('certificate_hub'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Transfer & Leaving Certificates')
        self.assertContains(response, 'New Certificate Request')

    def test_certificate_preview_view(self):
        """Verify the Certificate Preview page renders certificate particulars."""
        cert = CertificateService.create_certificate_request(
            student=self.student_1,
            certificate_type='TRANSFER',
            requested_by=self.user_registrar,
            destination_school='Jimma High School',
            reason='Transfer'
        )
        self.client.login(username='registrar_step23', password='Password123!')
        response = self.client.get(reverse('certificate_preview', args=[cert.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Official Student Transfer Certificate')
        self.assertContains(response, self.student_1.get_full_name())
