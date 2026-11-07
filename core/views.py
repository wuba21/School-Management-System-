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
    context = {
        'active_menu': 'system_settings',
        'page_title': 'System Settings',
        'module_title': 'System & Network Settings',
        'module_description': (
            'Server LAN IP address, automated backup schedules, '
            'and institutional metadata.'
        ),
        'module_icon': 'bi-gear-fill',
        'action_btn': 'Save Configuration',
    }
    return render(request, 'system_module.html', context)


@sysadmin_required
def system_audit_view(request):
    """
    Immutable audit logs and activity tracking.
    Only System Administrators can review security audit trails.
    """
    from core.models import AuditLog
    logs = AuditLog.objects.select_related('actor').order_by('-timestamp')[:200]
    context = {
        'active_menu': 'system_audit',
        'page_title': 'Security Audit Trail',
        'module_title': 'Security Audit Trail',
        'module_description': (
            'Immutable activity logs capturing IP addresses, timestamps, '
            'and mark edits.'
        ),
        'module_icon': 'bi-shield-lock-fill',
        'action_btn': 'Export Audit Log Archive',
        'audit_logs': logs,
    }
    return render(request, 'system_module.html', context)
