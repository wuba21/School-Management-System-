"""
URL configuration for the Examinations Module.
"""

from django.urls import path
from examinations import views

urlpatterns = [
    # Dashboard & Directories
    path('', views.examination_dashboard_view, name='examinations_index'),
    path('list/', views.examination_list_view, name='examination_list'),
    path('create/', views.examination_create_view, name='examination_create'),
    path('<int:exam_id>/', views.examination_detail_view, name='examination_detail'),

    # Subject Configurations
    path('<int:exam_id>/subjects/add/', views.examination_subject_config_view, name='examination_subject_add'),
    path('<int:exam_id>/subjects/auto/', views.examination_auto_configure_view, name='examination_subject_auto'),

    # Lifecycle Controls
    path('<int:exam_id>/close/', views.examination_close_view, name='examination_close'),
    path('<int:exam_id>/reopen/', views.examination_reopen_view, name='examination_reopen'),
]
