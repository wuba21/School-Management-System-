"""
School Reports and Analytics Views for SSMS.
Integrates with role-based access control (RBAC), multi-dimensional filtering,
pagination, interactive Chart.js visualization, and ReportLab / OpenPyXL exports.
"""

import json
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, Http404
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.contrib import messages
from django.core.exceptions import PermissionDenied

from accounts.decorators import (
    any_authenticated_role_required,
    management_staff_required,
    principal_or_registrar_required,
)
from reports.forms import ReportFilterForm
from reports.services import (
    AnalyticsService,
    StudentReportService,
    TeacherReportService,
    AttendanceReportService,
    ExaminationPerformanceReportService,
    PromotionReportService,
    ReportExportService,
)
from students.models import Student
from teachers.models import Teacher


def _extract_cleaned_filters(request):
    """Helper to instantiate and validate ReportFilterForm from GET parameters."""
    form = ReportFilterForm(request.GET, teacher_user=request.user)
    filters = {}
    if form.is_valid():
        for field in [
            'academic_year', 'grade', 'class_offering', 'section',
            'stream', 'subject', 'examination', 'teacher',
            'date_from', 'date_to', 'search'
        ]:
            val = form.cleaned_data.get(field)
            if val:
                filters[field] = val
    return form, filters


# -----------------------------------------------------------------------------
# 1. MAIN SCHOOL ANALYTICS DASHBOARD
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def analytics_dashboard_view(request):
    """
    Centralized school analytics dashboard presenting real database KPIs,
    demographic breakdowns, attendance trends, exam broadsheets, and 8 Chart.js charts.
    """
    form, filters = _extract_cleaned_filters(request)
    stats = AnalyticsService.get_school_overview_stats(filters=filters, user=request.user)
    charts_payload = AnalyticsService.get_charts_payload(filters=filters, user=request.user)

    context = {
        'active_menu': 'reports_dashboard',
        'page_title': 'School Reports & Analytics Dashboard',
        'form': form,
        'filters': filters,
        'stats': stats,
        'charts_json': json.dumps(charts_payload),
        'user_role': request.user.role.code if request.user.role else 'STAFF',
    }
    return render(request, 'reports/dashboard.html', context)


# -----------------------------------------------------------------------------
# 2. STUDENT REPORTS
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def student_reports_view(request):
    """
    Student registration, enrollment, and academic roster report.
    Supports search by name / admission number, filters, and pagination.
    """
    form, filters = _extract_cleaned_filters(request)
    students_qs = StudentReportService.get_student_reports(filters=filters, user=request.user)

    paginator = Paginator(students_qs, 25)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        'active_menu': 'reports_students',
        'page_title': 'Student Reports & Registry',
        'form': form,
        'filters': filters,
        'page_obj': page_obj,
        'total_count': paginator.count,
    }
    return render(request, 'reports/student_reports.html', context)


@any_authenticated_role_required
def student_report_detail_view(request, student_id):
    """
    Detailed 360-degree student academic portfolio:
    Multi-year enrollments, subject scores, attendance percentage, and promotion history.
    """
    # Teacher role verification
    if request.user.role and request.user.role.code == 'TEACHER':
        if hasattr(request.user, 'teacher_profile'):
            teacher = request.user.teacher_profile
            teaches_student = Student.objects.filter(
                id=student_id,
                enrollments__class_offering__teacher_assignments__teacher=teacher
            ).exists()
            if not teaches_student:
                raise PermissionDenied("You are only permitted to view academic reports for students in your assigned classes.")

    data = StudentReportService.get_student_detail_report(student_id, user=request.user)
    context = {
        'active_menu': 'reports_students',
        'page_title': f"Student Portfolio: {data['student'].full_name}",
        'data': data,
    }
    return render(request, 'reports/student_detail_report.html', context)


# -----------------------------------------------------------------------------
# 3. TEACHER REPORTS
# -----------------------------------------------------------------------------

