"""
Service layer for Student Promotion, Academic History, Graduation, and Status Tracking.
Implements multi-tier approval workflows, transaction-safe batch processing,
and PDF/Excel document generation.
"""

from decimal import Decimal
import io
from django.db import transaction, models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.http import HttpResponse

from academics.models import AcademicYear, Grade, Stream, ClassOffering
from students.models import Student, StudentEnrollment
from examinations.models import Examination, ExamSubject
from results.models import Mark, StudentResultSummary
from attendance.models import AttendanceRecord
from core.models import AuditLog

from promotion.models import (
    PromotionCriteria,
    PromotionBatch,
    PromotionRecord,
    GraduationRecord,
    StudentStatusHistory
)


class PromotionAuditHelper:
    """Helper to record promotion events in the core AuditLog."""
    @staticmethod
    def log(request, action, resource_type, resource_id, details=None):
        user = getattr(request, 'user', None) if request else None
        ip_addr = request.META.get('REMOTE_ADDR') if request else None
        AuditLog.objects.create(
            actor=user if user and user.is_authenticated else None,
            action=action,
            entity_name=resource_type,
            record_id=str(resource_id),
            changes_json=details or {},
            ip_address=ip_addr
        )


class PromotionAssessmentService:
    """
    Evaluates individual student academic performance and attendance
    against configurable PromotionCriteria to generate objective recommendations.
    Never enforces automatic promotion; output is strictly for human review.
    """

    @classmethod
    def get_active_criteria(cls):
        criteria = PromotionCriteria.objects.filter(is_default=True, is_active=True).first()
        if not criteria:
            criteria = PromotionCriteria.objects.filter(is_active=True).first()
        if not criteria:
            criteria = PromotionCriteria.objects.create(
                name="Default Secondary Promotion Policy",
                code="DEF-PROM",
                minimum_average=Decimal("50.00"),
                max_failing_subjects=2,
                minimum_attendance_percentage=Decimal("75.00"),
                is_active=True,
                is_default=True
            )
        return criteria

    @classmethod
    def assess_student_eligibility(cls, student_enrollment, criteria=None):
        """
        Gathers examination averages, failing subjects count, attendance percentage,
        and incomplete flags for a student enrollment.
        """
        if not criteria:
            criteria = cls.get_active_criteria()

        student = student_enrollment.student
        academic_year = student_enrollment.academic_year
        grade = student_enrollment.class_offering.grade

        # 1. Examination Performance
        summaries = StudentResultSummary.objects.filter(
            student_enrollment=student_enrollment,
            examination__academic_year=academic_year
        )

        average_mark = Decimal("0.00")
        has_incomplete = False
        failing_subjects_count = 0

        if summaries.exists():
            avg_list = [s.average_mark for s in summaries if s.average_mark is not None]
            if avg_list:
                average_mark = round(sum(avg_list) / Decimal(len(avg_list)), 2)
            has_incomplete = summaries.filter(is_complete=False).exists()
        else:
            has_incomplete = True

        # Check failing marks across exam subjects
        failing_marks = Mark.objects.filter(
            student_enrollment=student_enrollment,
            exam_subject__examination__academic_year=academic_year,
            is_absent=False,
            marks_obtained__isnull=False
        ).select_related('exam_subject')

        # Collect unique subjects where student scored below pass marks
        failing_subject_ids = set()
        for m in failing_marks:
            if not m.is_passing:
                failing_subject_ids.add(m.exam_subject.subject_id)
        failing_subjects_count = len(failing_subject_ids)

        # 2. Attendance Summary
        attendance_records = AttendanceRecord.objects.filter(
            student_enrollment=student_enrollment,
            attendance_session__class_offering__academic_year=academic_year
        )
        total_sessions = attendance_records.count()
        present_sessions = attendance_records.filter(status__in=['PRESENT', 'LATE']).count()
        attendance_percentage = Decimal("100.00")
        if total_sessions > 0:
            attendance_percentage = round((Decimal(present_sessions) / Decimal(total_sessions)) * Decimal(100), 2)

        # 3. Generate Algorithmic Recommendation
        # Grade 12 special case: Graduation
        if grade.level == 12:
            if average_mark >= criteria.minimum_average and failing_subjects_count == 0 and not has_incomplete:
                recommended = 'GRADUATED'
            elif has_incomplete:
                recommended = 'PENDING'
            else:
                recommended = 'REPEATED'
        else:
            # Grades 9-11
            attendance_ok = True
            if criteria.minimum_attendance_percentage:
                attendance_ok = (attendance_percentage >= criteria.minimum_attendance_percentage)

            if (average_mark >= criteria.minimum_average and
                    failing_subjects_count <= criteria.max_failing_subjects and
                    attendance_ok and not has_incomplete):
                recommended = 'PROMOTED'
            elif has_incomplete:
                recommended = 'PENDING'
            elif average_mark < criteria.minimum_average or failing_subjects_count > criteria.max_failing_subjects:
                recommended = 'REPEATED'
            else:
                recommended = 'PENDING'

        return {
            'academic_average': average_mark,
            'failing_subjects_count': failing_subjects_count,
            'attendance_percentage': attendance_percentage,
            'has_incomplete': has_incomplete,
            'recommended_outcome': recommended,
            'criteria': criteria,
        }


