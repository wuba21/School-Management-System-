from django.shortcuts import render
from django.conf import settings

def home(request):
    """
    Renders the initial system status and diagnostic home page.
    """
    registered_apps = [
        {'name': 'core', 'description': 'Shared utilities, base templates, and common models.'},
        {'name': 'accounts', 'description': 'Custom user model, role definitions, and access control.'},
        {'name': 'students', 'description': 'Student personal profiles, registration, and class enrollments.'},
        {'name': 'teachers', 'description': 'Teacher profiles, qualifications, and teaching allocations.'},
        {'name': 'academics', 'description': 'Academic years, semesters, grades 9-12, sections, and subjects.'},
        {'name': 'attendance', 'description': 'Daily and period-based attendance tracking and absence alerts.'},
        {'name': 'examinations', 'description': 'Assessment structures, continuous assessments, and exam schedules.'},
        {'name': 'results', 'description': 'Mark entry, boundary validation, grading scales, and class rank computation.'},
        {'name': 'reports', 'description': 'Official printable PDF report cards, broadsheets, and student transcripts.'},
        {'name': 'dashboard', 'description': 'Role-tailored dashboards for Principal, Registrar, Teacher, and SysAdmin.'},
        {'name': 'ai_assistant', 'description': 'Machine learning performance analysis and offline school assistant.'},
    ]

    context = {
        'timezone': settings.TIME_ZONE,
        'registered_apps': registered_apps,
        'debug_mode': settings.DEBUG,
    }
    return render(request, 'home.html', context)
