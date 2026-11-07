"""
URL configuration for the Attendance Management System.
"""

from django.urls import path
from attendance import views

urlpatterns = [
    # Dashboard
    path('', views.attendance_dashboard_view, name='attendance_index'),

    # Sessions Management
    path('sessions/', views.attendance_session_list_view, name='attendance_sessions'),
    path('sessions/create/', views.attendance_session_create_view, name='attendance_session_create'),
    path('sessions/<int:session_id>/', views.attendance_session_detail_view, name='attendance_session_detail'),
    path('sessions/<int:session_id>/take/', views.attendance_take_view, name='attendance_take'),
    path('sessions/<int:session_id>/close/', views.attendance_session_close_view, name='attendance_session_close'),
    path('sessions/<int:session_id>/reopen/', views.attendance_session_reopen_view, name='attendance_session_reopen'),

    # Audit & History
    path('history/', views.attendance_history_view, name='attendance_history'),
    path('students/<int:student_id>/', views.student_attendance_detail_view, name='student_attendance_detail'),

    # Reporting & Exports
    path('reports/', views.attendance_reports_view, name='attendance_reports'),
    path('reports/view/', views.attendance_reports_view, name='reports_attendance'),
    path('export/excel/', views.attendance_export_excel_view, name='attendance_export_excel'),
    path('export/pdf/', views.attendance_export_pdf_view, name='attendance_export_pdf'),

    # Alerts & Early Warning
    path('alerts/', views.attendance_alerts_view, name='attendance_alerts'),
]