class PromotionBatchService:
    """Manages batch preparation, candidate assessment population, and record editing."""

    @classmethod
    def get_next_grade(cls, current_grade):
        """Identifies target subsequent grade (e.g. 9 -> 10, 10 -> 11, 11 -> 12, 12 -> None)."""
        target_level = current_grade.level + 1
        return Grade.objects.filter(level=target_level, is_active=True).first()

    @classmethod
    def create_batch(cls, name, academic_year, target_academic_year, grade, criteria=None, user=None, request=None):
        """
        Creates a promotion batch for a specific grade cohort and prepares
        candidate records with assessment recommendations.
        """
        if academic_year == target_academic_year:
            raise ValidationError("Target academic year must be different from source academic year.")

        if target_academic_year.start_date <= academic_year.start_date:
            raise ValidationError("Target academic year must start after the source academic year.")

        if not criteria:
            criteria = PromotionAssessmentService.get_active_criteria()

        next_grade = cls.get_next_grade(grade)

        with transaction.atomic():
            batch = PromotionBatch.objects.create(
                name=name,
                academic_year=academic_year,
                target_academic_year=target_academic_year,
                grade=grade,
                promotion_criteria=criteria,
                created_by=user,
                status='DRAFT'
            )

            # Query active student enrollments for this grade and academic year
            enrollments = StudentEnrollment.objects.filter(
                academic_year=academic_year,
                class_offering__grade=grade,
                status='ACTIVE'
            ).select_related('student', 'class_offering__section', 'class_offering__stream')

            for enr in enrollments:
                assessment = PromotionAssessmentService.assess_student_eligibility(enr, criteria)

                # Proposed next grade: if recommended to repeat, stays same grade; if promoted, next_grade; if graduated, None
                proposed_grade = next_grade if assessment['recommended_outcome'] == 'PROMOTED' else (grade if assessment['recommended_outcome'] == 'REPEATED' else None)

                # Attempt to find a matching class offering in target year if available
                matching_offering = ClassOffering.objects.filter(
                    academic_year=target_academic_year,
                    grade=proposed_grade,
                    section=enr.class_offering.section,
                    stream=enr.class_offering.stream
                ).first() if proposed_grade else None

                PromotionRecord.objects.create(
                    batch=batch,
                    student_enrollment=enr,
                    student=enr.student,
                    previous_academic_year=academic_year,
                    next_academic_year=target_academic_year,
                    previous_grade=grade,
                    next_grade=proposed_grade,
                    previous_class_offering=enr.class_offering,
                    next_class_offering=matching_offering,
                    recommended_outcome=assessment['recommended_outcome'],
                    final_outcome=assessment['recommended_outcome'],
                    decision_status='PENDING',
                    academic_average=assessment['academic_average'],
                    total_failing_subjects=assessment['failing_subjects_count'],
                    attendance_percentage=assessment['attendance_percentage'],
                    has_incomplete_results=assessment['has_incomplete'],
                )

            PromotionAuditHelper.log(
                request,
                'CREATE',
                'PromotionBatch',
                batch.id,
                {
                    'name': batch.name,
                    'academic_year': academic_year.code,
                    'target_academic_year': target_academic_year.code,
                    'grade': grade.name,
                    'candidates': enrollments.count()
                }
            )

        return batch

    @classmethod
    def update_record_outcome(cls, record_id, final_outcome, next_class_offering_id=None, remarks='', user=None, request=None):
        """Allows authorized staff to adjust candidate proposed outcome or class offering."""
        record = PromotionRecord.objects.select_related('batch', 'previous_grade').get(pk=record_id)
        if record.batch.status in ['APPROVED', 'FINALIZED']:
            raise ValidationError("Cannot modify candidates in an approved or finalized batch.")

        next_offering = None
        if next_class_offering_id:
            next_offering = ClassOffering.objects.filter(pk=next_class_offering_id).first()

        next_grade = record.next_grade
        if final_outcome == 'PROMOTED':
            next_grade = cls.get_next_grade(record.previous_grade)
        elif final_outcome == 'REPEATED':
            next_grade = record.previous_grade
        elif final_outcome in ['GRADUATED', 'TRANSFERRED', 'WITHDRAWN']:
            next_grade = None
            next_offering = None

        record.final_outcome = final_outcome
        record.next_grade = next_grade
        record.next_class_offering = next_offering
        record.remarks = remarks
        record.save(update_fields=['final_outcome', 'next_grade', 'next_class_offering', 'remarks', 'updated_at'])

        PromotionAuditHelper.log(
            request,
            'UPDATE',
            'PromotionRecord',
            record.id,
            {'outcome': final_outcome, 'remarks': remarks}
        )
        return record


