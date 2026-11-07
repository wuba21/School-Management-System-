"""
URL patterns for the accounts app.
Handles authentication, profile, and user management routes.
"""

from django.urls import path
from accounts import views

urlpatterns = [
    # ---- Authentication ----
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # ---- Self-service Profile ----
    path('profile/', views.profile_view, name='profile'),
    path('profile/password/', views.password_change_view, name='password_change'),

    # ---- User Management (System Administrator only) ----
    path('users/', views.user_list_view, name='user_list'),
    path('users/create/', views.user_create_view, name='user_create'),
    path('users/<int:user_id>/edit/', views.user_edit_view, name='user_edit'),
    path('users/<int:user_id>/toggle-active/', views.user_toggle_active_view, name='user_toggle_active'),
    path('users/<int:user_id>/reset-password/', views.admin_password_reset_view, name='user_admin_reset_password'),
]
