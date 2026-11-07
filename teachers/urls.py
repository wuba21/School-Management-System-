"""
URL routing configuration for the Teachers app.
"""

from django.urls import path
from teachers import views

urlpatterns = [
    path('', views.teacher_list_view, name='teachers_list'),
    path('register/', views.teacher_register_view, name='teacher_register'),
    path('my-profile/', views.teacher_my_profile_view, name='teacher_my_profile'),
    path('<int:teacher_id>/', views.teacher_detail_view, name='teacher_detail'),
    path('<int:teacher_id>/edit/', views.teacher_edit_view, name='teacher_edit'),
    path('<int:teacher_id>/status/', views.teacher_status_view, name='teacher_status'),
    path('<int:teacher_id>/assign/', views.teacher_assign_view, name='teacher_assign'),
    path('assignment/<int:assignment_id>/delete/', views.teacher_assignment_delete_view, name='teacher_assignment_delete'),
]
