"""
Attendance Management Views for SSMS.

Implements role-gated interfaces for:
  - Attendance Dashboard with Chart.js visualizations
  - Attendance Session Management (create, view, close, reopen)
  - Student Roll-Call Recording (bulk grid entry with duplicate prevention)
  - Student Longitudinal Attendance History
  - Multi-Criteria Attendance Reports (Daily, Class, Grade, Student)
  - Excel (.xlsx) and PDF Export using OpenPyXL and ReportLab
  - Attendance Early-Warning Alerts (Chronic absenteeism, missing roll-calls)
"""

from datetime import date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied, ValidationError
from django.views.decorators.http import require_POST
from django.db.models import Count, Q
from django.utils import timezone

from accounts.decorators import (
    any_authenticated_role_required,
    management_staff_required,
    principal_or_registrar_required,
)
from academics.models import AcademicYear, ClassOffering, Grade, Subject
from students.models import Student, StudentEnrollment
from teachers.models import Teacher, TeacherAssignment
from attendance.models import AttendanceSession, AttendanceRecord
from attendance.forms import (
    AttendanceSessionCreateForm,
    AttendanceFilterForm,
    SingleRecordUpdateForm,
)
from attendance.services import (
    AttendanceSessionService,
    AttendanceRecordService,
    AttendanceAnalyticsService,
    AttendanceExportService,
    AttendanceAuditHelper,
)


def _get_user_role(user):
    """Helper to extract user's primary role code."""
    if user.is_superuser:
        return 'ADMIN'
    if user.role:
        return user.role.code
    return None


def _is_teacher_assigned_to_class(teacher, class_offering):
    """Verifies whether a teacher is assigned to teach a class offering."""
    if not teacher or not class_offering:
        return False
    return TeacherAssignment.objects.filter(
        teacher=teacher,
        class_offering=class_offering
    ).exists()


# -----------------------------------------------------------------------------
# 1. ATTENDANCE DASHBOARD
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def attendance_dashboard_view(request):
    """
    Main attendance landing page.
    Displays KPI metrics, Chart.js trends, quick session actions, and recent activity.
    """
    user_role = _get_user_role(request.user)
    current_year = AcademicYear.objects.filter(is_current=True).first()
    selected_date_str = request.GET.get('date')
    
    query_date = timezone.now().date()
    if selected_date_str:
        try:
            query_date = date.fromisoformat(selected_date_str)
        except ValueError:
            query_date = timezone.now().date()

    teacher_profile = getattr(request.user, 'teacher_profile', None) if user_role == 'TEACHER' else None

    # Get analytical metrics
    metrics = AttendanceAnalyticsService.get_school_summary(
        academic_year=current_year,
        query_date=query_date
    )

    # Filter recent sessions
    recent_sessions_qs = AttendanceSession.objects.select_related(
        'class_offering__grade',
        'class_offering__section',
        'class_offering__stream',
        'subject',
        'recorded_by'
    ).order_by('-date', '-created_at')

    if user_role == 'TEACHER' and teacher_profile:
        # Teachers see their assigned classes' recent sessions
        assigned_offering_ids = TeacherAssignment.objects.filter(
            teacher=teacher_profile
        ).values_list('class_offering_id', flat=True)
        recent_sessions_qs = recent_sessions_qs.filter(class_offering_id__in=assigned_offering_ids)

    recent_sessions = recent_sessions_qs[:10]

    # Teacher quick class shortcuts
    teacher_classes = []
    if user_role == 'TEACHER' and teacher_profile:
        assignments = TeacherAssignment.objects.filter(
            teacher=teacher_profile,
            class_offering__academic_year=current_year
        ).select_related('class_offering__grade', 'class_offering__section', 'subject')
        teacher_classes = [a.class_offering for a in assignments]

    context = {
        'active_menu': 'attendance',
        'page_title': 'Attendance Dashboard',
        'user_role': user_role,
        'current_year': current_year,
        'query_date': query_date,
        'metrics': metrics,
        'recent_sessions': recent_sessions,
        'teacher_classes': set(teacher_classes),
        'is_teacher': user_role == 'TEACHER',
        'is_principal': user_role == 'PRINCIPAL',
        'is_management': user_role in ('ADMIN', 'REGISTRAR', 'PRINCIPAL'),
    }
    return render(request, 'attendance/dashboard.html', context)


