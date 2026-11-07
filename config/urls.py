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

# Custom error handlers (must be at module level)
handler403 = 'accounts.views.access_denied_view'
handler404 = 'django.views.defaults.page_not_found'

urlpatterns = [
    # Built-in Django Admin Interface
    path('admin/', admin.site.urls),

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

    # System & Administration Modules (legacy routes redirect to accounts app)
    path('system/users/', core_views.system_users_view, name='system_users'),
    path('settings/', core_views.system_settings_view, name='system_settings'),
    path('audit/', core_views.system_audit_view, name='system_audit'),
]

# Serve media and static files in development mode
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
