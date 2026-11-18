"""
URL configuration for the Smart School Management and Academic Information System (SSMS).
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from core import views as core_views
from accounts.views import access_denied_view
from attendance import views as attendance_views

import sys
from django.views.debug import technical_500_response
from django.views.defaults import server_error

def custom_handler500(request):
    """Provides diagnostic tracebacks for superusers to troubleshoot production issues."""
    try:
        user = getattr(request, 'user', None)
        if (user and user.is_authenticated and user.is_superuser) or request.GET.get('debug') == '1':
            return technical_500_response(request, *sys.exc_info())
    except Exception:
        pass
    return server_error(request)

# Custom error handlers (must be at module level)
handler403 = 'accounts.views.access_denied_view'
handler404 = 'django.views.defaults.page_not_found'
handler500 = 'config.urls.custom_handler500'

urlpatterns = [
    # Built-in Django Admin Interface
    path('admin/', admin.site.urls),

    # Django i18n language switcher
    path('i18n/', include('django.conf.urls.i18n')),

    # Accounts app: auth + user management (replaces old /login/ and /users/ in core)
    path('', include('accounts.urls')),

    # Main Dashboard
    path('', core_views.dashboard_view, name='home'),
    path('dashboard/', core_views.dashboard_view, name='dashboard'),

    # Management Modules
    path('students/', include('students.urls')),
    path('teachers/', include('teachers.urls')),
    path('academics/', include('academics.urls')),

    # Academic Modules
    path('attendance/', include('attendance.urls')),
    path('examinations/', include('examinations.urls')),
    path('results/', include('results.urls')),
    path('promotion/', include('promotion.urls')),
    path('timetable/', include('timetable.urls')),

    # Reports & Analytics Hub
    path('reports/', include('reports.urls')),

    # Intelligence & AI Modules
    path('ai-assistant/', include('ai_assistant.urls')),

    # System Backup & Recovery (Step 17)
    path('backups/', include('backup.urls')),

    # System & Administration Modules (legacy routes redirect to accounts app)
    path('system/users/', core_views.system_users_view, name='system_users'),
    path('settings/', core_views.system_settings_view, name='system_settings'),
    path('audit/', core_views.system_audit_view, name='system_audit'),
    path('audit/export/', core_views.audit_log_export_csv_view, name='audit_log_export'),
]


# Serve media and static files in development mode
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