class PromotionApprovalService:
    """
    Handles the multi-tier review workflow and transaction-safe finalization.
    Guarantees atomic execution and rollback on failure.
    """

    @classmethod
    def submit_for_review(cls, batch, user=None, request=None):
        if batch.status not in ['DRAFT', 'REJECTED']:
            raise ValidationError(f"Batch cannot be submitted from status '{batch.status}'.")

        batch.status = 'SUBMITTED'
        batch.save(update_fields=['status', 'updated_at'])

        PromotionAuditHelper.log(
            request,
            'SUBMIT',
            'PromotionBatch',
            batch.id,
            {'action': 'SUBMIT_FOR_REVIEW'}
        )
        return batch

    @classmethod
    def review_batch(cls, batch, decision, reviewer_user, comments='', request=None):
        """
        Decision: 'APPROVED' or 'REJECTED'.
        """
        if decision not in ['APPROVED', 'REJECTED']:
            raise ValidationError("Invalid review decision.")

        with transaction.atomic():
            if decision == 'APPROVED':
                batch.status = 'APPROVED'
                batch.approved_by = reviewer_user
                batch.approval_date = timezone.now()
                batch.approval_remarks = comments
                batch.records.update(decision_status='APPROVED')
            else:
                batch.status = 'REJECTED'
                batch.approval_remarks = comments
                batch.records.update(decision_status='REJECTED')

            batch.save(update_fields=['status', 'approved_by', 'approval_date', 'approval_remarks', 'updated_at'])

            PromotionAuditHelper.log(
                request,
                'REVIEW',
                'PromotionBatch',
                batch.id,
                {'decision': decision, 'comments': comments}
            )
        return batch

    @classmethod
    def finalize_promotions(cls, batch, user=None, request=None):
        """
        Executes atomic batch finalization:
        - Closes old enrollments as 'COMPLETED'
        - Creates new StudentEnrollment for Promoted and Repeated students
        - Records GraduationRecord for Graduated students
        - Records StudentStatusHistory for Transfers and Withdrawals
        - Prevents duplicate next-year enrollments
        Rolls back completely if any error occurs.
        """
        if batch.status != 'APPROVED':
            raise ValidationError("Only approved promotion batches can be finalized.")

        target_year = batch.target_academic_year
        if target_year.is_closed:
            raise ValidationError(f"Cannot finalize promotion into closed academic year '{target_year.name}'.")

        promoted_count = 0
        repeated_count = 0
        graduated_count = 0
        transferred_count = 0
        withdrawn_count = 0

        with transaction.atomic():
            for rec in batch.records.select_related('student', 'student_enrollment', 'previous_grade', 'next_grade', 'next_class_offering'):
                old_enr = rec.student_enrollment
                student = rec.student
                outcome = rec.final_outcome

                # Check for duplicate target enrollment
                already_enrolled = StudentEnrollment.objects.filter(
                    student=student,
                    academic_year=target_year
                ).exists()

                if already_enrolled and outcome in ['PROMOTED', 'REPEATED']:
                    raise ValidationError(
                        f"Student {student.admission_number} ({student.full_name}) is already enrolled in {target_year.name}. "
                        "Duplicate enrollment prevented."
                    )

                if outcome == 'PROMOTED':
                    dest_offering = rec.next_class_offering
                    if not dest_offering:
                        dest_offering = ClassOffering.objects.filter(
                            academic_year=target_year,
                            grade=rec.next_grade
                        ).first()

                    if not dest_offering:
                        raise ValidationError(
                            f"No valid class offering found in {target_year.name} for promoted Grade {rec.next_grade.name}. "
                            "Please configure target classes first."
                        )

                    # Update previous enrollment status
                    old_enr.status = 'PROMOTED'
                    old_enr.save(update_fields=['status'])

                    # Create new enrollment
                    new_enr = StudentEnrollment.objects.create(
                        student=student,
                        academic_year=target_year,
                        class_offering=dest_offering,
                        status='ACTIVE'
                    )

                    rec.new_enrollment = new_enr
                    rec.is_enrolled_in_next_year = True
                    rec.decision_status = 'FINALIZED'
                    rec.save(update_fields=['new_enrollment', 'is_enrolled_in_next_year', 'decision_status', 'updated_at'])
                    promoted_count += 1

                elif outcome == 'REPEATED':
                    repeat_offering = rec.next_class_offering
                    if not repeat_offering:
                        repeat_offering = ClassOffering.objects.filter(
                            academic_year=target_year,
                            grade=rec.previous_grade
                        ).first()

                    if not repeat_offering:
                        raise ValidationError(
                            f"No valid class offering found in {target_year.name} for repeating Grade {rec.previous_grade.name}."
                        )

                    old_enr.status = 'RETAINED'
                    old_enr.save(update_fields=['status'])

                    new_enr = StudentEnrollment.objects.create(
                        student=student,
                        academic_year=target_year,
                        class_offering=repeat_offering,
                        status='ACTIVE'
                    )

                    rec.new_enrollment = new_enr
                    rec.is_enrolled_in_next_year = True
                    rec.decision_status = 'FINALIZED'
                    rec.save(update_fields=['new_enrollment', 'is_enrolled_in_next_year', 'decision_status', 'updated_at'])
                    repeated_count += 1

                elif outcome == 'GRADUATED':
                    old_enr.status = 'PROMOTED'
                    old_enr.save(update_fields=['status'])

                    student.status = 'GRADUATED'
                    student.save(update_fields=['status'])

                    GraduationRecord.objects.update_or_create(
                        student=student,
                        academic_year=batch.academic_year,
                        defaults={
                            'grade': rec.previous_grade,
                            'stream': old_enr.class_offering.stream,
                            'graduation_date': timezone.now().date(),
                            'status': 'GRADUATED',
                            'cumulative_average': rec.academic_average,
                            'approved_by': user or batch.approved_by,
                            'remarks': f"Graduated via Batch '{batch.name}'"
                        }
                    )

                    StudentStatusHistory.objects.create(
                        student=student,
                        status_type='GRADUATION',
                        effective_date=timezone.now().date(),
                        reason="Successfully completed secondary education curriculum (Grade 12).",
                        authorized_by=user or batch.approved_by,
                        previous_status='ACTIVE',
                        new_status='GRADUATED'
                    )

                    rec.decision_status = 'FINALIZED'
                    rec.save(update_fields=['decision_status', 'updated_at'])
                    graduated_count += 1

                elif outcome == 'TRANSFERRED':
                    old_enr.status = 'WITHDRAWN'
                    old_enr.save(update_fields=['status'])

                    student.status = 'TRANSFERRED'
                    student.save(update_fields=['status'])

                    StudentStatusHistory.objects.create(
                        student=student,
                        status_type='TRANSFER_OUT',
                        effective_date=timezone.now().date(),
                        reason=rec.remarks or "Transferred to another school.",
                        authorized_by=user or batch.approved_by,
                        previous_status='ACTIVE',
                        new_status='TRANSFERRED'
                    )
                    rec.decision_status = 'FINALIZED'
                    rec.save(update_fields=['decision_status', 'updated_at'])
                    transferred_count += 1

                elif outcome == 'WITHDRAWN':
                    old_enr.status = 'WITHDRAWN'
                    old_enr.save(update_fields=['status'])

                    student.status = 'WITHDRAWN'
                    student.save(update_fields=['status'])

                    StudentStatusHistory.objects.create(
                        student=student,
                        status_type='WITHDRAWAL',
                        effective_date=timezone.now().date(),
                        reason=rec.remarks or "Withdrawn from school.",
                        authorized_by=user or batch.approved_by,
                        previous_status='ACTIVE',
                        new_status='WITHDRAWN'
                    )
                    rec.decision_status = 'FINALIZED'
                    rec.save(update_fields=['decision_status', 'updated_at'])
                    withdrawn_count += 1

            batch.status = 'FINALIZED'
            batch.finalized_at = timezone.now()
            batch.save(update_fields=['status', 'finalized_at', 'updated_at'])

            PromotionAuditHelper.log(
                request,
                'FINALIZE',
                'PromotionBatch',
                batch.id,
                {
                    'promoted': promoted_count,
                    'repeated': repeated_count,
                    'graduated': graduated_count,
                    'transferred': transferred_count,
                    'withdrawn': withdrawn_count
                }
            )

        return {
            'promoted': promoted_count,
            'repeated': repeated_count,
            'graduated': graduated_count,
            'transferred': transferred_count,
            'withdrawn': withdrawn_count,
            'total': promoted_count + repeated_count + graduated_count + transferred_count + withdrawn_count
        }