@management_staff_required
def teacher_reports_view(request):
    """
    Teacher staff report: employment status, subject allocations, assigned classes,
    and weekly scheduled period counts from published timetables.
    """
    form, filters = _extract_cleaned_filters(request)
    teacher_data = TeacherReportService.get_teacher_reports(filters=filters, user=request.user)

    context = {
        'active_menu': 'reports_teachers',
        'page_title': 'Teacher Staff & Workload Reports',
        'form': form,
        'filters': filters,
        'teacher_data': teacher_data,
        'total_teachers': len(teacher_data),
    }
    return render(request, 'reports/teacher_reports.html', context)


@any_authenticated_role_required
def teacher_report_detail_view(request, teacher_id):
    """
    Individual teacher report view showing assignments, contact details, and classes.
    """
    # If teacher, can only see own profile unless management
    if request.user.role and request.user.role.code == 'TEACHER':
        if not hasattr(request.user, 'teacher_profile') or request.user.teacher_profile.id != teacher_id:
            raise PermissionDenied("You may only view your own teacher workload report.")

    teacher = get_object_or_404(Teacher, pk=teacher_id)
    report_items = TeacherReportService.get_teacher_reports(filters={'teacher': teacher}, user=request.user)
    item = report_items[0] if report_items else None

    context = {
        'active_menu': 'reports_teachers',
        'page_title': f"Teacher Report: {teacher.full_name}",
        'teacher': teacher,
        'item': item,
    }
    return render(request, 'reports/teacher_detail_report.html', context)


# -----------------------------------------------------------------------------
# 4. ATTENDANCE REPORTS
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def attendance_reports_view(request):
    """
    Comprehensive school attendance reports:
    - Daily attendance breakdown with presence rates
    - Chronic absenteeism alerts (students missing 3+ sessions or with < 80% presence)
    """
    form, filters = _extract_cleaned_filters(request)
    data = AttendanceReportService.get_attendance_reports(filters=filters, user=request.user)

    context = {
        'active_menu': 'reports_attendance',
        'page_title': 'Attendance Reports & Absenteeism Review',
        'form': form,
        'filters': filters,
        'daily_summary': data['daily_summary'],
        'chronic_absentees': data['chronic_absentees'],
        'total_sessions_count': data['total_sessions_count'],
    }
    return render(request, 'reports/attendance_reports.html', context)


# -----------------------------------------------------------------------------
# 5. EXAMINATION & ACADEMIC PERFORMANCE REPORTS
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def examination_reports_view(request):
    """
    Examination completion and broad-sheet report:
    Sat counts, draft vs verified marks, averages, highest and lowest scores.
    """
    form, filters = _extract_cleaned_filters(request)
    exam_reports = ExaminationPerformanceReportService.get_examination_reports(filters=filters, user=request.user)

    context = {
        'active_menu': 'reports_examinations',
        'page_title': 'Examination Results & Completion Reports',
        'form': form,
        'filters': filters,
        'exam_reports': exam_reports,
    }
    return render(request, 'reports/examination_reports.html', context)


@management_staff_required
def academic_performance_reports_view(request):
    """
    Subject-level broadsheets, grade-level performance, and passing statistics.
    """
    form, filters = _extract_cleaned_filters(request)
    subject_reports = ExaminationPerformanceReportService.get_subject_performance_reports(filters=filters, user=request.user)

    context = {
        'active_menu': 'reports_academic',
        'page_title': 'Subject Performance & Academic Broadsheets',
        'form': form,
        'filters': filters,
        'subject_reports': subject_reports,
    }
    return render(request, 'reports/academic_performance.html', context)


# -----------------------------------------------------------------------------
# 6. PROMOTION & GRADUATION REPORTS
# -----------------------------------------------------------------------------

@management_staff_required
def promotion_reports_view(request):
    """
    End-of-year promotion outcomes, graduation registry, and cohort progression.
    """
    form, filters = _extract_cleaned_filters(request)
    data = PromotionReportService.get_promotion_reports(filters=filters, user=request.user)

    context = {
        'active_menu': 'reports_promotion',
        'page_title': 'Promotion & Graduation Analytics',
        'form': form,
        'filters': filters,
        'batch_summaries': data['batch_summaries'],
        'graduations': data['graduations'],
    }
    return render(request, 'reports/promotion_reports.html', context)


