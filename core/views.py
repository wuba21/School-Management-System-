"""
Core views for SSMS.

All views below are protected:
  - @login_required              : any authenticated user can view
  - @any_authenticated_role_required : user must have an assigned role
  - @management_staff_required   : Principal / Registrar / Admin only
  - @sysadmin_required           : System Administrator only
  - @principal_or_registrar_required : Principal or Registrar

Teachers see their own module views but cannot access admin-only routes.
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required

from accounts.decorators import (
    any_authenticated_role_required,
    management_staff_required,
    principal_or_registrar_required,
    sysadmin_required,
    teacher_required,
    principal_required,
    registrar_required,
)
from dashboard.views import dashboard_view
from students.views import student_list_view as students_list_view


# ---------------------------------------------------------------------------
# STUDENT MANAGEMENT  — Moved to students app (students.views.student_list_view)
# ---------------------------------------------------------------------------
# students_list_view is imported above from students.views.student_list_view


# ---------------------------------------------------------------------------
# TEACHER MANAGEMENT  — Principal, Registrar, Admin
# ---------------------------------------------------------------------------

# Re-export from teachers app for backwards compatibility
from teachers.views import teacher_list_view as teachers_list_view
# Re-export from academics app for backwards compatibility
from academics.views import (
    academic_year_list_view as academics_years_view,
    grades_sections_view as academics_grades_view,
    subject_list_view as academics_subjects_view,
)




# ---------------------------------------------------------------------------
# ATTENDANCE  — Teachers (own classes), Principal/Registrar/Admin (all)
# ---------------------------------------------------------------------------

@any_authenticated_role_required
def attendance_index_view(request):
    """
    Daily and period attendance tracking sheet.
    Teachers see only their assigned classes (enforced in next step).
    """
    context = {
        'active_menu': 'attendance',
        'page_title': 'Attendance',
    }
    return render(request, 'attendance.html', context)


# ---------------------------------------------------------------------------
# EXAMINATIONS  — All staff
# ---------------------------------------------------------------------------

@any_authenticated_role_required
def examinations_index_view(request):
    """
    Examination cycles and assessment weight setup.
    """
    context = {
        'active_menu': 'examinations',
        'page_title': 'Examinations',
    }
    return render(request, 'examinations.html', context)


# ---------------------------------------------------------------------------
# RESULTS  — Teacher (own subjects), Registrar/Principal/Admin (all)
# ---------------------------------------------------------------------------

@any_authenticated_role_required
def results_index_view(request):
    """
    Examination mark entry and results processing.
    """
    context = {
        'active_menu': 'results',
        'page_title': 'Results',
    }
    return render(request, 'results.html', context)


# ---------------------------------------------------------------------------
# PROMOTION  — Principal, Registrar, Admin
# ---------------------------------------------------------------------------

@management_staff_required
def promotion_index_view(request):
    """
    Student promotion evaluation and academic progression hub.
    """
    context = {
        'active_menu': 'promotion',
        'page_title': 'Promotion Management',
        'module_title': 'Student Promotion Management',
        'module_description': (
            'End-of-year candidate evaluation, minimum passing thresholds, '
            'and Principal review.'
        ),
        'module_icon': 'bi-arrow-up-right-circle-fill',
        'action_btn': 'Process Promotion Candidates',
    }
    return render(request, 'system_module.html', context)


# ---------------------------------------------------------------------------
# TIMETABLE  — All staff (read); Admin/Registrar (edit)
# ---------------------------------------------------------------------------

@any_authenticated_role_required
def timetable_index_view(request):
    """
    Section and teacher weekly schedule builder.
    """
    context = {
        'active_menu': 'timetable',
        'page_title': 'Timetable & Scheduling',
        'module_title': 'Timetable & Scheduling',
        'module_description': (
            'Weekly class period schedules, classroom allocation, '
            'and teacher conflict detection.'
        ),
        'module_icon': 'bi-clock-history',
        'action_btn': 'Generate Timetable Grid',
    }
    return render(request, 'system_module.html', context)


# ---------------------------------------------------------------------------
# REPORTS  — Principal, Registrar, Admin
# ---------------------------------------------------------------------------

@principal_or_registrar_required
def reports_students_view(request):
    """
    Student report cards and transcript generation hub.
    """
    context = {
        'active_menu': 'reports_students',
        'page_title': 'Student Reports',
    }
    return render(request, 'reports.html', context)


@principal_or_registrar_required
def reports_academic_view(request):
    """
    Master class broadsheets and school-wide grade distributions.
    """
    context = {
        'active_menu': 'reports_academic',
        'page_title': 'Academic Reports',
    }
    return render(request, 'reports.html', context)


@principal_or_registrar_required
def reports_attendance_view(request):
    """
    Monthly and semester attendance rate summaries.
    """
    context = {
        'active_menu': 'reports_attendance',
        'page_title': 'Attendance Reports',
    }
    return render(request, 'reports.html', context)


# ---------------------------------------------------------------------------
# AI ASSISTANT  — All authenticated staff
# ---------------------------------------------------------------------------

@any_authenticated_role_required
def ai_assistant_chat_view(request):
    """
    Offline conversational AI assistant.
    """
    context = {
        'active_menu': 'ai_assistant',
        'page_title': 'AI School Assistant',
    }
    return render(request, 'ai_assistant.html', context)


@management_staff_required
def ai_analytics_view(request):
    """
    Academic performance forecasting and early-warning signals.
    Advisory only — AI cannot make promotion decisions.
    """
    context = {
        'active_menu': 'ai_analytics',
        'page_title': 'AI Academic Analytics',
        'module_title': 'AI Academic Performance Analytics',
        'module_description': (
            'Scikit-learn predictive modeling to forecast student pass rates '
            'and detect at-risk students.'
        ),
        'module_icon': 'bi-graph-up-arrow',
        'action_btn': 'Run Model Training Pipeline',
    }
    return render(request, 'system_module.html', context)


# ---------------------------------------------------------------------------
# SYSTEM ADMINISTRATION  — System Administrator only
# ---------------------------------------------------------------------------

@sysadmin_required
def system_users_view(request):
    """
    Redirect legacy /users/ route to the accounts user_list view.
    """
    from django.shortcuts import redirect
    return redirect('user_list')


@sysadmin_required
def system_settings_view(request):
    """
    School system configuration and LAN network parameters.
    """
    import os
    from django.conf import settings

    context = {
        'active_menu': 'system_settings',
        'page_title': 'System & Infrastructure Settings',
        'lan_ip': os.getenv('LAN_SERVER_IP', '192.168.1.100'),
        'db_engine': os.getenv('DB_ENGINE', 'sqlite3').lower(),
        'login_max_attempts': getattr(settings, 'LOGIN_MAX_ATTEMPTS', 5),
    }
    return render(request, 'core/system_settings.html', context)


@sysadmin_required
def system_audit_view(request):
    """
    Full audit log viewer with filtering and pagination.
    Only System Administrators can review security audit trails.
    """
    from django.core.paginator import Paginator
    from core.models import AuditLog

    logs = AuditLog.objects.select_related('actor').order_by('-timestamp')

    # ── Filters ─────────────────────────────────────────────────────────────
    action_filter = request.GET.get('action', '').strip()
    actor_filter = request.GET.get('actor', '').strip()
    ip_filter = request.GET.get('ip', '').strip()
    entity_filter = request.GET.get('entity', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if action_filter:
        logs = logs.filter(action=action_filter)
    if actor_filter:
        logs = logs.filter(actor__username__icontains=actor_filter)
    if ip_filter:
        logs = logs.filter(ip_address__icontains=ip_filter)
    if entity_filter:
        logs = logs.filter(entity_name__icontains=entity_filter)
    if date_from:
        logs = logs.filter(timestamp__date__gte=date_from)
    if date_to:
        logs = logs.filter(timestamp__date__lte=date_to)

    # ── KPI summary (today) ──────────────────────────────────────────────────
    from django.utils import timezone
    from core.models import LoginAttempt
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    total_today = AuditLog.objects.filter(timestamp__gte=today_start).count()
    failed_logins_today = LoginAttempt.objects.filter(
        status=LoginAttempt.STATUS_FAILED,
        timestamp__gte=today_start,
    ).count()
    unique_ips_today = (
        AuditLog.objects
        .filter(timestamp__gte=today_start)
        .exclude(ip_address__isnull=True)
        .values('ip_address')
        .distinct()
        .count()
    )

    # ── Pagination ───────────────────────────────────────────────────────────
    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    action_choices = AuditLog.ACTION_CHOICES

    context = {
        'active_menu': 'system_audit',
        'page_title': 'Security Audit Trail',
        'page_obj': page_obj,
        'action_filter': action_filter,
        'actor_filter': actor_filter,
        'ip_filter': ip_filter,
        'entity_filter': entity_filter,
        'date_from': date_from,
        'date_to': date_to,
        'action_choices': action_choices,
        'total_today': total_today,
        'failed_logins_today': failed_logins_today,
        'unique_ips_today': unique_ips_today,
    }
    return render(request, 'core/audit_log.html', context)


@sysadmin_required
def audit_log_export_csv_view(request):
    """
    Export filtered audit logs as a downloadable CSV file.
    """
    import csv
    from django.http import HttpResponse
    from core.models import AuditLog

    logs = AuditLog.objects.select_related('actor').order_by('-timestamp')

    # Apply same filters as the viewer
    action_filter = request.GET.get('action', '').strip()
    actor_filter = request.GET.get('actor', '').strip()
    ip_filter = request.GET.get('ip', '').strip()
    entity_filter = request.GET.get('entity', '').strip()
    date_from = request.GET.get('date_from', '').strip()
    date_to = request.GET.get('date_to', '').strip()

    if action_filter:
        logs = logs.filter(action=action_filter)
    if actor_filter:
        logs = logs.filter(actor__username__icontains=actor_filter)
    if ip_filter:
        logs = logs.filter(ip_address__icontains=ip_filter)
    if entity_filter:
        logs = logs.filter(entity_name__icontains=entity_filter)
    if date_from:
        logs = logs.filter(timestamp__date__gte=date_from)
    if date_to:
        logs = logs.filter(timestamp__date__lte=date_to)

    # Limit to 10,000 rows for safety
    logs = logs[:10000]

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="ssms_audit_log.csv"'

    writer = csv.writer(response)
    writer.writerow(['Timestamp', 'Actor', 'Action', 'Entity', 'Record ID', 'IP Address', 'Changes'])

    for log in logs:
        writer.writerow([
            log.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            log.actor.username if log.actor else 'System',
            log.action,
            log.entity_name,
            log.record_id,
            log.ip_address or '',
            str(log.changes_json),
        ])

    return response