# -----------------------------------------------------------------------------
# 2. ATTENDANCE SESSIONS LIST
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def attendance_session_list_view(request):
    """
    Searchable and paginated directory of all roll-call attendance sessions.
    """
    user_role = _get_user_role(request.user)
    teacher_profile = getattr(request.user, 'teacher_profile', None) if user_role == 'TEACHER' else None

    sessions = AttendanceSession.objects.select_related(
        'class_offering__grade',
        'class_offering__section',
        'class_offering__stream',
        'academic_year',
        'subject',
        'recorded_by'
    ).order_by('-date', '-created_at')

    # Teachers only see their assigned offerings
    if user_role == 'TEACHER' and teacher_profile:
        assigned_offering_ids = TeacherAssignment.objects.filter(
            teacher=teacher_profile
        ).values_list('class_offering_id', flat=True)
        sessions = sessions.filter(class_offering_id__in=assigned_offering_ids)

    # Filter parsing
    form = AttendanceFilterForm(request.GET)
    if form.is_valid():
        ay = form.cleaned_data.get('academic_year')
        grade = form.cleaned_data.get('grade')
        class_offering = form.cleaned_data.get('class_offering')
        date_from = form.cleaned_data.get('date_from')
        date_to = form.cleaned_data.get('date_to')
        status = form.cleaned_data.get('status')
        session_type = form.cleaned_data.get('session_type')

        if ay:
            sessions = sessions.filter(academic_year=ay)
        if grade:
            sessions = sessions.filter(class_offering__grade=grade)
        if class_offering:
            sessions = sessions.filter(class_offering=class_offering)
        if date_from:
            sessions = sessions.filter(date__gte=date_from)
        if date_to:
            sessions = sessions.filter(date__lte=date_to)
        if status:
            sessions = sessions.filter(status=status)
        if session_type:
            sessions = sessions.filter(session_type=session_type)

    paginator = Paginator(sessions, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'active_menu': 'attendance',
        'page_title': 'Attendance Sessions Directory',
        'filter_form': form,
        'page_obj': page_obj,
        'sessions': page_obj,
        'user_role': user_role,
        'can_create': user_role in ('TEACHER', 'REGISTRAR', 'ADMIN'),
    }
    return render(request, 'attendance/session_list.html', context)


# -----------------------------------------------------------------------------
# 3. CREATE ATTENDANCE SESSION
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def attendance_session_create_view(request):
    """
    Schedules/initiates a new attendance session.
    After creation, immediately routes to the Take Attendance roll-call page.
    """
    user_role = _get_user_role(request.user)
    if user_role not in ('TEACHER', 'REGISTRAR', 'ADMIN'):
        raise PermissionDenied("You do not have permission to initiate attendance sessions.")

    teacher_profile = getattr(request.user, 'teacher_profile', None) if user_role == 'TEACHER' else None
    current_year = AcademicYear.objects.filter(is_current=True).first()

    if request.method == 'POST':
        form = AttendanceSessionCreateForm(
            request.POST,
            user=request.user,
            academic_year=current_year
        )
        if form.is_valid():
            class_offering = form.cleaned_data['class_offering']
            session_date = form.cleaned_data['date']
            session_type = form.cleaned_data['session_type']
            subject = form.cleaned_data.get('subject')
            remarks = form.cleaned_data.get('remarks', '')

            # Determine who conducted the roll call
            recorded_by = teacher_profile
            if not recorded_by and user_role in ('ADMIN', 'REGISTRAR'):
                # Check if a primary teacher is assigned to this offering
                primary_assignment = TeacherAssignment.objects.filter(
                    class_offering=class_offering
                ).first()
                if primary_assignment:
                    recorded_by = primary_assignment.teacher

            try:
                session = AttendanceSessionService.create_session(
                    class_offering=class_offering,
                    session_date=session_date,
                    session_type=session_type,
                    subject=subject,
                    recorded_by=recorded_by,
                    created_by=request.user,
                    remarks=remarks,
                    request=request
                )
                messages.success(
                    request,
                    f"Attendance session for {class_offering.display_name} on {session_date} opened. Please proceed with student roll call."
                )
                return redirect('attendance_take', session_id=session.id)
            except ValidationError as e:
                form.add_error(None, e.message if hasattr(e, 'message') else str(e))
    else:
        # Pre-select class offering if passed in GET param
        initial_data = {}
        offering_id = request.GET.get('class_offering')
        if offering_id:
            initial_data['class_offering'] = offering_id
        form = AttendanceSessionCreateForm(
            user=request.user,
            academic_year=current_year,
            initial=initial_data
        )

    context = {
        'active_menu': 'attendance',
        'page_title': 'Initiate Attendance Session',
        'form': form,
        'user_role': user_role,
    }
    return render(request, 'attendance/session_create.html', context)