# -----------------------------------------------------------------------------
# 7. EXPORT CENTER (PDF & EXCEL DOWNLOADS)
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def export_center_view(request):
    """
    Centralized export dashboard allowing staff to download formatted PDF & Excel
    reports across all domains with active filters applied.
    """
    form, filters = _extract_cleaned_filters(request)
    context = {
        'active_menu': 'reports_exports',
        'page_title': 'Report Export Center',
        'form': form,
        'filters': filters,
    }
    return render(request, 'reports/export_center.html', context)


@any_authenticated_role_required
def export_report_pdf_view(request, report_type):
    """
    Streams publication-grade PDF report compiled with ReportLab.
    """
    form, filters = _extract_cleaned_filters(request)
    records = []
    title = f"{report_type.capitalize()} Report"

    if report_type == 'students':
        records = list(StudentReportService.get_student_reports(filters=filters, user=request.user)[:200])
        title = "Student Registry & Enrollment Report"
    elif report_type == 'teachers':
        if request.user.role and request.user.role.code == 'TEACHER':
            raise PermissionDenied("Teachers cannot export staff rosters.")
        records = TeacherReportService.get_teacher_reports(filters=filters, user=request.user)
        title = "Teacher Staff & Workload Report"
    elif report_type == 'attendance':
        data = AttendanceReportService.get_attendance_reports(filters=filters, user=request.user)
        records = data['daily_summary']
        title = "Attendance Daily Summary Report"
    elif report_type in ['examinations', 'academic']:
        records = ExaminationPerformanceReportService.get_subject_performance_reports(filters=filters, user=request.user)
        title = "Academic & Examination Performance Broadsheet"
    elif report_type == 'promotion':
        if request.user.role and request.user.role.code == 'TEACHER':
            raise PermissionDenied("Teachers cannot export promotion records.")
        data = PromotionReportService.get_promotion_reports(filters=filters, user=request.user)
        records = data['batch_summaries']
        title = "Student Promotion & Graduation Report"
    else:
        raise Http404("Invalid report type.")

    pdf_buffer = ReportExportService.export_pdf(
        report_type=report_type,
        context={'records': records},
        title=title
    )
    response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="SSMS_{report_type}_report.pdf"'
    return response


@any_authenticated_role_required
def export_report_excel_view(request, report_type):
    """
    Streams formatted Microsoft Excel workbook compiled with OpenPyXL.
    """
    form, filters = _extract_cleaned_filters(request)
    records = []
    title = f"{report_type.capitalize()} Report"

    if report_type == 'students':
        records = list(StudentReportService.get_student_reports(filters=filters, user=request.user)[:500])
        title = "Student Registry & Enrollment Report"
    elif report_type == 'teachers':
        if request.user.role and request.user.role.code == 'TEACHER':
            raise PermissionDenied("Teachers cannot export staff rosters.")
        records = TeacherReportService.get_teacher_reports(filters=filters, user=request.user)
        title = "Teacher Staff & Workload Report"
    elif report_type == 'attendance':
        data = AttendanceReportService.get_attendance_reports(filters=filters, user=request.user)
        records = data['daily_summary']
        title = "Attendance Daily Summary Report"
    elif report_type in ['examinations', 'academic']:
        records = ExaminationPerformanceReportService.get_subject_performance_reports(filters=filters, user=request.user)
        title = "Academic & Examination Performance Broadsheet"
    elif report_type == 'promotion':
        if request.user.role and request.user.role.code == 'TEACHER':
            raise PermissionDenied("Teachers cannot export promotion records.")
        data = PromotionReportService.get_promotion_reports(filters=filters, user=request.user)
        records = data['batch_summaries']
        title = "Student Promotion & Graduation Report"
    else:
        raise Http404("Invalid report type.")

    excel_buffer = ReportExportService.export_excel(
        report_type=report_type,
        context={'records': records},
        title=title
    )
    response = HttpResponse(
        excel_buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="SSMS_{report_type}_report.xlsx"'
    return response