class StudentAcademicHistoryService:
    """Assembles chronological timeline of academic achievements, examinations, and promotions."""

    @classmethod
    def get_student_academic_history(cls, student):
        enrollments = student.enrollments.select_related(
            'academic_year', 'class_offering__grade', 'class_offering__section', 'class_offering__stream'
        ).order_by('academic_year__start_date')

        history_rows = []
        for enr in enrollments:
            ay = enr.academic_year

            # Summaries for this enrollment
            summaries = StudentResultSummary.objects.filter(
                student_enrollment=enr
            ).select_related('examination', 'examination__exam_type')

            # Attendance for this enrollment
            att_records = AttendanceRecord.objects.filter(
                student_enrollment=enr,
                attendance_session__class_offering__academic_year=ay
            )
            att_total = att_records.count()
            att_present = att_records.filter(status__in=['PRESENT', 'LATE']).count()
            att_pct = round((Decimal(att_present) / Decimal(att_total)) * 100, 1) if att_total > 0 else None

            # Promotion outcome
            prom_rec = enr.academic_promotions.first()

            history_rows.append({
                'enrollment': enr,
                'academic_year': ay,
                'grade': enr.class_offering.grade,
                'section': enr.class_offering.section,
                'stream': enr.class_offering.stream,
                'class_offering': enr.class_offering,
                'is_repeating': enr.status == 'RETAINED',
                'status': enr.status,
                'summaries': summaries,
                'attendance_total': att_total,
                'attendance_present': att_present,
                'attendance_percentage': att_pct,
                'promotion_record': prom_rec,
            })

        status_changes = student.status_histories.select_related('authorized_by').order_by('-effective_date')
        graduation = getattr(student, 'graduation_records', None).first() if hasattr(student, 'graduation_records') else None

        return {
            'student': student,
            'history_rows': history_rows,
            'status_changes': status_changes,
            'graduation': graduation,
        }