# -----------------------------------------------------------------------------
# 4. TAKE / RECORD ATTENDANCE (ROLL-CALL GRID)
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def attendance_take_view(request, session_id):
    """
    Interactive roll-call sheet.
    Teachers and staff mark Present / Absent / Late / Excused with optional notes.
    """
    session = get_object_or_404(
        AttendanceSession.objects.select_related(
            'class_offering__grade',
            'class_offering__section',
            'class_offering__stream',
            'academic_year',
            'subject',
            'recorded_by'
        ),
        pk=session_id
    )

    user_role = _get_user_role(request.user)
    teacher_profile = getattr(request.user, 'teacher_profile', None) if user_role == 'TEACHER' else None

    # Teacher permission verification: must be assigned to this classroom
    if user_role == 'TEACHER':
        if not _is_teacher_assigned_to_class(teacher_profile, session.class_offering):
            raise PermissionDenied("You can only take attendance for classrooms assigned to you.")

    # Closed session check: locked from standard edits
    if session.is_closed:
        messages.warning(
            request,
            f"This attendance session ({session.date}) is closed and locked from modifications."
        )
        return redirect('attendance_session_detail', session_id=session.id)

    # Fetch active enrolled students in this classroom
    enrollments = StudentEnrollment.objects.filter(
        class_offering=session.class_offering,
        status='ACTIVE'
    ).select_related('student').order_by('student__first_name', 'student__father_name')

    # Load existing marks into a map: {enrollment_id: AttendanceRecord}
    existing_records = {
        r.student_enrollment_id: r
        for r in AttendanceRecord.objects.filter(attendance_session=session)
    }

    if request.method == 'POST':
        # Process bulk student attendance
        records_data = []
        for enr in enrollments:
            status_key = f"status_{enr.id}"
            reason_key = f"reason_{enr.id}"

            # Only accept status if submitted
            if status_key in request.POST:
                status_val = request.POST.get(status_key, 'PRESENT')
                reason_val = request.POST.get(reason_key, '')
                records_data.append({
                    'enrollment_id': enr.id,
                    'status': status_val,
                    'reason': reason_val,
                })

        if not records_data:
            messages.error(request, "No student attendance marks were submitted. Please check the student rows.")
        else:
            result = AttendanceRecordService.record_bulk_attendance(
                session=session,
                records_data=records_data,
                recorded_by_user=request.user,
                request=request
            )
            messages.success(
                request,
                f"Attendance saved successfully: {result['summary']['PRESENT']} Present, "
                f"{result['summary']['ABSENT']} Absent, {result['summary']['LATE']} Late, "
                f"{result['summary']['EXCUSED']} Excused."
            )
            return redirect('attendance_session_detail', session_id=session.id)

    # Prepare list with pre-filled status
    student_rows = []
    for enr in enrollments:
        rec = existing_records.get(enr.id)
        student_rows.append({
            'enrollment': enr,
            'student': enr.student,
            'status': rec.status if rec else 'PRESENT',
            'reason': rec.reason if rec else '',
            'has_existing': rec is not None,
        })

    context = {
        'active_menu': 'attendance',
        'page_title': f"Take Attendance: {session.class_offering.display_name}",
        'session': session,
        'student_rows': student_rows,
        'total_students': len(student_rows),
        'user_role': user_role,
        'can_close': user_role in ('ADMIN', 'REGISTRAR', 'PRINCIPAL'),
    }
    return render(request, 'attendance/take_attendance.html', context)


