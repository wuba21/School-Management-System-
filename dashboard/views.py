"""
Dashboard View Controller for SSMS.

Orchestrates data from DashboardService to deliver:
  - School-wide overview cards
  - Role-customized analytics (Principal, Registrar, Teacher, Administrator)
  - Interactive Chart.js JSON payloads
  - Safe empty states when database tables contain zero records
"""

import json
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from accounts.decorators import any_authenticated_role_required
from dashboard.services import DashboardService


@any_authenticated_role_required
def dashboard_view(request):
    """
    Renders the database-connected, role-aware dashboard for all staff.
    """
    user = request.user

    # 1. Gather all analytics modules via DashboardService
    kpis = DashboardService.get_overview_kpis(user)
    student_analytics = DashboardService.get_student_analytics()
    attendance_analytics = DashboardService.get_attendance_analytics()
    academic_analytics = DashboardService.get_academic_analytics()
    role_context = DashboardService.get_role_specific_context(user)
    recent_activities = DashboardService.get_recent_activities(user)

    # 2. Serialize chart data to JSON for secure client-side Chart.js hydration
    chart_payload = {
        'gradeLabels': student_analytics['grade_labels'],
        'gradeCounts': student_analytics['grade_counts'],
        'genderMale': student_analytics['gender_male'],
        'genderFemale': student_analytics['gender_female'],
        'attendanceLabels': attendance_analytics['trend_labels'],
        'attendanceRates': attendance_analytics['trend_rates'],
        'subjectNames': academic_analytics['subject_names'],
        'subjectAverages': academic_analytics['subject_averages'],
        'hasStudentData': student_analytics['has_student_data'],
        'hasAttendanceData': attendance_analytics['has_attendance_data'],
        'hasAcademicData': academic_analytics['has_academic_data'],
    }

    context = {
        'active_menu': 'dashboard',
        'page_title': 'Executive Dashboard & Analytics',
        'kpis': kpis,
        'student_analytics': student_analytics,
        'attendance_analytics': attendance_analytics,
        'academic_analytics': academic_analytics,
        'role_context': role_context,
        'recent_activities': recent_activities,
        'chart_payload_json': json.dumps(chart_payload),
    }

    return render(request, 'dashboard.html', context)
