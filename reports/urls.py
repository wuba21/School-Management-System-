"""
URL Configuration for SSMS Reports & Analytics Module.
"""

from django.urls import path
from reports import views

urlpatterns = [
    # 1. Main Analytics Dashboard
    path('', views.analytics_dashboard_view, name='reports_dashboard'),

    # 2. Student Reports
    path('students/', views.student_reports_view, name='reports_students'),
    path('students/<int:student_id>/', views.student_report_detail_view, name='student_report_detail'),

    # 3. Teacher Reports
    path('teachers/', views.teacher_reports_view, name='reports_teachers'),
    path('teachers/<int:teacher_id>/', views.teacher_report_detail_view, name='teacher_report_detail'),

    # 4. Attendance Reports
    path('attendance/', views.attendance_reports_view, name='reports_attendance'),

    # 5. Examination & Academic Reports
    path('examinations/', views.examination_reports_view, name='reports_examinations'),
    path('academic/', views.academic_performance_reports_view, name='reports_academic'),

    # 6. Promotion & Graduation Reports
    path('promotion/', views.promotion_reports_view, name='reports_promotion'),

    # 7. Export Center (PDF & Excel)
    path('exports/', views.export_center_view, name='reports_exports'),
    path('exports/pdf/<str:report_type>/', views.export_report_pdf_view, name='export_report_pdf'),
    path('exports/excel/<str:report_type>/', views.export_report_excel_view, name='export_report_excel'),
]
