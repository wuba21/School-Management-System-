"""
URL configuration for the Smart School Management and Academic Information System (SSMS).
"""

from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from core import views as core_views

urlpatterns = [
    # Built-in Django Admin Interface
    path('admin/', admin.site.urls),

    # Authentication UI
    path('login/', core_views.login_view, name='login'),

    # Main Dashboard
    path('', core_views.dashboard_view, name='home'),
    path('dashboard/', core_views.dashboard_view, name='dashboard'),

    # Management Modules
    path('students/', core_views.students_list_view, name='students_list'),
    path('teachers/', core_views.teachers_list_view, name='teachers_list'),
    path('academics/years/', core_views.academics_years_view, name='academics_years'),
    path('academics/grades/', core_views.academics_grades_view, name='academics_grades'),
    path('academics/subjects/', core_views.academics_subjects_view, name='academics_subjects'),

    # Academic Modules
    path('attendance/', core_views.attendance_index_view, name='attendance_index'),
    path('examinations/', core_views.examinations_index_view, name='examinations_index'),
    path('results/', core_views.results_index_view, name='results_index'),
    path('promotion/', core_views.promotion_index_view, name='promotion_index'),
    path('timetable/', core_views.timetable_index_view, name='timetable_index'),

    # Reports Modules
    path('reports/students/', core_views.reports_students_view, name='reports_students'),
    path('reports/academic/', core_views.reports_academic_view, name='reports_academic'),
    path('reports/attendance/', core_views.reports_attendance_view, name='reports_attendance'),

    # Intelligence & AI Modules
    path('ai-assistant/', core_views.ai_assistant_chat_view, name='ai_assistant_chat'),
    path('ai-assistant/analytics/', core_views.ai_analytics_view, name='ai_analytics'),

    # System & Administration Modules
    path('users/', core_views.system_users_view, name='system_users'),
    path('settings/', core_views.system_settings_view, name='system_settings'),
    path('audit/', core_views.system_audit_view, name='system_audit'),
]

# Serve media and static files in development mode
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
