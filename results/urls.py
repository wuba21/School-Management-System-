"""
URL configuration for the Results & Marks Management Module.
"""

from django.urls import path
from results import views

urlpatterns = [
    # Dashboard / Hub
    path('', views.results_index_view, name='results_index'),

    # Marks Recording & Workflow
    path('marks/entry/<int:exam_subject_id>/', views.marks_entry_view, name='marks_entry'),
    path('marks/submit/<int:exam_subject_id>/', views.marks_submit_view, name='marks_submit'),
    path('marks/verify/<int:exam_subject_id>/', views.marks_verify_view, name='marks_verify'),

    # Calculation & Publishing
    path('calculate/<int:exam_id>/', views.calculate_results_view, name='calculate_results'),
    path('publish/<int:exam_id>/', views.publish_results_view, name='publish_results'),
    path('published/', views.published_results_view, name='published_results'),
    path('published/<int:exam_id>/', views.published_results_view, name='published_results'),

    # Student Transcripts & Report Cards
    path('students/<int:student_id>/', views.student_result_history_view, name='student_result_history'),
    path('report-card/<int:exam_id>/<int:student_id>/', views.student_report_card_view, name='student_report_card'),

    # Excel Exports & Performance Analytics
    path('export/excel/<int:exam_id>/', views.export_class_results_excel_view, name='export_class_results_excel'),
    path('reports/', views.performance_reports_view, name='performance_reports'),
    path('reports/academic/', views.performance_reports_view, name='reports_academic'),

    # Grading Policy Configuration
    path('grading/', views.grading_configuration_view, name='grading_config'),
]
