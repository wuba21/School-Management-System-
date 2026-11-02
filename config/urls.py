"""
URL configuration for the Smart School Management and Academic Information System (SSMS).
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core.views import home

urlpatterns = [
    # Built-in Django Admin Interface
    path('admin/', admin.site.urls),

    # System Home Page & Diagnostic Overview
    path('', home, name='home'),

    # Modular App URLs (Will be wired as modules are developed)
    # path('accounts/', include('accounts.urls')),
    # path('students/', include('students.urls')),
    # path('teachers/', include('teachers.urls')),
    # path('academics/', include('academics.urls')),
    # path('attendance/', include('attendance.urls')),
    # path('examinations/', include('examinations.urls')),
    # path('results/', include('results.urls')),
    # path('reports/', include('reports.urls')),
    # path('dashboard/', include('dashboard.urls')),
    # path('ai/', include('ai_assistant.urls')),
]

# Serve media and static files in development mode
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
