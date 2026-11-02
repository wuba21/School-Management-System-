from django.shortcuts import render

def login_view(request):
    """
    Renders the professional login page UI.
    """
    return render(request, 'login.html')

def dashboard_view(request):
    """
    Renders the main school administration dashboard with KPI metrics and Chart.js previews.
    """
    context = {
        'active_menu': 'dashboard',
    }
    return render(request, 'dashboard.html', context)

def students_list_view(request):
    """
    Renders the student directory and enrollment list preview.
    """
    context = {
        'active_menu': 'students',
    }
    return render(request, 'students.html', context)

def teachers_list_view(request):
    """
    Renders the teacher directory and workload allocation preview.
    """
    context = {
        'active_menu': 'teachers',
    }
    return render(request, 'teachers.html', context)

def academics_years_view(request):
    """
    Renders the academic calendar and year status preview.
    """
    context = {
        'active_menu': 'academics_years',
    }
    return render(request, 'academics.html', context)

def academics_grades_view(request):
    """
    Renders grade levels, sections, and stream offerings.
    """
    context = {
        'active_menu': 'academics_grades',
    }
    return render(request, 'academics.html', context)

def academics_subjects_view(request):
    """
    Renders the master subject catalog.
    """
    context = {
        'active_menu': 'academics_subjects',
        'module_title': 'Subject Management',
        'module_description': 'Master subject catalog, weekly period allocations, and curriculum stream mappings.',
        'module_icon': 'bi-book-half',
        'action_btn': 'Add New Subject',
    }
    return render(request, 'system_module.html', context)

def attendance_index_view(request):
    """
    Renders the daily and period attendance tracking sheet.
    """
    context = {
        'active_menu': 'attendance',
    }
    return render(request, 'attendance.html', context)

def examinations_index_view(request):
    """
    Renders the examination cycles and assessment weight setup.
    """
    context = {
        'active_menu': 'examinations',
    }
    return render(request, 'examinations.html', context)

def results_index_view(request):
    """
    Renders examination mark entry and results processing preview.
    """
    context = {
        'active_menu': 'results',
    }
    return render(request, 'results.html', context)

def promotion_index_view(request):
    """
    Renders student promotion evaluation and academic progression hub.
    """
    context = {
        'active_menu': 'promotion',
        'module_title': 'Student Promotion Management',
        'module_description': 'End-of-year candidate evaluation, minimum passing thresholds, and Principal review.',
        'module_icon': 'bi-arrow-up-right-circle-fill',
        'action_btn': 'Process Promotion Candidates',
    }
    return render(request, 'system_module.html', context)

def timetable_index_view(request):
    """
    Renders section and teacher weekly schedule builder.
    """
    context = {
        'active_menu': 'timetable',
        'module_title': 'Timetable & Scheduling',
        'module_description': 'Weekly class period schedules, classroom allocation, and teacher conflict detection.',
        'module_icon': 'bi-clock-history',
        'action_btn': 'Generate Timetable Grid',
    }
    return render(request, 'system_module.html', context)

def reports_students_view(request):
    """
    Renders student report cards and transcript generation hub.
    """
    context = {
        'active_menu': 'reports_students',
    }
    return render(request, 'reports.html', context)

def reports_academic_view(request):
    """
    Renders master class broadsheets and school-wide grade distributions.
    """
    context = {
        'active_menu': 'reports_academic',
    }
    return render(request, 'reports.html', context)

def reports_attendance_view(request):
    """
    Renders monthly and semester attendance rate summaries.
    """
    context = {
        'active_menu': 'reports_attendance',
    }
    return render(request, 'reports.html', context)

def ai_assistant_chat_view(request):
    """
    Renders the offline conversational AI assistant.
    """
    context = {
        'active_menu': 'ai_assistant',
    }
    return render(request, 'ai_assistant.html', context)

def ai_analytics_view(request):
    """
    Renders academic performance forecasting and early-warning signals.
    """
    context = {
        'active_menu': 'ai_analytics',
        'module_title': 'AI Academic Performance Analytics',
        'module_description': 'Scikit-learn predictive modeling to forecast student pass rates and detect at-risk students.',
        'module_icon': 'bi-graph-up-arrow',
        'action_btn': 'Run Model Training Pipeline',
    }
    return render(request, 'system_module.html', context)

def system_users_view(request):
    """
    Renders user account management and RBAC role assignments.
    """
    context = {
        'active_menu': 'system_users',
        'module_title': 'User Management & Access Control',
        'module_description': 'System roles: Principal, Registrar, Teacher, and System Administrator.',
        'module_icon': 'bi-people-fill',
        'action_btn': 'Add System User',
    }
    return render(request, 'system_module.html', context)

def system_settings_view(request):
    """
    Renders school system configuration and LAN network parameters.
    """
    context = {
        'active_menu': 'system_settings',
        'module_title': 'System & Network Settings',
        'module_description': 'Server LAN IP address, automated backup schedules, and institutional metadata.',
        'module_icon': 'bi-gear-fill',
        'action_btn': 'Save Configuration',
    }
    return render(request, 'system_module.html', context)

def system_audit_view(request):
    """
    Renders immutable audit logs and activity tracking.
    """
    context = {
        'active_menu': 'system_audit',
        'module_title': 'Security Audit Trail',
        'module_description': 'Immutable activity logs capturing IP addresses, timestamps, and mark edits.',
        'module_icon': 'bi-shield-lock-fill',
        'action_btn': 'Export Audit Log Archive',
    }
    return render(request, 'system_module.html', context)