class GraduationService:
    """Manages Grade 12 candidate certification and graduation registries."""

    @classmethod
    def get_graduation_candidates(cls, academic_year=None):
        if not academic_year:
            academic_year = AcademicYear.objects.filter(is_current=True).first()

        grade12 = Grade.objects.filter(level=12).first()
        if not grade12:
            return []

        enrollments = StudentEnrollment.objects.filter(
            academic_year=academic_year,
            class_offering__grade=grade12,
            status__in=['ACTIVE', 'PROMOTED']
        ).select_related('student', 'class_offering__section', 'class_offering__stream')

        records = []
        for enr in enrollments:
            grad_rec = GraduationRecord.objects.filter(student=enr.student, academic_year=academic_year).first()
            # Calculate overall average
            summaries = StudentResultSummary.objects.filter(student_enrollment=enr)
            avg = Decimal("0.00")
            if summaries.exists():
                scores = [s.average_mark for s in summaries if s.average_mark is not None]
                avg = round(sum(scores) / len(scores), 2) if scores else Decimal("0.00")

            records.append({
                'enrollment': enr,
                'student': enr.student,
                'stream': enr.class_offering.stream,
                'average': avg,
                'graduation_record': grad_rec,
                'is_approved': grad_rec and grad_rec.status in ['APPROVED', 'GRADUATED'],
            })
        return records