# -----------------------------------------------------------------------------
# 5. ATTENDANCE SESSION DETAIL
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def attendance_session_detail_view(request, session_id):
    """
    Displays roll-call summary, student roster status breakdown, and administrative actions.
    """
    session = get_object_or_404(
        AttendanceSession.objects.select_related(
            'class_offering__grade',
            'class_offering__section',
            'class_offering__stream',
            'academic_year',
            'subject',
            'recorded_by'
        ),
        pk=session_id
    )

    user_role = _get_user_role(request.user)
    teacher_profile = getattr(request.user, 'teacher_profile', None) if user_role == 'TEACHER' else None

    if user_role == 'TEACHER':
        if not _is_teacher_assigned_to_class(teacher_profile, session.class_offering):
            raise PermissionDenied("You do not have access to attendance for this classroom.")

    records = AttendanceRecord.objects.filter(
        attendance_session=session
    ).select_related('student_enrollment__student', 'recorded_by').order_by(
        'student_enrollment__student__first_name',
        'student_enrollment__student__father_name'
    )

    # Calculate status totals
    total = records.count()
    present = records.filter(status='PRESENT').count()
    absent = records.filter(status='ABSENT').count()
    late = records.filter(status='LATE').count()
    excused = records.filter(status='EXCUSED').count()
    rate = round(((present + late) / total * 100), 1) if total > 0 else 0.0

    context = {
        'active_menu': 'attendance',
        'page_title': f"Attendance Session - {session.date}",
        'session': session,
        'records': records,
        'total': total,
        'present': present,
        'absent': absent,
        'late': late,
        'excused': excused,
        'rate': rate,
        'user_role': user_role,
        'can_edit': session.is_editable and (user_role in ('ADMIN', 'REGISTRAR') or _is_teacher_assigned_to_class(teacher_profile, session.class_offering)),
        'can_close': user_role in ('ADMIN', 'REGISTRAR', 'PRINCIPAL') and not session.is_closed,
        'can_reopen': user_role in ('ADMIN', 'REGISTRAR') and session.is_closed,
    }
    return render(request, 'attendance/session_detail.html', context)


# -----------------------------------------------------------------------------
# 6. CLOSE / REOPEN ATTENDANCE SESSION
# -----------------------------------------------------------------------------

@require_POST
@management_staff_required
def attendance_session_close_view(request, session_id):
    """Locks a completed session to protect historical integrity."""
    session = get_object_or_404(AttendanceSession, pk=session_id)
    AttendanceSessionService.close_session(session, user=request.user, request=request)
    messages.success(request, f"Attendance session for {session.class_offering} on {session.date} has been closed and locked.")
    return redirect('attendance_session_detail', session_id=session.id)


@require_POST
@principal_or_registrar_required
def attendance_session_reopen_view(request, session_id):
    """Reopens a locked session for administrative corrections."""
    session = get_object_or_404(AttendanceSession, pk=session_id)
    try:
        AttendanceSessionService.reopen_session(session, user=request.user, request=request)
        messages.success(request, f"Attendance session for {session.class_offering} on {session.date} has been reopened for editing.")
    except ValidationError as e:
        messages.error(request, str(e))
    return redirect('attendance_session_detail', session_id=session.id)


