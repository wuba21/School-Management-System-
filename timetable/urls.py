"""
URL patterns for Timetable and Class Scheduling Management System.
"""

from django.urls import path
from timetable import views

urlpatterns = [
    # Dashboard and Directory
    path('', views.timetable_dashboard_view, name='timetable_index'),
    path('dashboard/', views.timetable_dashboard_view, name='timetable_dashboard'),
    path('list/', views.timetable_list_view, name='timetable_list'),
    path('create/', views.timetable_create_view, name='timetable_create'),

    # Timetable Detail & Entries
    path('<int:timetable_id>/', views.timetable_detail_view, name='timetable_detail'),
    path('<int:timetable_id>/entries/add/', views.timetable_entry_create_view, name='timetable_entry_create'),
    path('entries/<int:entry_id>/delete/', views.timetable_entry_delete_view, name='timetable_entry_delete'),
    path('<int:timetable_id>/copy/', views.timetable_copy_view, name='timetable_copy'),

    # Review & Lifecycle Workflows
    path('<int:timetable_id>/submit/', views.timetable_submit_view, name='timetable_submit'),
    path('<int:timetable_id>/approve/', views.timetable_approval_view, name='timetable_approval'),
    path('<int:timetable_id>/publish/', views.timetable_publish_view, name='timetable_publish'),
    path('<int:timetable_id>/revise/', views.timetable_revise_view, name='timetable_revise'),

    # Teacher Timetable Views
    path('teachers/', views.teacher_timetable_view, name='teacher_timetable_default'),
    path('teachers/<int:teacher_id>/', views.teacher_timetable_view, name='teacher_timetable'),

    # Class Timetable Views
    path('classes/', views.class_timetable_view, name='class_timetable_default'),
    path('classes/<int:class_offering_id>/', views.class_timetable_view, name='class_timetable'),

    # Classroom Management
    path('classrooms/', views.classroom_list_view, name='classroom_list'),
    path('classrooms/create/', views.classroom_create_view, name='classroom_create'),
    path('classrooms/<int:room_id>/edit/', views.classroom_edit_view, name='classroom_edit'),
    path('classrooms/<int:room_id>/toggle/', views.classroom_toggle_view, name='classroom_toggle'),

    # Periods & Working Days Configuration
    path('periods/', views.period_list_view, name='period_list'),
    path('periods/create/', views.period_create_view, name='period_create'),
    path('periods/<int:period_id>/edit/', views.period_edit_view, name='period_edit'),
    path('working-days/', views.working_days_view, name='working_days'),

    # Conflicts Audit Report
    path('conflicts/', views.conflict_detection_view, name='timetable_conflicts'),

    # Reports and Exports
    path('<int:timetable_id>/export/pdf/', views.export_class_timetable_pdf_view, name='export_class_timetable_pdf'),
    path('<int:timetable_id>/export/excel/', views.export_class_timetable_excel_view, name='export_class_timetable_excel'),
    path('teachers/<int:teacher_id>/export/pdf/', views.export_teacher_timetable_pdf_view, name='export_teacher_timetable_pdf'),
    path('teachers/<int:teacher_id>/export/excel/', views.export_teacher_timetable_excel_view, name='export_teacher_timetable_excel'),
]
