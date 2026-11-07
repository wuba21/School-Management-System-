"""
URL Configuration for AI Assistant Module.
"""

from django.urls import path
from ai_assistant import views

urlpatterns = [
    # 1. AI Dashboard
    path('', views.ai_dashboard_view, name='ai_dashboard'),

    # 2. Academic Performance Analysis
    path('academic/', views.academic_analysis_view, name='ai_academic_analysis'),
    path('analytics/', views.academic_analysis_view, name='ai_analytics'),

    # 3. Attendance Intelligence Analysis
    path('attendance/', views.attendance_analysis_view, name='ai_attendance_analysis'),

    # 4. Conversational Assistant (Chat)
    path('chat/', views.chat_assistant_view, name='ai_chat_assistant'),
    path('chat/alias/', views.chat_assistant_view, name='ai_assistant_chat'),
    path('chat/clear/', views.chat_clear_history_view, name='ai_chat_clear'),

    # 5. AI Report Generator
    path('reports/', views.ai_report_generator_view, name='ai_report_generator'),
]