# -----------------------------------------------------------------------------
# 7. ATTENDANCE HISTORY
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def attendance_history_view(request):
    """
    Searchable audit history of individual student attendance marks across time.
    """
    user_role = _get_user_role(request.user)
    teacher_profile = getattr(request.user, 'teacher_profile', None) if user_role == 'TEACHER' else None

    records = AttendanceRecord.objects.select_related(
        'student_enrollment__student',
        'attendance_session__class_offering__grade',
        'attendance_session__class_offering__section',
        'attendance_session__subject',
        'attendance_session__recorded_by'
    ).order_by('-attendance_session__date', '-created_at')

    # Teacher visibility constraint
    if user_role == 'TEACHER' and teacher_profile:
        assigned_offering_ids = TeacherAssignment.objects.filter(
            teacher=teacher_profile
        ).values_list('class_offering_id', flat=True)
        records = records.filter(attendance_session__class_offering_id__in=assigned_offering_ids)

    # Search & filters
    search_q = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if search_q:
        records = records.filter(
            Q(student_enrollment__student__first_name__icontains=search_q) |
            Q(student_enrollment__student__father_name__icontains=search_q) |
            Q(student_enrollment__student__admission_number__icontains=search_q)
        )
    if status_filter:
        records = records.filter(status=status_filter)
    if date_from:
        records = records.filter(attendance_session__date__gte=date_from)
    if date_to:
        records = records.filter(attendance_session__date__lte=date_to)

    paginator = Paginator(records, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'active_menu': 'attendance',
        'page_title': 'Attendance History Log',
        'page_obj': page_obj,
        'records': page_obj,
        'search_q': search_q,
        'status_filter': status_filter,
        'date_from': date_from,
        'date_to': date_to,
        'user_role': user_role,
    }
    return render(request, 'attendance/history.html', context)


# -----------------------------------------------------------------------------
# 8. STUDENT ATTENDANCE DETAILS
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def student_attendance_detail_view(request, student_id):
    """
    Dedicated longitudinal attendance profile for a specific student.
    Preserves historical attendance records across academic years.
    """
    student = get_object_or_404(Student, pk=student_id)
    user_role = _get_user_role(request.user)

    # Optional academic year filter
    ay_id = request.GET.get('academic_year')
    selected_year = None
    if ay_id:
        selected_year = AcademicYear.objects.filter(pk=ay_id).first()

    summary = AttendanceAnalyticsService.get_student_summary(student, academic_year=selected_year)
    academic_years = AcademicYear.objects.all().order_by('-start_date')

    context = {
        'active_menu': 'attendance',
        'page_title': f"Attendance Profile: {student.full_name}",
        'student': student,
        'summary': summary,
        'academic_years': academic_years,
        'selected_year': selected_year,
        'user_role': user_role,
    }
    return render(request, 'attendance/student_attendance.html', context)


# -----------------------------------------------------------------------------
# 9. ATTENDANCE REPORTS
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def attendance_reports_view(request):
    """
    Multi-faceted attendance reporting view with summaries across classes, grades, and dates.
    """
    user_role = _get_user_role(request.user)
    current_year = AcademicYear.objects.filter(is_current=True).first()
    report_type = request.GET.get('type', 'daily')  # 'daily', 'class', 'grade', 'monthly'

    # Filter params
    selected_date = request.GET.get('date', timezone.now().date().isoformat())
    selected_grade_id = request.GET.get('grade')
    selected_offering_id = request.GET.get('class_offering')

    try:
        report_date = date.fromisoformat(selected_date)
    except ValueError:
        report_date = timezone.now().date()

    classes_summary = []
    offerings_qs = ClassOffering.objects.filter(
        academic_year=current_year
    ).select_related('grade', 'section', 'stream').order_by('grade__level', 'section__name')

    if selected_grade_id:
        offerings_qs = offerings_qs.filter(grade_id=selected_grade_id)
    if selected_offering_id:
        offerings_qs = offerings_qs.filter(id=selected_offering_id)

    for off in offerings_qs:
        s_data = AttendanceAnalyticsService.get_class_summary(off)
        classes_summary.append(s_data)

    grades = Grade.objects.filter(is_active=True).order_by('level')

    context = {
        'active_menu': 'reports_attendance',
        'page_title': 'Attendance Reports & Analytics',
        'report_type': report_type,
        'report_date': report_date,
        'selected_grade_id': selected_grade_id,
        'selected_offering_id': selected_offering_id,
        'classes_summary': classes_summary,
        'grades': grades,
        'offerings': offerings_qs,
        'current_year': current_year,
        'user_role': user_role,
    }
    return render(request, 'attendance/reports.html', context)


