"""
Results Management Service Layer for SSMS.

Handles marks recording, bulk evaluation, verification workflow,
decimal-safe result calculations, grading boundaries, and report card generation.
"""

import io
import csv
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum, Avg, Count, Max, Min, Q
from django.core.exceptions import ValidationError, PermissionDenied
from django.http import HttpResponse
from django.utils import timezone

from academics.models import AcademicYear, Grade, Subject, ClassOffering
from students.models import Student, StudentEnrollment
from teachers.models import Teacher, TeacherAssignment
from core.models import AuditLog
from examinations.models import Examination, ExamSubject
from results.models import GradingScale, GradingRange, Mark, ResultApproval, StudentResultSummary


def sanitize_csv_cell(val):
    """
    Prevents CSV formula injection (OWASP / CWE-1236).
    If a string value starts with '=', '+', '-', '@', '\t', or '\r',
    it is prepended with a single quote to force spreadsheet programs
    (Excel, Calc) to treat it as a literal string.
    """
    if val is None:
        return ""
    s = str(val)
    if s and s[0] in ('=', '+', '-', '@', '\t', '\r'):
        return "'" + s
    return s


class ResultAuditHelper:
    """Centralized audit logger for examination result operations."""


    @staticmethod
    def log(request, action, entity_name, record_id, changes=None):
        try:
            actor = getattr(request, 'user', None) if request and request.user.is_authenticated else None
            ip = None
            if request:
                x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
                ip = x_forwarded.split(',')[0].strip() if x_forwarded else request.META.get('REMOTE_ADDR')

            AuditLog.objects.create(
                actor=actor,
                action=action,
                entity_name=entity_name,
                record_id=str(record_id),
                ip_address=ip,
                changes_json=changes or {}
            )
        except Exception:
            pass


