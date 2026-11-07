"""
URL configuration for the Student Promotion and Academic History Module.
"""

from django.urls import path
from promotion import views

urlpatterns = [
    # Dashboard
    path('', views.promotion_dashboard_view, name='promotion_index'),
    path('dashboard/', views.promotion_dashboard_view, name='promotion_dashboard'),

    # Batch Promotion Lifecycle
    path('prepare/', views.promotion_prepare_view, name='promotion_prepare'),
    path('batch/<int:batch_id>/', views.promotion_batch_detail_view, name='promotion_batch_detail'),
    path('batch/<int:batch_id>/submit/', views.promotion_batch_submit_view, name='promotion_batch_submit'),
    path('batch/<int:batch_id>/preview/', views.promotion_preview_view, name='promotion_preview'),
    path('batch/<int:batch_id>/approve/', views.promotion_approval_view, name='promotion_approval'),
    path('batch/<int:batch_id>/finalize/', views.promotion_finalize_view, name='promotion_finalize'),
    path('record/<int:record_id>/update/', views.promotion_record_update_view, name='promotion_record_update'),

    # Student Academic History Transcript
    path('history/<int:student_id>/', views.student_academic_history_view, name='student_academic_history'),

    # Graduation Management
    path('graduation/', views.graduation_management_view, name='graduation_management'),

    # Student Transfer & Withdrawal
    path('status-change/', views.student_status_change_view, name='student_status_change'),
    path('transfers-withdrawals/', views.student_status_history_view, name='student_status_history'),

    # Reports & Exports
    path('reports/', views.promotion_reports_view, name='promotion_reports'),
    path('batch/<int:batch_id>/export/pdf/', views.export_promotion_pdf_view, name='export_promotion_pdf'),
    path('batch/<int:batch_id>/export/excel/', views.export_promotion_excel_view, name='export_promotion_excel'),

    # Policy Criteria Management
    path('criteria/', views.promotion_criteria_view, name='promotion_criteria'),
]
