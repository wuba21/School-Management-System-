"""
Role-Based Access Control (RBAC) Decorators for SSMS.

Usage:
    @login_required           — any authenticated user
    @principal_required       — Principal only
    @registrar_required       — Registrar only
    @teacher_required         — Teacher only
    @sysadmin_required        — System Administrator only
    @staff_or_principal       — Principal OR Registrar (view-only data)
    @can_manage_users         — System Administrator only

All decorators enforce server-side role checks.
Bypassing a URL does NOT bypass the check.
"""

from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect


def _role_required(role_codes, allow_superuser=True):
    """
    Factory that returns a decorator enforcing one or more role codes.
    - allow_superuser: if True, Django superusers always pass regardless of role.
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            # Superusers bypass role checks
            if allow_superuser and user.is_superuser:
                return view_func(request, *args, **kwargs)
            # Inactive or unapproved accounts are blocked
            if not user.is_active or not getattr(user, 'is_approved', True):
                raise PermissionDenied
            # Role check
            user_role_code = user.role.code if user.role else None
            if user_role_code in role_codes:
                return view_func(request, *args, **kwargs)
            raise PermissionDenied
        return _wrapped_view
    return decorator


def principal_required(view_func):
    """Allow only users with the PRINCIPAL role."""
    return _role_required(['PRINCIPAL'])(view_func)


def registrar_required(view_func):
    """Allow only users with the REGISTRAR role."""
    return _role_required(['REGISTRAR'])(view_func)


def teacher_required(view_func):
    """Allow only users with the TEACHER role."""
    return _role_required(['TEACHER'])(view_func)


def sysadmin_required(view_func):
    """Allow only users with the ADMIN role (or Django superusers)."""
    return _role_required(['ADMIN'])(view_func)


def principal_or_registrar_required(view_func):
    """Allow Principal or Registrar — for shared read/report views."""
    return _role_required(['PRINCIPAL', 'REGISTRAR'])(view_func)


def management_staff_required(view_func):
    """Allow Principal, Registrar, or Admin — excluding Teacher-only access."""
    return _role_required(['PRINCIPAL', 'REGISTRAR', 'ADMIN'])(view_func)


def any_authenticated_role_required(view_func):
    """
    Require login AND that the user has an assigned role (or is superuser).
    Teachers, Registrars, Principals, and Admins all pass.
    Bare staff accounts with no role are blocked.
    """
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        if user.is_superuser:
            return view_func(request, *args, **kwargs)
        if not user.is_active or not getattr(user, 'is_approved', True):
            raise PermissionDenied
        if user.role is None:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped_view