class MarksService:
    """Manages individual and bulk student marks entry and submission workflow."""

    @classmethod
    def record_bulk_marks(cls, exam_subject, marks_data, entered_by_user=None, request=None):
        """
        Takes exam_subject and a list of mark dicts:
        [{'enrollment_id': int, 'marks_obtained': Decimal|None, 'is_absent': bool, 'is_excused': bool, 'remarks': str}, ...]
        """
        if exam_subject.is_locked:
            raise ValidationError(
                f"Marks entry for '{exam_subject}' is locked because the examination or marks are already verified."
            )

        # Pre-fetch valid active enrollments for the exam subject's grade
        valid_enrollments = {
            enr.id: enr for enr in StudentEnrollment.objects.filter(
                class_offering__grade=exam_subject.grade,
                academic_year=exam_subject.examination.academic_year,
                status='ACTIVE'
            ).select_related('student', 'class_offering')
        }

        created_count = 0
        updated_count = 0

        with transaction.atomic():
            for row in marks_data:
                enr_id = row.get('enrollment_id')
                if enr_id not in valid_enrollments:
                    continue

                enrollment = valid_enrollments[enr_id]
                is_absent = bool(row.get('is_absent', False))
                is_excused = bool(row.get('is_excused', False))
                raw_score = row.get('marks_obtained')
                remarks = (row.get('remarks') or '').strip()

                score = None
                if not is_absent and raw_score is not None and str(raw_score).strip() != '':
                    try:
                        score = Decimal(str(raw_score))
                    except Exception:
                        score = None

                if score is not None:
                    if score < Decimal('0.00'):
                        raise ValidationError(f"Mark cannot be negative ({score}) for {enrollment.student.full_name}.")
                    if score > exam_subject.max_marks:
                        raise ValidationError(
                            f"Score ({score}) exceeds maximum allowed ({exam_subject.max_marks}) "
                            f"for student {enrollment.student.full_name}."
                        )

                mark, created = Mark.objects.update_or_create(
                    student_enrollment=enrollment,
                    exam_subject=exam_subject,
                    defaults={
                        'marks_obtained': score if not is_absent else None,
                        'is_absent': is_absent,
                        'is_excused': is_excused,
                        'remarks': remarks,
                        'entered_by': entered_by_user,
                        'status': 'DRAFT'
                    }
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

            # If subject was returned, reset to PENDING when teacher saves new edits
            if exam_subject.status == 'RETURNED':
                exam_subject.status = 'PENDING'
                exam_subject.save(update_fields=['status'])

            ResultAuditHelper.log(
                request,
                'UPDATE',
                'ExamSubject',
                exam_subject.id,
                {
                    'action': 'RECORD_MARKS',
                    'created': created_count,
                    'updated': updated_count,
                    'subject': exam_subject.subject.name
                }
            )

        return {'created': created_count, 'updated': updated_count}

    @classmethod
    def submit_marks_for_verification(cls, exam_subject, teacher_user=None, request=None):
        """Teacher formally submits entered marks to examination officer / registrar."""
        if exam_subject.is_locked:
            raise ValidationError("Cannot submit marks for a locked or verified examination subject.")

        teacher_profile = None
        if teacher_user:
            if hasattr(teacher_user, 'teacher_profile'):
                teacher_profile = teacher_user.teacher_profile
            elif teacher_user.__class__.__name__ == 'Teacher':
                teacher_profile = teacher_user

        with transaction.atomic():
            exam_subject.status = 'SUBMITTED'
            exam_subject.submitted_by = teacher_profile
            exam_subject.submitted_at = timezone.now()
            exam_subject.save(update_fields=['status', 'submitted_by', 'submitted_at'])

            # Advance all draft marks to SUBMITTED
            Mark.objects.filter(exam_subject=exam_subject).update(status='SUBMITTED')

            ResultAuditHelper.log(
                request,
                'UPDATE',
                'ExamSubject',
                exam_subject.id,
                {'action': 'SUBMIT_MARKS', 'status': 'SUBMITTED'}
            )
        return exam_subject

    # Alias for convenience
    submit_marks_for_review = submit_marks_for_verification

    @classmethod
    def review_and_verify_marks(cls, exam_subject, reviewer_user, decision, comments='', request=None):
        """
        Administrative review by Registrar, Principal, or Examination Officer.
        Decision: 'APPROVED' or 'RETURNED'.
        """
        if decision not in ('APPROVED', 'RETURNED'):
            raise ValidationError("Invalid review decision. Must be APPROVED or RETURNED.")

        with transaction.atomic():
            if decision == 'APPROVED':
                exam_subject.status = 'VERIFIED'
                exam_subject.verified_by = reviewer_user
                exam_subject.verified_at = timezone.now()
                exam_subject.verification_remarks = comments
                exam_subject.save(update_fields=['status', 'verified_by', 'verified_at', 'verification_remarks'])

                Mark.objects.filter(exam_subject=exam_subject).update(status='VERIFIED')

            elif decision == 'RETURNED':
                exam_subject.status = 'RETURNED'
                exam_subject.verification_remarks = comments
                exam_subject.save(update_fields=['status', 'verification_remarks'])

                Mark.objects.filter(exam_subject=exam_subject).update(status='RETURNED')

            ResultApproval.objects.create(
                exam_subject=exam_subject,
                reviewed_by=reviewer_user,
                decision=decision,
                comments=comments
            )

            ResultAuditHelper.log(
                request,
                'UPDATE',
                'ExamSubject',
                exam_subject.id,
                {'action': 'VERIFY_MARKS', 'decision': decision, 'comments': comments}
            )
        return exam_subject


class ResultCalculationService:
    """Computes decimal-safe weighted totals, class averages, and rankings."""

    @classmethod
    def calculate_examination_results(cls, examination, grading_scale=None, class_offering=None, request=None):
        """
        Aggregates marks for all students in the examination into StudentResultSummary records.
        Ranks students safely by average mark descending.
        """
        if not grading_scale:
            grading_scale = GradingScale.objects.filter(is_default=True).first()
            if not grading_scale:
                grading_scale = GradingScale.objects.first()

        exam_subjects = examination.exam_subjects.all().select_related('subject', 'grade')
        total_subjects_count = exam_subjects.count()

        enrollments_qs = StudentEnrollment.objects.filter(
            academic_year=examination.academic_year,
            status='ACTIVE'
        ).select_related('student', 'class_offering__grade', 'class_offering__section')

        if examination.grade:
            enrollments_qs = enrollments_qs.filter(class_offering__grade=examination.grade)
        if class_offering:
            enrollments_qs = enrollments_qs.filter(class_offering=class_offering)

        summaries = []

        with transaction.atomic():
            for enr in enrollments_qs:
                student_marks = Mark.objects.filter(
                    student_enrollment=enr,
                    exam_subject__examination=examination
                ).select_related('exam_subject')

                obtained_sum = Decimal('0.00')
                max_sum = Decimal('0.00')
                entered_count = 0
                passed_count = 0
                failed_count = 0

                for m in student_marks:
                    if not m.is_absent and m.marks_obtained is not None:
                        obtained_sum += m.marks_obtained
                        max_sum += m.exam_subject.max_marks
                        entered_count += 1
                        if m.is_passing:
                            passed_count += 1
                        else:
                            failed_count += 1
                    elif m.is_absent:
                        # Absent counts as evaluated 0 for calculation
                        max_sum += m.exam_subject.max_marks
                        entered_count += 1
                        failed_count += 1

                # Calculation percentage
                percentage = Decimal('0.00')
                if max_sum > Decimal('0.00'):
                    percentage = round((obtained_sum / max_sum) * Decimal('100.00'), 2)

                # Average mark per subject evaluated
                average_mark = Decimal('0.00')
                if entered_count > 0:
                    average_mark = round(obtained_sum / Decimal(str(entered_count)), 2)

                is_complete = (entered_count >= total_subjects_count) and (total_subjects_count > 0)

                grade_label = "—"
                grade_desc = ""
                if grading_scale and entered_count > 0:
                    gr = grading_scale.get_grade_for_score(float(percentage))
                    if gr:
                        grade_label = gr.grade_label
                        grade_desc = gr.description

                summary_status = 'PUBLISHED' if examination.is_published else 'PROVISIONAL'

                summary, _ = StudentResultSummary.objects.update_or_create(
                    student_enrollment=enr,
                    examination=examination,
                    defaults={
                        'total_obtained': obtained_sum,
                        'total_max': max_sum,
                        'average_mark': average_mark,
                        'percentage': percentage,
                        'overall_grade': grade_label,
                        'grade_description': grade_desc,
                        'subjects_passed': passed_count,
                        'subjects_failed': failed_count,
                        'total_subjects': total_subjects_count,
                        'is_complete': is_complete,
                        'status': summary_status,
                    }
                )
                summaries.append(summary)

            # Calculate Class Ranks per class offering
            classes_to_rank = set(s.student_enrollment.class_offering for s in summaries)
            for c_off in classes_to_rank:
                class_summaries = StudentResultSummary.objects.filter(
                    examination=examination,
                    student_enrollment__class_offering=c_off
                ).order_by('-average_mark', '-total_obtained')

                current_rank = 1
                for s in class_summaries:
                    s.rank = current_rank
                    s.save(update_fields=['rank'])
                    current_rank += 1

            ResultAuditHelper.log(
                request,
                'UPDATE',
                'Examination',
                examination.id,
                {'action': 'CALCULATE_RESULTS', 'students_processed': len(summaries)}
            )

        return summaries


class ReportCardService:
    """Produces structured report cards and formatted PDF / Excel documents."""

    @classmethod
    def get_report_card_data(cls, student_enrollment, examination, grading_scale=None):
        """
        Assembles verified academic marks, attendance records, promotion status,
        and Ethiopian/Gregorian calendar metadata for student report cards.
        Strictly ENGLISH-ONLY representation.
        """
        import os
        from datetime import date
        from django.utils import translation
        from core.utils.ethiopian_calendar import gregorian_to_ethiopian
        from attendance.services import AttendanceAnalyticsService
        from promotion.models import PromotionRecord

        # Enforce English locale during report card compilation
        with translation.override('en'):
            if not grading_scale:
                grading_scale = GradingScale.objects.filter(is_default=True).first()

            student = student_enrollment.student
            class_offering = student_enrollment.class_offering
            academic_year = examination.academic_year

            # 1. Summary Record (calculated by ResultCalculationService)
            summary = StudentResultSummary.objects.filter(
                student_enrollment=student_enrollment,
                examination=examination
            ).first()

            # 2. Verified Subject Marks
            marks_qs = Mark.objects.filter(
                student_enrollment=student_enrollment,
                exam_subject__examination=examination
            ).select_related(
                'exam_subject__subject',
                'exam_subject__grade',
                'exam_subject__stream'
            ).order_by('exam_subject__subject__name')

            subjects_data = []
            calc_total_obtained = Decimal('0.00')
            calc_total_max = Decimal('0.00')
            subjects_passed_cnt = 0
            subjects_failed_cnt = 0

            for m in marks_qs:
                g_item = None
                if grading_scale and m.percentage is not None:
                    g_item = grading_scale.get_grade_for_score(m.percentage)

                grade_label = g_item.grade_label if g_item else '—'
                grade_desc = g_item.description if g_item else ''

                if m.marks_obtained is not None and not m.is_absent:
                    calc_total_obtained += m.marks_obtained
                if m.exam_subject.max_marks:
                    calc_total_max += m.exam_subject.max_marks

                if m.is_passing:
                    subjects_passed_cnt += 1
                else:
                    subjects_failed_cnt += 1

                subjects_data.append({
                    'subject_name': m.exam_subject.subject.name,
                    'subject_code': m.exam_subject.subject.code,
                    'max_marks': m.exam_subject.max_marks,
                    'pass_marks': m.exam_subject.pass_marks,
                    'marks_obtained': m.marks_obtained,
                    'is_absent': m.is_absent,
                    'percentage': m.percentage,
                    'grade_label': grade_label,
                    'grade_description': grade_desc,
                    'is_passing': m.is_passing,
                    'remarks': m.remarks or '',
                })

            # 3. Overall Performance Numbers
            if summary:
                total_obtained = summary.total_obtained
                total_max = summary.total_max
                average_mark = summary.average_mark
                overall_pct = summary.percentage
                overall_grade = summary.overall_grade or '—'
                grade_description = summary.grade_description or ''
                rank = summary.rank
                is_pass = getattr(summary, 'is_passing', False) if summary else False
                standing = "Pass / Promoted in Good Standing" if is_pass else "Academic Warning"
                teacher_remarks = summary.teacher_remarks
                is_complete = summary.is_complete
            else:
                total_obtained = calc_total_obtained
                total_max = calc_total_max
                overall_pct = round((calc_total_obtained / calc_total_max * 100), 2) if calc_total_max > 0 else Decimal('0.00')
                average_mark = overall_pct
                g_item = grading_scale.get_grade_for_score(overall_pct) if grading_scale else None
                overall_grade = g_item.grade_label if g_item else '—'
                grade_description = g_item.description if g_item else ''
                rank = None
                standing = "Provisional / Pending Approval"
                teacher_remarks = ''
                is_complete = len(subjects_data) > 0

            # 4. Attendance Summary
            try:
                att_profile = AttendanceAnalyticsService.get_student_summary(student, academic_year=academic_year)
                attendance_summary = {
                    'total_sessions': att_profile.get('total_sessions', 0),
                    'present': att_profile.get('present', 0),
                    'absent': att_profile.get('absent', 0),
                    'late': att_profile.get('late', 0),
                    'excused': att_profile.get('excused', 0),
                    'rate': att_profile.get('rate', 0.0),
                }
            except Exception:
                attendance_summary = {
                    'total_sessions': 0, 'present': 0, 'absent': 0, 'late': 0, 'excused': 0, 'rate': 0.0
                }

            # 5. Promotion Status (only when officially approved)
            promo_rec = PromotionRecord.objects.filter(
                student=student,
                batch__academic_year=academic_year,
                decision_status__in=['APPROVED', 'FINALIZED']
            ).select_related('next_grade', 'batch').first()

            if promo_rec:
                promotion_info = {
                    'is_approved': True,
                    'status': promo_rec.get_final_outcome_display(),
                    'outcome_code': promo_rec.final_outcome,
                    'decision_status': promo_rec.get_decision_status_display(),
                    'next_grade': promo_rec.next_grade.name if promo_rec.next_grade else None,
                    'comments': getattr(promo_rec, 'remarks', '') or getattr(promo_rec, 'comments', '') or 'Official promotion decision confirmed by academic committee.',
                }
            else:
                promotion_info = {
                    'is_approved': False,
                    'status': 'Pending Official Committee Evaluation',
                    'outcome_code': 'PENDING',
                    'decision_status': 'In Progress / Pending End-of-Year Review',
                    'next_grade': None,
                    'comments': 'Official promotion outcome is evaluated and authorized at the end of the academic year.',
                }

            # 6. Calendar Dates (Ethiopian & Gregorian)
            today = date.today()
            eth_today = gregorian_to_ethiopian(today)
            issued_date_gc = today.strftime("%B %d, %Y")
            issued_date_ec = str(eth_today)
            issued_date_display = f"{issued_date_gc} G.C. ({issued_date_ec})"

            eth_year_display = academic_year.ethiopian_year_display
            academic_year_display = f"{academic_year.name} G.C. ({eth_year_display})"

            stream_name = class_offering.stream.name if (class_offering and class_offering.stream) else "General Secondary"

            logo_rel = os.path.join('static', 'images', 'school_logo.png')
            logo_abs = os.path.abspath(logo_rel)

            return {
                'student': student,
                'enrollment': student_enrollment,
                'class_offering': class_offering,
                'academic_year': academic_year,
                'academic_year_gc': academic_year.name,
                'academic_year_ec': eth_year_display,
                'academic_year_display': academic_year_display,
                'grade_name': class_offering.grade.name if class_offering else '—',
                'section_name': class_offering.section.name if class_offering else '—',
                'stream_name': stream_name,
                'examination': examination,
                'issued_date_gc': issued_date_gc,
                'issued_date_ec': issued_date_ec,
                'issued_date_display': issued_date_display,
                'summary': summary,
                'subjects': subjects_data,
                'grading_scale': grading_scale,
                'metrics': {
                    'total_obtained': total_obtained,
                    'total_max': total_max,
                    'average_mark': average_mark,
                    'percentage': overall_pct,
                    'overall_grade': overall_grade,
                    'grade_description': grade_description,
                    'rank': rank,
                    'standing': standing,
                    'subjects_passed': subjects_passed_cnt,
                    'subjects_failed': subjects_failed_cnt,
                    'total_subjects': len(subjects_data),
                    'is_complete': is_complete,
                    'teacher_remarks': teacher_remarks,
                },
                'attendance': attendance_summary,
                'promotion': promotion_info,
                'school_info': {
                    'name': 'METTI SECONDARY SCHOOL',
                    'system_title': 'Smart School Management and Academic Information System (SSMS)',
                    'location': 'Majang Zone, Gambella Region, Ethiopia',
                    'grades': 'Grades 9–12 &bull; Secondary Education',
                    'motto': 'Excellence in Academic Discipline and Ethical Character',
                    'logo_path': logo_abs if os.path.exists(logo_abs) else None,
                }
            }

    @classmethod
    def export_report_card_pdf(cls, data, filename="report_card.pdf"):
        """
        Generates an official, publication-grade, strictly ENGLISH-ONLY
        printable PDF student report card using ReportLab.
        """
        import os
        from reportlab.lib.pagesizes import letter, portrait
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image
        )
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=portrait(letter),
            rightMargin=28,
            leftMargin=28,
            topMargin=22,
            bottomMargin=22
        )
        elements = []
        styles = getSampleStyleSheet()

        # Typography Styles (Strictly English fonts: Helvetica & Helvetica-Bold)
        style_title = ParagraphStyle(
            'SchoolTitle',
            fontName='Helvetica-Bold',
            fontSize=13,
            leading=15,
            alignment=1,
            textColor=colors.HexColor('#1E3A8A')
        )
        style_sub = ParagraphStyle(
            'SchoolSub',
            fontName='Helvetica',
            fontSize=7.5,
            leading=9.5,
            alignment=1,
            textColor=colors.HexColor('#475569')
        )
        style_card_title = ParagraphStyle(
            'CardTitle',
            fontName='Helvetica-Bold',
            fontSize=9.5,
            leading=11,
            alignment=1,
            textColor=colors.HexColor('#0F172A')
        )
        style_cell = ParagraphStyle(
            'TableCell',
            fontName='Helvetica',
            fontSize=7,
            leading=8.5,
            textColor=colors.HexColor('#0F172A')
        )
        style_cell_bold = ParagraphStyle(
            'TableCellBold',
            fontName='Helvetica-Bold',
            fontSize=7,
            leading=8.5,
            textColor=colors.HexColor('#0F172A')
        )
        style_cell_center = ParagraphStyle(
            'TableCellCenter',
            fontName='Helvetica',
            fontSize=7,
            leading=8.5,
            alignment=1,
            textColor=colors.HexColor('#0F172A')
        )
        style_cell_pass = ParagraphStyle(
            'TableCellPass',
            fontName='Helvetica-Bold',
            fontSize=7,
            leading=8.5,
            alignment=1,
            textColor=colors.HexColor('#15803D')
        )
        style_cell_fail = ParagraphStyle(
            'TableCellFail',
            fontName='Helvetica-Bold',
            fontSize=7,
            leading=8.5,
            alignment=1,
            textColor=colors.HexColor('#B91C1C')
        )
        style_cell_absent = ParagraphStyle(
            'TableCellAbsent',
            fontName='Helvetica-Bold',
            fontSize=7,
            leading=8.5,
            alignment=1,
            textColor=colors.HexColor('#D97706')
        )
        style_box_title = ParagraphStyle(
            'BoxTitle',
            fontName='Helvetica-Bold',
            fontSize=7.5,
            leading=9,
            textColor=colors.HexColor('#1E3A8A')
        )
        style_sig = ParagraphStyle(
            'SigStyle',
            fontName='Helvetica',
            fontSize=7,
            leading=9,
            alignment=1,
            textColor=colors.HexColor('#1E293B')
        )

        st = data['student']
        enr = data['enrollment']
        exam = data['examination']
        metrics = data.get('metrics', {})

        # 1. School Header Banner with Official Emblem
        logo_path = data.get('school_info', {}).get('logo_path')
        if not logo_path or not os.path.exists(logo_path):
            logo_rel = os.path.join('static', 'images', 'school_logo.png')
            logo_path = os.path.abspath(logo_rel) if os.path.exists(logo_rel) else None

        header_cells = [
            [
                Image(logo_path, width=38, height=38) if logo_path else Paragraph('<b>SSMS</b>', style_cell_bold),
                [
                    Paragraph('METTI SECONDARY SCHOOL', style_title),
                    Paragraph('Smart School Management and Academic Information System (SSMS)', style_sub),
                    Paragraph('Majang Zone, Gambella Region, Ethiopia &bull; Grades 9–12 Secondary Education', style_sub),
                    Paragraph(f'OFFICIAL STUDENT ACADEMIC REPORT CARD — {exam.name.upper()}', style_card_title),
                ]
            ]
        ]
        header_table = Table(header_cells, colWidths=[42, 514])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ]))
        elements.append(header_table)
        elements.append(HRFlowable(width='100%', thickness=1.5, color=colors.HexColor('#1E3A8A'), spaceBefore=3, spaceAfter=5))

        # 2. Student & Academic Identification Box (3 Columns)
        meta_data = [
            [
                Paragraph(f'<b>Student Name:</b> {st.full_name}', style_cell),
                Paragraph(f"<b>Grade &amp; Section:</b> {data.get('grade_name', '—')} - Sec {data.get('section_name', '—')}", style_cell),
                Paragraph(f"<b>Academic Year:</b> {data.get('academic_year_display', '')}", style_cell),
            ],
            [
                Paragraph(f'<b>Admission No:</b> {st.admission_number}', style_cell),
                Paragraph(f"<b>Curriculum Stream:</b> {data.get('stream_name', 'General Secondary')}", style_cell),
                Paragraph(f'<b>Semester / Cycle:</b> {exam.get_semester_display()}', style_cell),
            ],
            [
                Paragraph(f'<b>Gender:</b> {st.get_gender_display()}', style_cell),
                Paragraph(f"<b>Class Rank:</b> #{metrics.get('rank', '—') if metrics.get('rank') else 'Unranked'}", style_cell),
                Paragraph(f"<b>Date Issued:</b> {data.get('issued_date_display', '')}", style_cell),
            ],
        ]
        meta_table = Table(meta_data, colWidths=[185, 185, 186])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ('PADDING', (0, 0), (-1, -1), 2.5),
        ]))
        elements.append(meta_table)
        elements.append(Spacer(1, 4))

        # 3. Subject Academic Performance Table
        col_w = [20, 136, 40, 36, 36, 44, 46, 42, 44, 112]
        headers = ['#', 'Subject Description', 'Code', 'Max', 'Pass', 'Score', 'Score %', 'Grade', 'Status', 'Teacher Remarks']
        marks_rows = [[
            Paragraph(f'<b>{h}</b>', style_cell_bold if i in (0, 1) else ParagraphStyle('HdrC', parent=style_cell_bold, alignment=1, textColor=colors.white))
            for i, h in enumerate(headers)
        ]]

        for idx, sub in enumerate(data.get('subjects', []), 1):
            if sub['is_absent']:
                score_p = Paragraph('ABSENT', style_cell_absent)
                status_p = Paragraph('Excused', style_cell_center)
            elif sub['marks_obtained'] is not None:
                score_p = Paragraph(str(sub['marks_obtained']), style_cell_center)
                status_p = Paragraph('Pass', style_cell_pass) if sub['is_passing'] else Paragraph('Fail', style_cell_fail)
            else:
                score_p = Paragraph('—', style_cell_center)
                status_p = Paragraph('Pending', style_cell_center)

            pct_txt = f"{sub['percentage']}%" if sub['percentage'] is not None else '—'

            marks_rows.append([
                Paragraph(str(idx), style_cell_center),
                Paragraph(sub['subject_name'], style_cell),
                Paragraph(sub['subject_code'], style_cell_center),
                Paragraph(str(sub['max_marks']), style_cell_center),
                Paragraph(str(sub['pass_marks']), style_cell_center),
                score_p,
                Paragraph(pct_txt, style_cell_center),
                Paragraph(sub['grade_label'], style_cell_center),
                status_p,
                Paragraph(sub.get('remarks') or 'Satisfactory work', style_cell),
            ])

        if not data.get('subjects'):
            marks_rows.append([
                Paragraph('', style_cell),
                Paragraph('<i>No verified subject marks recorded for this examination cycle.</i>', style_cell),
                Paragraph('', style_cell), Paragraph('', style_cell), Paragraph('', style_cell),
                Paragraph('', style_cell), Paragraph('', style_cell), Paragraph('', style_cell),
                Paragraph('', style_cell), Paragraph('', style_cell),
            ])

        # Overall Table Summary Footer Row
        tot_obt = str(metrics.get('total_obtained', '0.00'))
        tot_mx = str(metrics.get('total_max', '0.00'))
        avg_pct = f"{metrics.get('percentage', '0.00')}%"
        ov_grd = metrics.get('overall_grade', '—')

        marks_rows.append([
            Paragraph('', style_cell),
            Paragraph('<b>TOTAL / AVERAGE</b>', style_cell_bold),
            Paragraph('', style_cell),
            Paragraph(f'<b>{tot_mx}</b>', style_cell_center),
            Paragraph('', style_cell),
            Paragraph(f'<b>{tot_obt}</b>', style_cell_center),
            Paragraph(f'<b>{avg_pct}</b>', style_cell_center),
            Paragraph(f'<b>{ov_grd}</b>', style_cell_center),
            Paragraph('<b>Pass</b>' if metrics.get('standing', '').startswith('Pass') else '<b>Review</b>', style_cell_pass),
            Paragraph(f"<b>{metrics.get('standing', 'Good Standing')}</b>", style_cell),
        ])

        marks_table = Table(marks_rows, colWidths=col_w)
        marks_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, colors.HexColor('#F8FAFC')]),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#EFF6FF')),
            ('PADDING', (0, 0), (-1, -1), 2.2),
        ]))
        elements.append(marks_table)
        elements.append(Spacer(1, 4))

        # 4. Performance & Attendance Summary Grid (Side-by-Side Tables)
        att = data.get('attendance', {})
        summary_box = [
            [Paragraph('<b>ACADEMIC PERFORMANCE SUMMARY</b>', style_box_title), Paragraph('', style_cell)],
            [Paragraph('Total Score Obtained:', style_cell), Paragraph(f'<b>{tot_obt} / {tot_mx}</b>', style_cell)],
            [Paragraph('Overall Average Score:', style_cell), Paragraph(f'<b>{avg_pct}</b>', style_cell)],
            [Paragraph('Grade Awarded:', style_cell), Paragraph(f"<b>{ov_grd}</b> ({metrics.get('grade_description', 'Standard')})", style_cell)],
            [Paragraph('Class Standing &amp; Rank:', style_cell), Paragraph(f"<b>#{metrics.get('rank', '—')}</b> ({metrics.get('standing', 'In Progress')})", style_cell)],
        ]
        att_box = [
            [Paragraph('<b>STUDENT ATTENDANCE RECORD</b>', style_box_title), Paragraph('', style_cell)],
            [Paragraph('Total Academic Sessions:', style_cell), Paragraph(f"<b>{att.get('total_sessions', 0)} Days</b>", style_cell)],
            [Paragraph('Sessions Present / Absent:', style_cell), Paragraph(f"<b>{att.get('present', 0)} Present</b> &bull; {att.get('absent', 0)} Absent", style_cell)],
            [Paragraph('Sessions Late / Excused:', style_cell), Paragraph(f"{att.get('late', 0)} Late &bull; {att.get('excused', 0)} Excused", style_cell)],
            [Paragraph('Net Attendance Rate:', style_cell), Paragraph(f"<b>{att.get('rate', 0.0)}%</b>", style_cell)],
        ]
        tbl_summ = Table(summary_box, colWidths=[140, 130])
        tbl_summ.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('PADDING', (0, 0), (-1, -1), 2),
        ]))
        tbl_att = Table(att_box, colWidths=[140, 130])
        tbl_att.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('PADDING', (0, 0), (-1, -1), 2),
        ]))

        twin_table = Table([[tbl_summ, tbl_att]], colWidths=[274, 274])
        twin_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('PADDING', (0, 0), (-1, -1), 0),
        ]))
        elements.append(twin_table)
        elements.append(Spacer(1, 4))

        # 5. Official End-of-Year Promotion Decision Box
        promo = data.get('promotion', {})
        if promo.get('is_approved'):
            target_str = f" to {promo.get('next_grade')}" if promo.get('next_grade') else ""
            promo_title = f"OFFICIAL PROMOTION STATUS: {promo.get('status', 'Approved').upper()}{target_str.upper()}"
            promo_box = [
                [Paragraph(f'<b>{promo_title}</b>', style_cell_bold)],
                [Paragraph(f"<i>{promo.get('comments', 'Decision authorized and finalized by Metti Secondary School Academic Committee.')}</i>", style_cell)],
            ]
            box_bg = colors.HexColor('#F0FDF4')
            box_border = colors.HexColor('#86EFAC')
        else:
            promo_box = [
                [Paragraph('<b>ANNUAL PROMOTION STATUS:</b> Pending Official Academic Committee Approval', style_cell_bold)],
                [Paragraph('<i>Annual grade promotion is officially evaluated and authorized at the conclusion of all semester examination cycles.</i>', style_cell)],
            ]
            box_bg = colors.HexColor('#FEF9C3')
            box_border = colors.HexColor('#FDE047')

        tbl_promo = Table(promo_box, colWidths=[548])
        tbl_promo.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), box_bg),
            ('BOX', (0, 0), (-1, -1), 0.8, box_border),
            ('PADDING', (0, 0), (-1, -1), 2.5),
        ]))
        elements.append(tbl_promo)
        elements.append(Spacer(1, 8))

        # 6. Official Signatures Section
        sig_data = [
            [
                Paragraph('___________________________<br/><b>Homeroom Teacher</b><br/>Signature &amp; Date', style_sig),
                Paragraph('___________________________<br/><b>Exam Officer / Registrar</b><br/>Signature &amp; Date', style_sig),
                Paragraph('___________________________<br/><b>School Principal</b><br/>Signature, Date &amp; School Seal', style_sig),
            ]
        ]
        sig_table = Table(sig_data, colWidths=[182, 182, 184])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(sig_table)
        elements.append(Spacer(1, 3))
        elements.append(Paragraph('Metti Secondary School &bull; Majang Zone, Gambella Region, Ethiopia &bull; Offline Local Area Network (LAN) Build &bull; English Only', style_sub))

        doc.build(elements)
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @classmethod
    def export_class_results_excel(cls, examination, class_offering=None, filename="class_results.xlsx"):
        """Exports full classroom gradebook spreadsheet via openpyxl."""
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Class Gradebook"

        title_font = Font(name="Arial", size=13, bold=True, color="1E3A8A")
        header_font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")

        ws['A1'] = "Smart School Management System (SSMS) — Examination Results Sheet"
        ws['A1'].font = title_font
        ws['A2'] = f"Exam: {examination.name} | Year: {examination.academic_year.name} | Generated: {timezone.now():%Y-%m-%d %H:%M}"
        ws['A2'].font = Font(name="Arial", size=10, italic=True)

        exam_subjects = examination.exam_subjects.all().select_related('subject')

        headers = ["#", "Admission No", "Student Full Name", "Gender"]
        for es in exam_subjects:
            headers.append(f"{es.subject.code} (/{es.max_marks})")
        headers.extend(["Total", "Average", "Percentage", "Grade", "Rank"])

        row_num = 4
        for col_num, h in enumerate(headers, 1):
            cell = ws.cell(row=row_num, column=col_num, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")

        row_num += 1

        summaries_qs = StudentResultSummary.objects.filter(
            examination=examination
        ).select_related('student_enrollment__student')
        if class_offering:
            summaries_qs = summaries_qs.filter(student_enrollment__class_offering=class_offering)

        for idx, summ in enumerate(summaries_qs.order_by('rank', '-average_mark'), 1):
            st = summ.student_enrollment.student
            ws.cell(row=row_num, column=1, value=idx)
            ws.cell(row=row_num, column=2, value=st.admission_number)
            ws.cell(row=row_num, column=3, value=st.full_name)
            ws.cell(row=row_num, column=4, value=st.gender)

            col_cursor = 5
            for es in exam_subjects:
                mk = Mark.objects.filter(student_enrollment=summ.student_enrollment, exam_subject=es).first()
                if mk:
                    val = "ABS" if mk.is_absent else (mk.marks_obtained if mk.marks_obtained is not None else "—")
                else:
                    val = "—"
                ws.cell(row=row_num, column=col_cursor, value=str(val)).alignment = Alignment(horizontal="center")
                col_cursor += 1

            ws.cell(row=row_num, column=col_cursor, value=summ.total_obtained)
            ws.cell(row=row_num, column=col_cursor + 1, value=summ.average_mark)
            ws.cell(row=row_num, column=col_cursor + 2, value=f"{summ.percentage}%")
            ws.cell(row=row_num, column=col_cursor + 3, value=summ.overall_grade)
            ws.cell(row=row_num, column=col_cursor + 4, value=summ.rank or "—")
            row_num += 1

        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 10)

        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)

        response = HttpResponse(
            stream.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class MarksExportImportService:
    """
    Step 21: Service managing Excel and CSV examination mark templates,
    multi-step validation, preview parsing, error reporting, atomic confirmation,
    and granular database record export.
    """

    @classmethod
    def generate_marks_template(cls, exam_subject, class_offering=None, file_format='xlsx'):
        """
        Generates a structured marks entry template containing actual enrolled student records.
        Outputs in either Excel (.xlsx) or CSV (.csv) format.
        """
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter

        # Fetch active enrollments for this grade / stream / offering
        enrollments_qs = StudentEnrollment.objects.filter(
            class_offering__grade=exam_subject.grade,
            academic_year=exam_subject.examination.academic_year,
            status='ACTIVE'
        ).select_related('student', 'class_offering__grade', 'class_offering__section', 'class_offering__stream')

        if exam_subject.stream:
            enrollments_qs = enrollments_qs.filter(class_offering__stream=exam_subject.stream)
        if class_offering:
            enrollments_qs = enrollments_qs.filter(class_offering=class_offering)

        enrollments_qs = enrollments_qs.order_by(
            'class_offering__section__name',
            'student__first_name',
            'student__father_name',
            'student__grandfather_name'
        )

        existing_marks = {
            m.student_enrollment_id: m
            for m in Mark.objects.filter(exam_subject=exam_subject).select_related('student_enrollment')
        }

        safe_subj = exam_subject.subject.code.replace('/', '_').replace(' ', '_')
        safe_grade = exam_subject.grade.name.replace('/', '_').replace(' ', '_')
        filename = f"Marks_Template_{safe_subj}_{safe_grade}_{exam_subject.examination_id}.{file_format}"

        if file_format == 'csv':
            stream = io.StringIO()
            writer = csv.writer(stream)
            # UTF-8 BOM is written via bytes response for Excel compatibility
            writer.writerow([
                "Admission Number",
                "Student Full Name",
                "Grade",
                "Section",
                "Stream",
                "Subject Code",
                "Subject Name",
                "Examination",
                "Max Mark",
                "Mark Obtained",
                "Is Absent",
                "Remarks"
            ])

            for enr in enrollments_qs:
                st = enr.student
                existing = existing_marks.get(enr.id)
                score_str = str(existing.marks_obtained) if existing and existing.marks_obtained is not None else ""
                absent_str = "YES" if existing and existing.is_absent else "NO"
                remarks_str = existing.remarks if existing else ""
                stream_str = enr.class_offering.stream.name if enr.class_offering and enr.class_offering.stream else "General"
                section_str = enr.class_offering.section.name if enr.class_offering and enr.class_offering.section else ""

                writer.writerow([
                    sanitize_csv_cell(st.admission_number),
                    sanitize_csv_cell(st.full_name),
                    sanitize_csv_cell(exam_subject.grade.name),
                    sanitize_csv_cell(section_str),
                    sanitize_csv_cell(stream_str),
                    sanitize_csv_cell(exam_subject.subject.code),
                    sanitize_csv_cell(exam_subject.subject.name),
                    sanitize_csv_cell(exam_subject.examination.name),
                    exam_subject.max_marks,
                    score_str,
                    absent_str,
                    sanitize_csv_cell(remarks_str)
                ])


            csv_bytes = ('\ufeff' + stream.getvalue()).encode('utf-8')
            response = HttpResponse(csv_bytes, content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        # Excel (.xlsx) Generation via openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Marks Entry Template"

        # Styles
        title_font = Font(name="Arial", size=12, bold=True, color="1E3A8A")
        sub_font = Font(name="Arial", size=9, italic=True, color="475569")
        header_font = Font(name="Arial", size=9, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        editable_fill = PatternFill(start_color="FEF9C3", end_color="FEF9C3", fill_type="solid") # subtle yellow
        thin_border = Border(
            left=Side(style='thin', color='E2E8F0'),
            right=Side(style='thin', color='E2E8F0'),
            top=Side(style='thin', color='E2E8F0'),
            bottom=Side(style='thin', color='E2E8F0')
        )

        ws['A1'] = "METTI SECONDARY SCHOOL — EXAMINATION MARKS ENTRY TEMPLATE"
        ws['A1'].font = title_font
        ws['A2'] = (
            f"Examination: {exam_subject.examination.name} | "
            f"Subject: {exam_subject.subject.name} ({exam_subject.subject.code}) | "
            f"Grade: {exam_subject.grade.name} | "
            f"Max Marks: {exam_subject.max_marks} | "
            f"Pass Marks: {exam_subject.pass_marks}"
        )
        ws['A2'].font = sub_font
        ws['A3'] = (
            "INSTRUCTIONS: Enter numerical scores between 0.00 and "
            f"{exam_subject.max_marks} in the 'Mark Obtained' column. "
            "For absent students, enter 'YES' in 'Is Absent'. Do not alter Admission Numbers."
        )
        ws['A3'].font = Font(name="Arial", size=8.5, color="DC2626", bold=True)

        headers = [
            "Admission Number",
            "Student Full Name",
            "Grade",
            "Section",
            "Stream",
            "Subject Code",
            "Subject Name",
            "Examination",
            "Max Mark",
            "Mark Obtained",
            "Is Absent",
            "Remarks"
        ]

        row_num = 5
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=row_num, column=col_idx, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

        row_num += 1
        for enr in enrollments_qs:
            st = enr.student
            existing = existing_marks.get(enr.id)
            score_val = float(existing.marks_obtained) if existing and existing.marks_obtained is not None else ""
            absent_val = "YES" if existing and existing.is_absent else "NO"
            remarks_val = existing.remarks if existing else ""
            stream_str = enr.class_offering.stream.name if enr.class_offering and enr.class_offering.stream else "General"
            section_str = enr.class_offering.section.name if enr.class_offering and enr.class_offering.section else ""

            row_values = [
                st.admission_number,
                st.full_name,
                exam_subject.grade.name,
                section_str,
                stream_str,
                exam_subject.subject.code,
                exam_subject.subject.name,
                exam_subject.examination.name,
                float(exam_subject.max_marks),
                score_val,
                absent_val,
                remarks_val
            ]

            for c_idx, val in enumerate(row_values, 1):
                c = ws.cell(row=row_num, column=c_idx, value=val)
                c.border = thin_border
                c.font = Font(name="Arial", size=9)
                if c_idx in [1, 3, 4, 6, 9, 11]:
                    c.alignment = Alignment(horizontal="center")
                elif c_idx == 10:
                    c.alignment = Alignment(horizontal="right")
                    c.fill = editable_fill # Highlight editable column
                else:
                    c.alignment = Alignment(horizontal="left")

            row_num += 1

        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)

        response = HttpResponse(
            stream.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @classmethod
    def validate_import_file(cls, uploaded_file, exam_subject, class_offering=None, user=None):
        """
        Validates uploaded Excel (.xlsx) or CSV (.csv) marks file without committing to database.
        Detects invalid student IDs, negative scores, scores exceeding max marks, duplicates,
        and locked examination subjects.
        Returns a rich validation result dictionary.
        """
        # 1. State and Lock Checks
        if exam_subject.examination.is_closed or exam_subject.examination.status == 'CLOSED':
            return {
                'is_valid': False,
                'fatal_error': f"Examination '{exam_subject.examination.name}' is closed and locked. Marks cannot be modified.",
                'valid_rows': [],
                'invalid_rows': [],
                'total_rows': 0,
            }

        if exam_subject.is_locked:
            return {
                'is_valid': False,
                'fatal_error': (
                    f"Marks entry for '{exam_subject.subject.name}' ({exam_subject.grade.name}) is verified or locked. "
                    "File import is disabled."
                ),
                'valid_rows': [],
                'invalid_rows': [],
                'total_rows': 0,
            }

        # 2. RBAC assignment check for Teacher role
        if user and hasattr(user, 'teacher_profile') and user.teacher_profile:
            is_assigned = TeacherAssignment.objects.filter(
                teacher=user.teacher_profile,
                subject=exam_subject.subject,
                class_offering__grade=exam_subject.grade
            ).exists()
            if not is_assigned:
                return {
                    'is_valid': False,
                    'fatal_error': (
                        f"Access Denied: Teacher '{user.get_full_name()}' is not assigned to teach "
                        f"{exam_subject.subject.name} for {exam_subject.grade.name}."
                    ),
                    'valid_rows': [],
                    'invalid_rows': [],
                    'total_rows': 0,
                }

        # 3. File Extension & Size Validation
        file_name = uploaded_file.name.lower()
        if not (file_name.endswith('.xlsx') or file_name.endswith('.csv')):
            return {
                'is_valid': False,
                'fatal_error': "Unsupported file extension. Only Excel (.xlsx) and CSV (.csv) files are supported.",
                'valid_rows': [],
                'invalid_rows': [],
                'total_rows': 0,
            }

        if uploaded_file.size > 5 * 1024 * 1024:
            return {
                'is_valid': False,
                'fatal_error': f"File size exceeds 5MB limit ({uploaded_file.size / (1024*1024):.2f}MB).",
                'valid_rows': [],
                'invalid_rows': [],
                'total_rows': 0,
            }

        # 4. Parse Rows from File
        raw_rows = []
        try:
            if file_name.endswith('.csv'):
                content = uploaded_file.read()
                try:
                    decoded = content.decode('utf-8-sig')
                except UnicodeDecodeError:
                    try:
                        decoded = content.decode('utf-8')
                    except UnicodeDecodeError:
                        decoded = content.decode('latin-1')
                reader = csv.reader(io.StringIO(decoded))
                raw_rows = [row for row in reader]
            else:
                import openpyxl
                wb = openpyxl.load_workbook(uploaded_file, data_only=True, read_only=True)
                ws = wb.active
                for r in ws.iter_rows(values_only=True):
                    raw_rows.append([str(c) if c is not None else '' for c in r])
        except Exception as e:
            return {
                'is_valid': False,
                'fatal_error': f"Failed to parse uploaded file: {str(e)}",
                'valid_rows': [],
                'invalid_rows': [],
                'total_rows': 0,
            }

        if not raw_rows:
            return {
                'is_valid': False,
                'fatal_error': "Uploaded file is completely empty.",
                'valid_rows': [],
                'invalid_rows': [],
                'total_rows': 0,
            }

        # 5. Locate Header Row
        header_idx = -1
        col_map = {}
        for r_idx, row in enumerate(raw_rows[:10]):
            joined = " ".join(str(c).lower() for c in row if c)
            if 'admission' in joined and ('mark' in joined or 'score' in joined or 'obtained' in joined):
                header_idx = r_idx
                for c_idx, cell in enumerate(row):
                    cell_clean = str(cell).strip().lower()
                    if 'admission' in cell_clean:
                        col_map['adm'] = c_idx
                    elif 'name' in cell_clean:
                        col_map['name'] = c_idx
                    elif 'mark obtained' in cell_clean or 'obtained' in cell_clean or cell_clean == 'mark' or cell_clean == 'score':
                        col_map['mark'] = c_idx
                    elif 'absent' in cell_clean:
                        col_map['absent'] = c_idx
                    elif 'remark' in cell_clean:
                        col_map['remarks'] = c_idx
                break

        if header_idx == -1 or 'adm' not in col_map or 'mark' not in col_map:
            return {
                'is_valid': False,
                'fatal_error': (
                    "Could not recognize template header columns ('Admission Number' and 'Mark Obtained'). "
                    "Please download and use the official SSMS template."
                ),
                'valid_rows': [],
                'invalid_rows': [],
                'total_rows': 0,
            }

        # 6. Fetch Eligible Active Enrollments
        enrollments_qs = StudentEnrollment.objects.filter(
            class_offering__grade=exam_subject.grade,
            academic_year=exam_subject.examination.academic_year,
            status='ACTIVE'
        ).select_related('student', 'class_offering__grade', 'class_offering__section', 'class_offering__stream')

        if exam_subject.stream:
            enrollments_qs = enrollments_qs.filter(class_offering__stream=exam_subject.stream)
        if class_offering:
            enrollments_qs = enrollments_qs.filter(class_offering=class_offering)

        enrollment_map = {e.student.admission_number.strip().upper(): e for e in enrollments_qs}
        existing_marks = {m.student_enrollment_id: m for m in Mark.objects.filter(exam_subject=exam_subject)}

        # 7. Row-by-Row Validation
        seen_admissions = set()
        valid_rows = []
        invalid_rows = []

        data_rows = raw_rows[header_idx + 1:]
        for idx, row in enumerate(data_rows, start=header_idx + 2):
            if not any(str(c).strip() for c in row):
                continue # Skip empty lines

            raw_adm = str(row[col_map['adm']]).strip() if col_map['adm'] < len(row) else ''
            raw_mark = str(row[col_map['mark']]).strip() if col_map['mark'] < len(row) else ''
            raw_absent = str(row[col_map['absent']]).strip().upper() if 'absent' in col_map and col_map['absent'] < len(row) else ''
            raw_remarks = str(row[col_map['remarks']]).strip() if 'remarks' in col_map and col_map['remarks'] < len(row) else ''
            raw_name = str(row[col_map['name']]).strip() if 'name' in col_map and col_map['name'] < len(row) else ''

            if not raw_adm:
                invalid_rows.append({
                    'row_num': idx,
                    'admission_number': 'MISSING',
                    'student_name': raw_name or '—',
                    'submitted_mark': raw_mark,
                    'error_message': 'Student admission number is required and cannot be blank.',
                    'recommended_fix': 'Provide a valid student admission number.'
                })
                continue

            adm_upper = raw_adm.upper()
            if adm_upper in seen_admissions:
                invalid_rows.append({
                    'row_num': idx,
                    'admission_number': raw_adm,
                    'student_name': raw_name or '—',
                    'submitted_mark': raw_mark,
                    'error_message': f"Duplicate student admission number '{raw_adm}' detected in uploaded file.",
                    'recommended_fix': 'Remove duplicate row from file before uploading.'
                })
                continue
            seen_admissions.add(adm_upper)

            enr = enrollment_map.get(adm_upper)
            if not enr:
                # Distinguish whether student doesn't exist at all vs enrolled in different class/year
                st_lookup = Student.objects.filter(admission_number__iexact=raw_adm).first()
                if st_lookup:
                    err_msg = (
                        f"Student '{st_lookup.full_name}' ({raw_adm}) exists in SSMS but is not enrolled "
                        f"in {exam_subject.grade.name} for academic year {exam_subject.examination.academic_year.name}."
                    )
                    s_name = st_lookup.full_name
                else:
                    err_msg = f"Admission number '{raw_adm}' does not exist in SSMS student records."
                    s_name = raw_name or 'Unknown Student'

                invalid_rows.append({
                    'row_num': idx,
                    'admission_number': raw_adm,
                    'student_name': s_name,
                    'submitted_mark': raw_mark,
                    'error_message': err_msg,
                    'recommended_fix': 'Verify admission number or ensure student is enrolled in target grade.'
                })
                continue

            student = enr.student
            student_display_name = student.full_name

            # Check existing mark lock
            existing = existing_marks.get(enr.id)
            if existing and existing.status in ('VERIFIED', 'PUBLISHED'):
                invalid_rows.append({
                    'row_num': idx,
                    'admission_number': raw_adm,
                    'student_name': student_display_name,
                    'submitted_mark': raw_mark,
                    'error_message': f"Marks for {student_display_name} are already verified/published and locked against overwriting.",
                    'recommended_fix': 'Request an administrator to return the mark subject to PENDING status if re-entry is required.'
                })
                continue

            # Absence vs Numeric Mark Evaluation
            is_absent = raw_absent in ('YES', 'Y', 'TRUE', '1', 'ABS', 'ABSENT')
            parsed_mark = None

            if not is_absent:
                if raw_mark and raw_mark.lower() not in ('none', 'null', '—', '-', ''):
                    try:
                        clean_num_str = raw_mark.replace(',', '.')
                        parsed_mark = Decimal(clean_num_str)
                    except Exception:
                        invalid_rows.append({
                            'row_num': idx,
                            'admission_number': raw_adm,
                            'student_name': student_display_name,
                            'submitted_mark': raw_mark,
                            'error_message': f"Invalid numeric score '{raw_mark}'. Value must be a valid number.",
                            'recommended_fix': f"Enter a decimal number between 0.00 and {exam_subject.max_marks}."
                        })
                        continue

                    if parsed_mark < Decimal('0.00'):
                        invalid_rows.append({
                            'row_num': idx,
                            'admission_number': raw_adm,
                            'student_name': student_display_name,
                            'submitted_mark': raw_mark,
                            'error_message': f"Negative mark ({parsed_mark}) is not allowed.",
                            'recommended_fix': 'Ensure score is zero or positive.'
                        })
                        continue

                    if parsed_mark > exam_subject.max_marks:
                        invalid_rows.append({
                            'row_num': idx,
                            'admission_number': raw_adm,
                            'student_name': student_display_name,
                            'submitted_mark': raw_mark,
                            'error_message': f"Score ({parsed_mark}) exceeds maximum allowed score of {exam_subject.max_marks}.",
                            'recommended_fix': f"Score cannot exceed {exam_subject.max_marks}."
                        })
                        continue

            action_type = 'UPDATE' if existing else 'CREATE'
            curr_mark_disp = (
                f"{existing.marks_obtained}/{exam_subject.max_marks}"
                if existing and existing.marks_obtained is not None
                else ("ABSENT" if existing and existing.is_absent else "UNMARKED")
            ) if existing else "—"

            valid_rows.append({
                'row_num': idx,
                'enrollment_id': enr.id,
                'admission_number': student.admission_number,
                'student_name': student_display_name,
                'section': enr.class_offering.section.name if enr.class_offering and enr.class_offering.section else '—',
                'mark_obtained': str(parsed_mark) if parsed_mark is not None else None,
                'is_absent': is_absent,
                'remarks': raw_remarks if raw_remarks.lower() not in ('none', 'null') else '',
                'action_type': action_type,
                'current_mark': curr_mark_disp,
            })

        total_rows = len(valid_rows) + len(invalid_rows)
        return {
            'is_valid': len(invalid_rows) == 0 and len(valid_rows) > 0,
            'total_rows': total_rows,
            'valid_count': len(valid_rows),
            'invalid_count': len(invalid_rows),
            'valid_rows': valid_rows,
            'invalid_rows': invalid_rows,
            'exam_subject_id': exam_subject.id,
            'exam_subject_name': str(exam_subject),
            'class_offering_id': class_offering.id if class_offering else None,
            'original_filename': uploaded_file.name,
        }

    @classmethod
    def commit_import_marks(cls, exam_subject_id, valid_rows, user, request=None):
        """
        Commits validated marks rows to database inside an atomic transaction.
        If an error occurs or the exam subject was locked in the meantime, rolls back completely.
        """
        exam_subject = ExamSubject.objects.select_related(
            'examination__academic_year', 'subject', 'grade', 'stream'
        ).get(pk=exam_subject_id)

        if exam_subject.is_locked:
            raise ValidationError(
                f"Cannot import marks: '{exam_subject.subject.name}' is verified or locked."
            )

        with transaction.atomic():
            marks_data = []
            for r in valid_rows:
                raw_score = r.get('mark_obtained')
                score = Decimal(raw_score) if raw_score is not None and raw_score != '' else None
                marks_data.append({
                    'enrollment_id': r['enrollment_id'],
                    'marks_obtained': score,
                    'is_absent': r.get('is_absent', False),
                    'is_excused': False,
                    'remarks': r.get('remarks', ''),
                })

            result = MarksService.record_bulk_marks(
                exam_subject=exam_subject,
                marks_data=marks_data,
                entered_by_user=user,
                request=request
            )

            ResultAuditHelper.log(
                request,
                'IMPORT',
                'ExamSubject',
                exam_subject.id,
                {
                    'action': 'EXCEL_CSV_MARKS_IMPORT',
                    'exam_subject': str(exam_subject),
                    'created': result['created'],
                    'updated': result['updated'],
                    'total_rows': len(valid_rows),
                }
            )

            return result

    @classmethod
    def generate_error_report(cls, invalid_rows, exam_subject_name="Marks_Import"):
        """Generates a downloadable CSV error report containing all invalid rows."""
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow([
            "Row Number",
            "Admission Number",
            "Student Name",
            "Submitted Mark",
            "Error Description",
            "Recommended Fix"
        ])
        for r in invalid_rows:
            writer.writerow([
                sanitize_csv_cell(r.get('row_num', '—')),
                sanitize_csv_cell(r.get('admission_number', '—')),
                sanitize_csv_cell(r.get('student_name', '—')),
                sanitize_csv_cell(r.get('submitted_mark', '—')),
                sanitize_csv_cell(r.get('error_message', '—')),
                sanitize_csv_cell(r.get('recommended_fix', '—'))
            ])


        csv_bytes = ('\ufeff' + stream.getvalue()).encode('utf-8')
        response = HttpResponse(csv_bytes, content_type='text/csv; charset=utf-8')
        filename = f"Marks_Import_Errors_{timezone.now():%Y%m%d_%H%M%S}.csv"
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @classmethod
    def export_examination_marks(cls, filters=None, file_format='xlsx'):
        """
        Exports granular examination marks from database to Excel (.xlsx) or CSV (.csv).
        Filterable by Academic Year, Examination, Grade, ClassOffering, Stream, and Subject.
        """
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
        from openpyxl.utils import get_column_letter

        filters = filters or {}
        marks_qs = Mark.objects.select_related(
            'student_enrollment__student',
            'student_enrollment__class_offering__grade',
            'student_enrollment__class_offering__section',
            'student_enrollment__class_offering__stream',
            'exam_subject__examination__academic_year',
            'exam_subject__subject',
            'exam_subject__grade'
        )

        if filters.get('academic_year'):
            marks_qs = marks_qs.filter(exam_subject__examination__academic_year=filters['academic_year'])
        if filters.get('examination'):
            marks_qs = marks_qs.filter(exam_subject__examination=filters['examination'])
        if filters.get('grade'):
            marks_qs = marks_qs.filter(student_enrollment__class_offering__grade=filters['grade'])
        if filters.get('class_offering'):
            marks_qs = marks_qs.filter(student_enrollment__class_offering=filters['class_offering'])
        if filters.get('stream'):
            marks_qs = marks_qs.filter(student_enrollment__class_offering__stream=filters['stream'])
        if filters.get('subject'):
            marks_qs = marks_qs.filter(exam_subject__subject=filters['subject'])
        if filters.get('exam_subject'):
            marks_qs = marks_qs.filter(exam_subject=filters['exam_subject'])

        marks_qs = marks_qs.order_by(
            'exam_subject__grade__level',
            'student_enrollment__class_offering__section__name',
            'student_enrollment__student__first_name',
            'exam_subject__subject__name'
        )

        filename = f"Marks_Export_{timezone.now():%Y%m%d_%H%M%S}.{file_format}"

        headers = [
            "#",
            "Admission Number",
            "Student Full Name",
            "Gender",
            "Academic Year",
            "Examination",
            "Grade",
            "Section",
            "Stream",
            "Subject Code",
            "Subject Name",
            "Max Marks",
            "Pass Marks",
            "Marks Obtained",
            "Percentage",
            "Status",
            "Remarks"
        ]

        if file_format == 'csv':
            stream = io.StringIO()
            writer = csv.writer(stream)
            writer.writerow(headers)

            for idx, m in enumerate(marks_qs, 1):
                st = m.student_enrollment.student
                es = m.exam_subject
                co = m.student_enrollment.class_offering

                score_disp = "ABSENT" if m.is_absent else (str(m.marks_obtained) if m.marks_obtained is not None else "UNMARKED")
                pct_disp = f"{m.percentage}%" if m.percentage is not None else "—"
                stream_name = co.stream.name if co and co.stream else "General"
                section_name = co.section.name if co and co.section else "—"

                writer.writerow([
                    idx,
                    sanitize_csv_cell(st.admission_number),
                    sanitize_csv_cell(st.full_name),
                    sanitize_csv_cell(st.gender),
                    sanitize_csv_cell(es.examination.academic_year.name),
                    sanitize_csv_cell(es.examination.name),
                    sanitize_csv_cell(es.grade.name),
                    sanitize_csv_cell(section_name),
                    sanitize_csv_cell(stream_name),
                    sanitize_csv_cell(es.subject.code),
                    sanitize_csv_cell(es.subject.name),
                    es.max_marks,
                    es.pass_marks,
                    score_disp,
                    pct_disp,
                    sanitize_csv_cell(m.get_status_display()),
                    sanitize_csv_cell(m.remarks or "")
                ])


            csv_bytes = ('\ufeff' + stream.getvalue()).encode('utf-8')
            response = HttpResponse(csv_bytes, content_type='text/csv; charset=utf-8')
            response['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

        # Excel Export via openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Examination Marks Export"

        title_font = Font(name="Arial", size=12, bold=True, color="1E3A8A")
        sub_font = Font(name="Arial", size=9, italic=True, color="475569")
        header_font = Font(name="Arial", size=9, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        thin_border = Border(
            left=Side(style='thin', color='E2E8F0'),
            right=Side(style='thin', color='E2E8F0'),
            top=Side(style='thin', color='E2E8F0'),
            bottom=Side(style='thin', color='E2E8F0')
        )

        ws['A1'] = "METTI SECONDARY SCHOOL — OFFICIAL EXAMINATION MARKS EXPORT"
        ws['A1'].font = title_font
        ws['A2'] = f"Generated: {timezone.now():%Y-%m-%d %H:%M:%S} | Total Records Exported: {marks_qs.count()}"
        ws['A2'].font = sub_font

        row_num = 4
        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=row_num, column=col_idx, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")

        row_num += 1
        for idx, m in enumerate(marks_qs, 1):
            st = m.student_enrollment.student
            es = m.exam_subject
            co = m.student_enrollment.class_offering

            score_disp = "ABSENT" if m.is_absent else (float(m.marks_obtained) if m.marks_obtained is not None else "UNMARKED")
            pct_disp = f"{m.percentage}%" if m.percentage is not None else "—"
            stream_name = co.stream.name if co and co.stream else "General"
            section_name = co.section.name if co and co.section else "—"

            row_data = [
                idx,
                st.admission_number,
                st.full_name,
                st.gender,
                es.examination.academic_year.name,
                es.examination.name,
                es.grade.name,
                section_name,
                stream_name,
                es.subject.code,
                es.subject.name,
                float(es.max_marks),
                float(es.pass_marks),
                score_disp,
                pct_disp,
                m.get_status_display(),
                m.remarks or ""
            ]

            for c_idx, val in enumerate(row_data, 1):
                c = ws.cell(row=row_num, column=c_idx, value=val)
                c.border = thin_border
                c.font = Font(name="Arial", size=9)
                if c_idx in [1, 2, 4, 7, 8, 10, 12, 13, 15, 16]:
                    c.alignment = Alignment(horizontal="center")
                elif c_idx == 14:
                    c.alignment = Alignment(horizontal="right")
                else:
                    c.alignment = Alignment(horizontal="left")

            row_num += 1

        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 10)

        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)

        response = HttpResponse(
            stream.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
