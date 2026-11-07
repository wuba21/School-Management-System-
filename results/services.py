"""
Results Management Service Layer for SSMS.

Handles marks recording, bulk evaluation, verification workflow,
decimal-safe result calculations, grading boundaries, and report card generation.
"""

import io
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
        """Assembles all data needed for an individual student report card."""
        if not grading_scale:
            grading_scale = GradingScale.objects.filter(is_default=True).first()

        summary = StudentResultSummary.objects.filter(
            student_enrollment=student_enrollment,
            examination=examination
        ).first()

        # Subject marks
        marks_qs = Mark.objects.filter(
            student_enrollment=student_enrollment,
            exam_subject__examination=examination
        ).select_related('exam_subject__subject', 'exam_subject__grade').order_by('exam_subject__subject__name')

        subjects_data = []
        for m in marks_qs:
            g_item = None
            if grading_scale and m.percentage is not None:
                g_item = grading_scale.get_grade_for_score(m.percentage)

            subjects_data.append({
                'subject_name': m.exam_subject.subject.name,
                'subject_code': m.exam_subject.subject.code,
                'max_marks': m.exam_subject.max_marks,
                'pass_marks': m.exam_subject.pass_marks,
                'marks_obtained': m.marks_obtained,
                'is_absent': m.is_absent,
                'percentage': m.percentage,
                'grade_label': g_item.grade_label if g_item else '—',
                'is_passing': m.is_passing,
                'remarks': m.remarks,
            })

        return {
            'student': student_enrollment.student,
            'enrollment': student_enrollment,
            'class_offering': student_enrollment.class_offering,
            'academic_year': examination.academic_year,
            'examination': examination,
            'summary': summary,
            'subjects': subjects_data,
            'grading_scale': grading_scale,
        }

    @classmethod
    def export_report_card_pdf(cls, data, filename="report_card.pdf"):
        """Generates an official printable PDF report card via ReportLab."""
        from reportlab.lib.pagesizes import letter, portrait
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=portrait(letter),
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40
        )
        elements = []
        styles = getSampleStyleSheet()

        school_title = ParagraphStyle(
            'SchoolHeader',
            parent=styles['Heading1'],
            fontSize=15,
            leading=18,
            alignment=1,
            textColor=colors.HexColor('#1E3A8A'),
            spaceAfter=3
        )
        subtitle = ParagraphStyle(
            'SubHeader',
            parent=styles['Normal'],
            fontSize=9,
            leading=12,
            alignment=1,
            textColor=colors.HexColor('#475569'),
            spaceAfter=10
        )
        report_title = ParagraphStyle(
            'CardTitle',
            parent=styles['Heading2'],
            fontSize=12,
            leading=14,
            alignment=1,
            textColor=colors.HexColor('#0F172A'),
            spaceAfter=12
        )

        elements.append(Paragraph("SMART SECONDARY SCHOOL MANAGEMENT SYSTEM", school_title))
        elements.append(Paragraph("Majang Zone, Gambella Region, Ethiopia &bull; Ministry of Education Secondary Curriculum", subtitle))
        elements.append(Paragraph(f"STUDENT ACADEMIC REPORT CARD — {data['examination'].name.upper()}", report_title))
        elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1E3A8A'), spaceAfter=12))

        # Student Details Box
        st = data['student']
        enr = data['enrollment']
        meta_table_data = [
            [
                Paragraph(f"<b>Student Name:</b> {st.full_name}", styles['Normal']),
                Paragraph(f"<b>Admission No:</b> {st.admission_number}", styles['Normal']),
            ],
            [
                Paragraph(f"<b>Classroom:</b> {enr.class_offering.display_name}", styles['Normal']),
                Paragraph(f"<b>Academic Year:</b> {data['academic_year'].name}", styles['Normal']),
            ],
            [
                Paragraph(f"<b>Gender:</b> {st.get_gender_display()}", styles['Normal']),
                Paragraph(f"<b>Semester:</b> {data['examination'].get_semester_display()}", styles['Normal']),
            ]
        ]
        meta_table = Table(meta_table_data, colWidths=[270, 260])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(meta_table)
        elements.append(Spacer(1, 14))

        # Marks Table
        marks_rows = [["Subject Name", "Max", "Pass", "Score", "Percentage", "Grade", "Status"]]
        for sub in data['subjects']:
            score_txt = "ABSENT" if sub['is_absent'] else (str(sub['marks_obtained']) if sub['marks_obtained'] is not None else "—")
            pct_txt = f"{sub['percentage']}%" if sub['percentage'] is not None else "—"
            status_txt = "Pass" if sub['is_passing'] else "Fail"

            marks_rows.append([
                sub['subject_name'],
                str(sub['max_marks']),
                str(sub['pass_marks']),
                score_txt,
                pct_txt,
                sub['grade_label'],
                status_txt
            ])

        marks_table = Table(marks_rows, colWidths=[180, 50, 50, 60, 75, 55, 60])
        marks_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
            ('PADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(marks_table)
        elements.append(Spacer(1, 14))

        # Overall Summary Box
        summ = data['summary']
        if summ:
            summary_table_data = [
                [
                    Paragraph(f"<b>Total Score:</b> {summ.total_obtained} / {summ.total_max}", styles['Normal']),
                    Paragraph(f"<b>Overall Percentage:</b> {summ.percentage}%", styles['Normal']),
                    Paragraph(f"<b>Overall Grade:</b> {summ.overall_grade}", styles['Normal']),
                ],
                [
                    Paragraph(f"<b>Average Mark:</b> {summ.average_mark}", styles['Normal']),
                    Paragraph(f"<b>Class Rank:</b> {summ.rank or '—'}", styles['Normal']),
                    Paragraph(f"<b>Result Status:</b> {summ.get_status_display()}", styles['Normal']),
                ]
            ]
            summary_table = Table(summary_table_data, colWidths=[180, 180, 170])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#EFF6FF')),
                ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#3B82F6')),
                ('PADDING', (0, 0), (-1, -1), 7),
            ]))
            elements.append(summary_table)

        elements.append(Spacer(1, 25))

        # Signature Footer
        sig_data = [
            [
                Paragraph("__________________________<br/><b>Homeroom Teacher</b>", styles['Normal']),
                Paragraph("__________________________<br/><b>School Director / Principal</b>", styles['Normal']),
                Paragraph("__________________________<br/><b>Official School Stamp</b>", styles['Normal']),
            ]
        ]
        sig_table = Table(sig_data, colWidths=[180, 180, 170])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ]))
        elements.append(sig_table)

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
