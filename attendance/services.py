"""
Attendance Management Service Layer for SSMS.

Encapsulates business rules, duplicate prevention, bulk processing,
analytics, audit logging, and export utilities for school attendance tracking.
"""

import io
from datetime import date, timedelta
from django.db import transaction
from django.db.models import Count, Q, F, Avg
from django.core.exceptions import ValidationError, PermissionDenied
from django.http import HttpResponse
from django.utils import timezone

from academics.models import AcademicYear, ClassOffering, Grade, Subject
from students.models import Student, StudentEnrollment
from teachers.models import Teacher, TeacherAssignment
from core.models import AuditLog
from attendance.models import AttendanceSession, AttendanceRecord


class AttendanceAuditHelper:
    """Centralized audit logger for attendance operations."""

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
            # Audit logging failure should not crash core workflow
            pass


class AttendanceSessionService:
    """Handles AttendanceSession lifecycle, validation, and permissions."""

    @classmethod
    def create_session(cls, class_offering, session_date, session_type='DAILY',
                       subject=None, recorded_by=None, created_by=None,
                       remarks='', request=None):
        ay = class_offering.academic_year
        if ay.is_closed:
            raise ValidationError(f"Academic Year '{ay.name}' is closed. Attendance cannot be recorded.")

        # If recorded by a teacher, verify that teacher is assigned to this class offering
        if recorded_by:
            assignment_qs = TeacherAssignment.objects.filter(
                teacher=recorded_by,
                class_offering=class_offering
            )
            if subject:
                assignment_qs = assignment_qs.filter(subject=subject)

            # We permit authorized teachers, or staff with elevated roles
            is_elevated = False
            if created_by:
                role_code = getattr(getattr(created_by, 'role', None), 'code', None)
                if created_by.is_superuser or role_code in ('ADMIN', 'REGISTRAR', 'PRINCIPAL'):
                    is_elevated = True

            if not is_elevated and not assignment_qs.exists():
                raise ValidationError(
                    f"Teacher {recorded_by.full_name} is not assigned to teach {class_offering.display_name}."
                )

        # Duplicate session check
        dup_qs = AttendanceSession.objects.filter(
            class_offering=class_offering,
            date=session_date,
            session_type=session_type
        )
        if subject:
            dup_qs = dup_qs.filter(subject=subject)
        else:
            dup_qs = dup_qs.filter(subject__isnull=True)

        if dup_qs.exists():
            subj_desc = f" for subject {subject.name}" if subject else ""
            raise ValidationError(
                f"An attendance session already exists for {class_offering.display_name} on "
                f"{session_date} ({session_type}{subj_desc})."
            )

        with transaction.atomic():
            session = AttendanceSession.objects.create(
                class_offering=class_offering,
                academic_year=ay,
                date=session_date,
                session_type=session_type,
                subject=subject,
                recorded_by=recorded_by,
                created_by=created_by,
                remarks=remarks,
                status='OPEN'
            )

            AttendanceAuditHelper.log(
                request,
                'CREATE',
                'AttendanceSession',
                session.id,
                {
                    'class_offering': str(class_offering),
                    'date': str(session_date),
                    'session_type': session_type,
                    'subject': subject.code if subject else None,
                    'recorded_by': recorded_by.employee_id if recorded_by else None,
                }
            )

        return session

    @classmethod
    def close_session(cls, session, user=None, request=None):
        """Locks an attendance session to prevent further regular edits."""
        if session.is_closed:
            return session

        session.status = 'CLOSED'
        session.save(update_fields=['status', 'updated_at'])

        AttendanceAuditHelper.log(
            request,
            'UPDATE',
            'AttendanceSession',
            session.id,
            {'action': 'CLOSE_SESSION', 'status': 'CLOSED'}
        )
        return session

    @classmethod
    def reopen_session(cls, session, user=None, request=None):
        """Reopens a closed session for administrative correction."""
        if not session.is_closed:
            return session

        if session.academic_year and session.academic_year.is_closed:
            raise ValidationError("Cannot reopen attendance for a closed academic year.")

        session.status = 'SUBMITTED'
        session.save(update_fields=['status', 'updated_at'])

        AttendanceAuditHelper.log(
            request,
            'OVERRIDE',
            'AttendanceSession',
            session.id,
            {'action': 'REOPEN_SESSION', 'status': 'SUBMITTED'}
        )
        return session