# -----------------------------------------------------------------------------
# 10. EXCEL AND PDF EXPORTS
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def attendance_export_excel_view(request):
    """Exports attendance report data as an Excel (.xlsx) spreadsheet."""
    report_type = request.GET.get('type', 'class_summary')
    session_id = request.GET.get('session_id')

    if session_id:
        session = get_object_or_404(AttendanceSession, pk=session_id)
        records = AttendanceRecord.objects.filter(attendance_session=session).select_related(
            'student_enrollment__student'
        )
        data = {'session': session, 'records': records}
        filename = f"Attendance_{session.class_offering.grade.name}_{session.class_offering.section.name}_{session.date}.xlsx"
        return AttendanceExportService.export_excel('session', data, filename=filename)

    # Class summary export
    current_year = AcademicYear.objects.filter(is_current=True).first()
    offerings = ClassOffering.objects.filter(academic_year=current_year).select_related('grade', 'section')
    classes_data = [AttendanceAnalyticsService.get_class_summary(o) for o in offerings]
    filename = f"School_Attendance_Summary_{timezone.now().strftime('%Y%m%d')}.xlsx"
    return AttendanceExportService.export_excel('class_summary', {'classes': classes_data}, filename=filename)


@any_authenticated_role_required
def attendance_export_pdf_view(request):
    """Exports attendance report data as a print-ready PDF document."""
    report_type = request.GET.get('type', 'class_summary')
    session_id = request.GET.get('session_id')

    if session_id:
        session = get_object_or_404(AttendanceSession, pk=session_id)
        records = AttendanceRecord.objects.filter(attendance_session=session).select_related(
            'student_enrollment__student'
        )
        data = {'session': session, 'records': records}
        filename = f"Attendance_{session.class_offering.grade.name}_{session.class_offering.section.name}_{session.date}.pdf"
        return AttendanceExportService.export_pdf('session', data, filename=filename)

    # Class summary export
    current_year = AcademicYear.objects.filter(is_current=True).first()
    offerings = ClassOffering.objects.filter(academic_year=current_year).select_related('grade', 'section')
    classes_data = [AttendanceAnalyticsService.get_class_summary(o) for o in offerings]
    filename = f"School_Attendance_Summary_{timezone.now().strftime('%Y%m%d')}.pdf"
    return AttendanceExportService.export_pdf('class_summary', {'classes': classes_data}, filename=filename)


# -----------------------------------------------------------------------------
# 11. ATTENDANCE ALERTS & EARLY WARNINGS
# -----------------------------------------------------------------------------

@management_staff_required
def attendance_alerts_view(request):
    """
    Early warning alert panel for chronic absenteeism, consecutive unexcused absences,
    and classrooms with missing roll calls today.
    """
    user_role = _get_user_role(request.user)
    current_year = AcademicYear.objects.filter(is_current=True).first()

    threshold = float(request.GET.get('threshold', 75.0))
    consecutive_days = int(request.GET.get('consecutive', 3))

    alerts = AttendanceAnalyticsService.get_attendance_alerts(
        academic_year=current_year,
        threshold_pct=threshold,
        consecutive_days=consecutive_days
    )

    context = {
        'active_menu': 'attendance',
        'page_title': 'Attendance Early Warning & Alerts',
        'alerts': alerts,
        'user_role': user_role,
        'current_year': current_year,
        'threshold': threshold,
        'consecutive_days': consecutive_days,
    }
    return render(request, 'attendance/alerts.html', context)
