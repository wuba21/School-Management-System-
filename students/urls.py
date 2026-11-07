"""
URL configuration for the Students application in SSMS.
"""

from django.urls import path
from students import views

urlpatterns = [
    path('', views.student_list_view, name='students_list'),
    path('register/', views.student_register_view, name='student_register'),
    path('<int:student_id>/', views.student_detail_view, name='student_detail'),
    path('<int:student_id>/edit/', views.student_edit_view, name='student_edit'),
    path('<int:student_id>/enroll/', views.student_enroll_view, name='student_enroll'),
    path('<int:student_id>/status/', views.student_status_view, name='student_status'),
]