class PromotionReportService:
    """Generates official printable ReportLab PDFs and OpenPyXL Excel reports."""

    @classmethod
    def export_promotion_batch_pdf(cls, batch, filename="promotion_roster.pdf"):
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=14,
            leading=16,
            alignment=1,
            textColor=colors.HexColor('#1E3A8A')
        )
        sub_style = ParagraphStyle(
            'SubStyle',
            parent=styles['Normal'],
            fontSize=9,
            leading=12,
            alignment=1,
            textColor=colors.HexColor('#475569')
        )

        elements.append(Paragraph("MAJANG SECONDARY SCHOOL - GAMBELLA REGION, ETHIOPIA", title_style))
        elements.append(Paragraph(f"Official Promotion Roster: {batch.name}", title_style))
        elements.append(Paragraph(
            f"Source Year: {batch.academic_year.name} &bull; Target Year: {batch.target_academic_year.name} "
            f"&bull; Grade: {batch.grade.name} &bull; Status: {batch.get_status_display()}",
            sub_style
        ))
        elements.append(Spacer(1, 15))

        table_data = [
            ["#", "Adm No", "Student Full Name", "Section", "Avg %", "Fails", "Att %", "Recommended", "Final Outcome", "Next Class"]
        ]

        records = batch.records.select_related('student', 'previous_class_offering__section', 'next_class_offering__grade', 'next_class_offering__section').order_by('student__first_name')
        for idx, r in enumerate(records, start=1):
            next_class_str = f"{r.next_class_offering.grade.name}-{r.next_class_offering.section.name}" if r.next_class_offering else (r.next_grade.name if r.next_grade else "N/A")
            table_data.append([
                str(idx),
                r.student.admission_number,
                r.student.full_name,
                r.previous_class_offering.section.name,
                f"{r.academic_average}%" if r.academic_average is not None else "—",
                str(r.total_failing_subjects),
                f"{r.attendance_percentage}%" if r.attendance_percentage is not None else "—",
                r.get_recommended_outcome_display(),
                r.get_final_outcome_display(),
                next_class_str
            ])

        t = Table(table_data, colWidths=[25, 75, 160, 45, 50, 40, 50, 100, 100, 95])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 5),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('ALIGN', (2, 1), (2, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
            ('FONTSIZE', (0, 1), (-1, -1), 7.5),
        ]))
        elements.append(t)

        doc.build(elements)
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @classmethod
    def export_promotion_batch_excel(cls, batch, filename="promotion_roster.xlsx"):
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Promotion Roster"
        ws.views.sheetView[0].showGridLines = True

        # Header titles
        ws.merge_cells("A1:I1")
        ws["A1"] = "MAJANG SECONDARY SCHOOL - OFFICIAL STUDENT PROMOTION ROSTER"
        ws["A1"].font = Font(name="Calibri", size=13, bold=True, color="1E3A8A")
        ws["A1"].alignment = Alignment(horizontal="center")

        ws.merge_cells("A2:I2")
        ws["A2"] = f"Batch: {batch.name} | From: {batch.academic_year.name} To: {batch.target_academic_year.name} | Grade: {batch.grade.name} | Status: {batch.get_status_display()}"
        ws["A2"].font = Font(name="Calibri", size=10, italic=True)
        ws["A2"].alignment = Alignment(horizontal="center")

        headers = ["#", "Admission No", "Student Full Name", "Section", "Academic Avg (%)", "Failing Subjects", "Attendance (%)", "Proposed Outcome", "Assigned Next Class"]
        ws.append([])
        ws.append(headers)

        header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        thin_border = Border(
            left=Side(style='thin', color='CBD5E1'),
            right=Side(style='thin', color='CBD5E1'),
            top=Side(style='thin', color='CBD5E1'),
            bottom=Side(style='thin', color='CBD5E1')
        )

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=4, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")

        records = batch.records.select_related('student', 'previous_class_offering__section', 'next_class_offering__grade', 'next_class_offering__section').order_by('student__first_name')
        for idx, r in enumerate(records, start=1):
            next_class_str = f"{r.next_class_offering.grade.name}-{r.next_class_offering.section.name}" if r.next_class_offering else (r.next_grade.name if r.next_grade else "N/A")
            row = [
                idx,
                r.student.admission_number,
                r.student.full_name,
                r.previous_class_offering.section.name,
                float(r.academic_average) if r.academic_average is not None else "",
                r.total_failing_subjects,
                float(r.attendance_percentage) if r.attendance_percentage is not None else "",
                r.get_final_outcome_display(),
                next_class_str
            ]
            ws.append(row)
            curr_row = ws.max_row
            for col_idx in range(1, len(headers) + 1):
                c = ws.cell(row=curr_row, column=col_idx)
                c.border = thin_border
                c.font = Font(name="Calibri", size=10)
                if col_idx in [1, 2, 4, 6, 8, 9]:
                    c.alignment = Alignment(horizontal="center")

        # Auto-adjust column widths
        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)

        response = HttpResponse(
            buffer.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