class AttendanceRecordService:
    """Manages individual and bulk student attendance entries."""

    @classmethod
    def record_bulk_attendance(cls, session, records_data, recorded_by_user=None, request=None):
        """
        Takes session and list of dicts:
        [{'enrollment_id': int, 'status': str, 'reason': str}, ...]
        """
        if not session.is_editable:
            raise ValidationError("This attendance session is locked and cannot be modified.")

        # Pre-fetch all active enrollments for this class offering
        valid_enrollments = {
            enr.id: enr for enr in StudentEnrollment.objects.filter(
                class_offering=session.class_offering,
                status='ACTIVE'
            ).select_related('student')
        }

        created_count = 0
        updated_count = 0
        summary_counts = {'PRESENT': 0, 'ABSENT': 0, 'LATE': 0, 'EXCUSED': 0}

        with transaction.atomic():
            for item in records_data:
                enr_id = item.get('enrollment_id')
                if enr_id not in valid_enrollments:
                    # Ignore or raise for invalid student
                    continue

                enrollment = valid_enrollments[enr_id]
                new_status = item.get('status', 'PRESENT').upper()
                if new_status not in ('PRESENT', 'ABSENT', 'LATE', 'EXCUSED'):
                    new_status = 'PRESENT'

                reason = (item.get('reason') or '').strip()

                record, created = AttendanceRecord.objects.update_or_create(
                    attendance_session=session,
                    student_enrollment=enrollment,
                    defaults={
                        'status': new_status,
                        'reason': reason,
                        'recorded_by': recorded_by_user
                    }
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

                summary_counts[new_status] += 1

            # Transition session from OPEN to SUBMITTED if currently open
            if session.status == 'OPEN':
                session.status = 'SUBMITTED'
                session.save(update_fields=['status', 'updated_at'])

            AttendanceAuditHelper.log(
                request,
                'UPDATE',
                'AttendanceSession',
                session.id,
                {
                    'action': 'RECORD_ATTENDANCE',
                    'created': created_count,
                    'updated': updated_count,
                    'summary': summary_counts
                }
            )

        return {
            'created': created_count,
            'updated': updated_count,
            'summary': summary_counts
        }

    @classmethod
    def update_single_record(cls, record, new_status, new_reason='', user=None, request=None):
        """Allows authorized staff to correct a single record with audit trail."""
        session = record.attendance_session
        if not session.is_editable:
            raise ValidationError("Cannot modify record of a closed attendance session.")

        old_status = record.status
        old_reason = record.reason

        record.status = new_status
        record.reason = new_reason
        if user:
            record.recorded_by = user
        record.save()

        AttendanceAuditHelper.log(
            request,
            'UPDATE',
            'AttendanceRecord',
            record.id,
            {
                'student': record.student_enrollment.student.admission_number,
                'old_status': old_status,
                'new_status': new_status,
                'old_reason': old_reason,
                'new_reason': new_reason,
            }
        )
        return record


class AttendanceAnalyticsService:
    """Aggregates attendance metrics, rates, and triggers early-warning alerts."""

    @classmethod
    def get_school_summary(cls, academic_year=None, query_date=None):
        """High-level metrics for dashboard."""
        if not academic_year:
            academic_year = AcademicYear.objects.filter(is_current=True).first()

        active_enrollments = StudentEnrollment.objects.filter(status='ACTIVE')
        if academic_year:
            active_enrollments = active_enrollments.filter(academic_year=academic_year)
        total_students = active_enrollments.count()

        sessions_qs = AttendanceSession.objects.all()
        records_qs = AttendanceRecord.objects.all()

        if academic_year:
            sessions_qs = sessions_qs.filter(academic_year=academic_year)
            records_qs = records_qs.filter(attendance_session__academic_year=academic_year)

        target_date = query_date or timezone.now().date()
        today_sessions = sessions_qs.filter(date=target_date)
        today_records = records_qs.filter(attendance_session__date=target_date)

        # Today's stats
        today_total_marks = today_records.count()
        today_present = today_records.filter(status='PRESENT').count()
        today_absent = today_records.filter(status='ABSENT').count()
        today_late = today_records.filter(status='LATE').count()
        today_excused = today_records.filter(status='EXCUSED').count()
        today_rate = round(((today_present + today_late) / today_total_marks * 100), 1) if today_total_marks > 0 else 0.0

        # Overall cumulative stats for academic year
        all_total_marks = records_qs.count()
        all_present = records_qs.filter(status='PRESENT').count()
        all_absent = records_qs.filter(status='ABSENT').count()
        all_late = records_qs.filter(status='LATE').count()
        all_excused = records_qs.filter(status='EXCUSED').count()
        overall_rate = round(((all_present + all_late) / all_total_marks * 100), 1) if all_total_marks > 0 else 0.0

        # Grade-wise performance
        grades_data = []
        for grade in Grade.objects.filter(is_active=True).order_by('level'):
            grade_records = records_qs.filter(attendance_session__class_offering__grade=grade)
            g_total = grade_records.count()
            if g_total > 0:
                g_present = grade_records.filter(status='PRESENT').count()
                g_late = grade_records.filter(status='LATE').count()
                g_rate = round(((g_present + g_late) / g_total * 100), 1)
            else:
                g_rate = 0.0
            grades_data.append({
                'grade_name': grade.name,
                'level': grade.level,
                'total_marks': g_total,
                'rate': g_rate
            })

        # Recent 7-day trend (business days or recent recorded dates)
        trend_dates = []
        trend_rates = []
        for i in range(6, -1, -1):
            d = target_date - timedelta(days=i)
            d_records = records_qs.filter(attendance_session__date=d)
            d_tot = d_records.count()
            d_rate = round(((d_records.filter(status='PRESENT').count() + d_records.filter(status='LATE').count()) / d_tot * 100), 1) if d_tot > 0 else 0.0
            trend_dates.append(d.strftime('%b %d'))
            trend_rates.append(d_rate)

        return {
            'target_date': target_date,
            'total_students': total_students,
            'today_sessions_count': today_sessions.count(),
            'today_total_marks': today_total_marks,
            'today_present': today_present,
            'today_absent': today_absent,
            'today_late': today_late,
            'today_excused': today_excused,
            'today_rate': today_rate,
            'all_total_marks': all_total_marks,
            'all_present': all_present,
            'all_absent': all_absent,
            'all_late': all_late,
            'all_excused': all_excused,
            'overall_rate': overall_rate,
            'grades_data': grades_data,
            'trend_dates': trend_dates,
            'trend_rates': trend_rates,
        }

    @classmethod
    def get_class_summary(cls, class_offering, start_date=None, end_date=None):
        """Attendance summary for a specific classroom."""
        sessions = AttendanceSession.objects.filter(class_offering=class_offering)
        if start_date:
            sessions = sessions.filter(date__gte=start_date)
        if end_date:
            sessions = sessions.filter(date__lte=end_date)

        records = AttendanceRecord.objects.filter(attendance_session__in=sessions)
        total = records.count()
        present = records.filter(status='PRESENT').count()
        absent = records.filter(status='ABSENT').count()
        late = records.filter(status='LATE').count()
        excused = records.filter(status='EXCUSED').count()
        rate = round(((present + late) / total * 100), 1) if total > 0 else 0.0

        return {
            'class_offering': class_offering,
            'total_sessions': sessions.count(),
            'total_records': total,
            'present': present,
            'absent': absent,
            'late': late,
            'excused': excused,
            'rate': rate,
        }

    @classmethod
    def get_student_summary(cls, student, academic_year=None):
        """Comprehensive student attendance profile with longitudinal preservation."""
        records = AttendanceRecord.objects.filter(
            student_enrollment__student=student
        ).select_related(
            'attendance_session__class_offering__grade',
            'attendance_session__class_offering__section',
            'attendance_session__subject',
            'attendance_session__recorded_by'
        ).order_by('-attendance_session__date', '-created_at')

        if academic_year:
            records = records.filter(attendance_session__academic_year=academic_year)

        total = records.count()
        present = records.filter(status='PRESENT').count()
        absent = records.filter(status='ABSENT').count()
        late = records.filter(status='LATE').count()
        excused = records.filter(status='EXCUSED').count()
        rate = round(((present + late) / total * 100), 1) if total > 0 else 0.0

        return {
            'student': student,
            'total_sessions': total,
            'present': present,
            'absent': absent,
            'late': late,
            'excused': excused,
            'rate': rate,
            'records': records,
        }

    @classmethod
    def get_attendance_alerts(cls, academic_year=None, threshold_pct=75.0, consecutive_days=3):
        """
        Identifies students with low attendance rates or consecutive unexcused absences,
        plus classes missing attendance for today.
        Non-punitive, supporting pastoral care and early intervention.
        """
        if not academic_year:
            academic_year = AcademicYear.objects.filter(is_current=True).first()

        # 1. Chronic absenteeism (< threshold_pct) with at least 3 recorded sessions
        chronic_alerts = []
        enrollments = StudentEnrollment.objects.filter(
            status='ACTIVE'
        ).select_related('student', 'class_offering__grade', 'class_offering__section')

        if academic_year:
            enrollments = enrollments.filter(academic_year=academic_year)

        for enr in enrollments:
            marks = AttendanceRecord.objects.filter(student_enrollment=enr)
            total = marks.count()
            if total >= 3:
                present = marks.filter(status__in=['PRESENT', 'LATE']).count()
                rate = round((present / total) * 100, 1)
                if rate < threshold_pct:
                    chronic_alerts.append({
                        'student': enr.student,
                        'enrollment': enr,
                        'class_offering': enr.class_offering,
                        'total_sessions': total,
                        'absent_count': marks.filter(status='ABSENT').count(),
                        'rate': rate,
                        'severity': 'HIGH' if rate < 60 else 'MODERATE'
                    })

        chronic_alerts.sort(key=lambda x: x['rate'])

        # 2. Consecutive absences
        consecutive_alerts = []
        for enr in enrollments:
            recent_marks = list(
                AttendanceRecord.objects.filter(student_enrollment=enr)
                .order_by('-attendance_session__date')[:consecutive_days]
            )
            if len(recent_marks) >= consecutive_days and all(m.status == 'ABSENT' for m in recent_marks):
                consecutive_alerts.append({
                    'student': enr.student,
                    'enrollment': enr,
                    'class_offering': enr.class_offering,
                    'consecutive_days': len(recent_marks),
                    'last_absent_date': recent_marks[0].attendance_session.date,
                })

        # 3. Classes missing attendance today
        today = timezone.now().date()
        missing_classes = []
        active_classes = ClassOffering.objects.filter(
            academic_year=academic_year
        ).select_related('grade', 'section', 'stream') if academic_year else []

        for co in active_classes:
            has_today = AttendanceSession.objects.filter(
                class_offering=co,
                date=today
            ).exists()
            if not has_today:
                missing_classes.append(co)

        return {
            'chronic_alerts': chronic_alerts,
            'consecutive_alerts': consecutive_alerts,
            'missing_classes': missing_classes,
            'threshold_pct': threshold_pct,
            'consecutive_days': consecutive_days,
            'today': today,
        }


class AttendanceExportService:
    """Provides Excel (.xlsx) and PDF document generation for attendance reports."""

    @classmethod
    def export_excel(cls, report_type, data, filename="attendance_report.xlsx"):
        """Exports tabular attendance data using openpyxl."""
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Attendance Report"

        # Headers styling
        title_font = Font(name="Arial", size=14, bold=True, color="1E3A8A")
        header_font = Font(name="Arial", size=10, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        thin_border = Border(
            left=Side(style='thin', color='D9D9D9'),
            right=Side(style='thin', color='D9D9D9'),
            top=Side(style='thin', color='D9D9D9'),
            bottom=Side(style='thin', color='D9D9D9')
        )

        ws['A1'] = "Smart School Management and Academic Information System (SSMS)"
        ws['A1'].font = title_font
        ws['A2'] = f"Report Type: {report_type.replace('_', ' ').title()} | Generated: {timezone.now().strftime('%Y-%m-%d %H:%M')}"
        ws['A2'].font = Font(name="Arial", size=10, italic=True)

        row_num = 4
        if report_type == 'session' and 'session' in data:
            session = data['session']
            records = data.get('records', [])
            ws[f'A{row_num}'] = f"Class: {session.class_offering.display_name} | Date: {session.date} | Session: {session.get_session_type_display()}"
            ws[f'A{row_num}'].font = Font(name="Arial", size=11, bold=True)
            row_num += 2

            headers = ["#", "Admission No", "Student Full Name", "Gender", "Status", "Reason / Remarks"]
            for col_num, h in enumerate(headers, 1):
                cell = ws.cell(row=row_num, column=col_num)
                cell.value = h
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center")

            row_num += 1
            for idx, r in enumerate(records, 1):
                ws.cell(row=row_num, column=1, value=idx).alignment = Alignment(horizontal="center")
                ws.cell(row=row_num, column=2, value=r.student_enrollment.student.admission_number)
                ws.cell(row=row_num, column=3, value=r.student_enrollment.student.full_name)
                ws.cell(row=row_num, column=4, value=r.student_enrollment.student.get_gender_display())
                ws.cell(row=row_num, column=5, value=r.get_status_display())
                ws.cell(row=row_num, column=6, value=r.reason)
                row_num += 1

        elif report_type == 'class_summary' and 'classes' in data:
            headers = ["#", "Class Offering", "Grade", "Section", "Total Sessions", "Present", "Absent", "Late", "Excused", "Attendance Rate %"]
            for col_num, h in enumerate(headers, 1):
                cell = ws.cell(row=row_num, column=col_num)
                cell.value = h
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center")

            row_num += 1
            for idx, item in enumerate(data['classes'], 1):
                ws.cell(row=row_num, column=1, value=idx).alignment = Alignment(horizontal="center")
                ws.cell(row=row_num, column=2, value=str(item['class_offering']))
                ws.cell(row=row_num, column=3, value=item['class_offering'].grade.name)
                ws.cell(row=row_num, column=4, value=item['class_offering'].section.name)
                ws.cell(row=row_num, column=5, value=item['total_sessions'])
                ws.cell(row=row_num, column=6, value=item['present'])
                ws.cell(row=row_num, column=7, value=item['absent'])
                ws.cell(row=row_num, column=8, value=item['late'])
                ws.cell(row=row_num, column=9, value=item['excused'])
                ws.cell(row=row_num, column=10, value=f"{item['rate']}%")
                row_num += 1
        else:
            # Generic export
            headers = ["#", "Details"]
            for col_num, h in enumerate(headers, 1):
                ws.cell(row=row_num, column=col_num, value=h)

        # Auto-adjust column widths
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

    @classmethod
    def export_pdf(cls, report_type, data, filename="attendance_report.pdf"):
        """Exports tabular attendance data using ReportLab."""
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(letter),
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'ReportTitle',
            parent=styles['Heading1'],
            fontSize=16,
            leading=20,
            textColor=colors.HexColor('#1E3A8A'),
            spaceAfter=6
        )
        subtitle_style = ParagraphStyle(
            'ReportSubtitle',
            parent=styles['Normal'],
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#475569'),
            spaceAfter=14
        )

        elements.append(Paragraph("Smart School Management and Academic Information System (SSMS)", title_style))
        elements.append(Paragraph(f"Attendance Report: {report_type.replace('_', ' ').title()} — Generated on {timezone.now().strftime('%Y-%m-%d %H:%M')}", subtitle_style))
        elements.append(Spacer(1, 10))

        if report_type == 'session' and 'session' in data:
            session = data['session']
            records = data.get('records', [])
            info_text = f"<b>Class:</b> {session.class_offering.display_name} &nbsp;|&nbsp; <b>Date:</b> {session.date} &nbsp;|&nbsp; <b>Type:</b> {session.get_session_type_display()} &nbsp;|&nbsp; <b>Recorded By:</b> {session.recorded_by.full_name if session.recorded_by else 'Staff'}"
            elements.append(Paragraph(info_text, styles['Normal']))
            elements.append(Spacer(1, 12))

            table_data = [["#", "Admission No", "Student Full Name", "Gender", "Status", "Reason / Remarks"]]
            for idx, r in enumerate(records, 1):
                table_data.append([
                    str(idx),
                    r.student_enrollment.student.admission_number,
                    r.student_enrollment.student.full_name,
                    r.student_enrollment.student.get_gender_display(),
                    r.get_status_display(),
                    r.reason or "-"
                ])

            t = Table(table_data, colWidths=[30, 110, 200, 60, 90, 230])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
            ]))
            elements.append(t)

        elif report_type == 'class_summary' and 'classes' in data:
            table_data = [["#", "Class Offering", "Grade", "Section", "Sessions", "Present", "Absent", "Late", "Excused", "Rate %"]]
            for idx, item in enumerate(data['classes'], 1):
                table_data.append([
                    str(idx),
                    str(item['class_offering']),
                    item['class_offering'].grade.name,
                    item['class_offering'].section.name,
                    str(item['total_sessions']),
                    str(item['present']),
                    str(item['absent']),
                    str(item['late']),
                    str(item['excused']),
                    f"{item['rate']}%"
                ])

            t = Table(table_data, colWidths=[30, 160, 70, 60, 60, 60, 60, 50, 60, 70])
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
            ]))
            elements.append(t)
        else:
            elements.append(Paragraph("No detailed records found for the requested report criteria.", styles['Normal']))

        doc.build(elements)
        buffer.seek(0)

        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
