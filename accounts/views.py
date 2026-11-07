"""
Authentication and User Management Views for SSMS.

Views:
  - login_view              : Staff portal login (GET + POST)
  - logout_view             : Secure session logout
  - profile_view            : View + edit own profile
  - password_change_view    : Self-service password change
  - user_list_view          : Admin: list all users
  - user_create_view        : Admin: create a new user
  - user_edit_view          : Admin: edit an existing user
  - user_toggle_active_view : Admin: activate / deactivate an account
  - admin_password_reset_view: Admin: reset another user's password
  - access_denied_view      : 403 page
"""

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST

from accounts.models import User, Role
from accounts.forms import (
    LoginForm,
    PasswordChangeForm,
    ProfileEditForm,
    UserCreateForm,
    UserEditForm,
    AdminPasswordResetForm,
)
from accounts.decorators import sysadmin_required, any_authenticated_role_required
from core.models import AuditLog


# ---------------------------------------------------------------------------
# Helper: write to AuditLog safely (never crash the main request)
# ---------------------------------------------------------------------------

def _audit(request, action, entity_name, record_id='', changes=None):
    """Write an audit log entry; silently suppresses errors."""
    try:
        actor = request.user if request.user.is_authenticated else None
        ip = (
            request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            or request.META.get('REMOTE_ADDR')
        )
        AuditLog.objects.create(
            actor=actor,
            action=action,
            entity_name=entity_name,
            record_id=str(record_id),
            ip_address=ip or None,
            changes_json=changes or {},
        )
    except Exception:
        pass  # Audit logging must never break user-facing requests


# ---------------------------------------------------------------------------
# 1. LOGIN
# ---------------------------------------------------------------------------

def login_view(request):
    """
    Staff portal login.
    Authenticated users are redirected to the dashboard immediately.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')

    form = LoginForm(request)

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)

            # Honour "Remember this terminal" (extend session to 2 weeks)
            if not request.POST.get('remember_me'):
                request.session.set_expiry(0)  # Expires when browser closes
            else:
                request.session.set_expiry(60 * 60 * 24 * 14)  # 14 days

            # Audit: successful login
            _audit(request, 'LOGIN', 'User', user.pk, {
                'username': user.username,
                'role': user.role.code if user.role else 'None',
            })

            messages.success(
                request,
                f'Welcome back, {user.get_full_name() or user.username}!'
            )

            # Redirect to "next" param if safe, otherwise dashboard
            next_url = request.GET.get('next', '')
            if next_url and next_url.startswith('/') and not next_url.startswith('//'):
                return redirect(next_url)
            return redirect('dashboard')

        else:
            # Log failed attempt (without leaking the password)
            attempted_username = request.POST.get('username', '')
            _audit(request, 'LOGIN', 'User', '', {
                'attempted_username': attempted_username,
                'result': 'FAILED',
            })

    return render(request, 'login.html', {'form': form})


# ---------------------------------------------------------------------------
# 2. LOGOUT
# ---------------------------------------------------------------------------

@login_required
def logout_view(request):
    """
    Secure logout — supports both GET and POST.
    POST is preferred (protects against CSRF-based forced logout).
    GET is accepted for LAN simplicity (logout links in navbar).
    """
    _audit(request, 'LOGIN', 'User', request.user.pk, {
        'username': request.user.username,
        'event': 'LOGOUT',
    })
    logout(request)
    messages.info(request, 'You have been signed out successfully.')
    return redirect('login')


# ---------------------------------------------------------------------------
# 3. PROFILE  (view + edit own profile)
# ---------------------------------------------------------------------------

@any_authenticated_role_required
def profile_view(request):
    """
    Users can view their own profile and edit permitted fields.
    Role, permissions, and activation status are read-only here.
    """
    user = request.user
    form = ProfileEditForm(instance=user)

    if request.method == 'POST':
        form = ProfileEditForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            _audit(request, 'UPDATE', 'User', user.pk, {
                'fields_changed': list(form.changed_data),
            })
            messages.success(request, 'Your profile has been updated successfully.')
            return redirect('profile')

    context = {
        'active_menu': 'profile',
        'form': form,
        'page_title': 'My Profile',
    }
    return render(request, 'accounts/profile.html', context)


# ---------------------------------------------------------------------------
# 4. PASSWORD CHANGE  (self-service)
# ---------------------------------------------------------------------------

@any_authenticated_role_required
def password_change_view(request):
    """
    Self-service password change.
    Requires the current password for verification.
    Session is refreshed after change so the user stays logged in.
    """
    user = request.user
    form = PasswordChangeForm(user=user)

    if request.method == 'POST':
        form = PasswordChangeForm(user=user, data=request.POST)
        if form.is_valid():
            form.save()
            # Keep the user logged in after password change
            update_session_auth_hash(request, user)
            _audit(request, 'UPDATE', 'User', user.pk, {
                'event': 'PASSWORD_CHANGED',
            })
            messages.success(
                request,
                'Your password has been changed successfully. '
                'Please use the new password on your next login.'
            )
            return redirect('profile')

    context = {
        'active_menu': 'profile',
        'form': form,
        'page_title': 'Change Password',
    }
    return render(request, 'accounts/password_change.html', context)


# ---------------------------------------------------------------------------
# 5. USER LIST  (Admin only)
# ---------------------------------------------------------------------------

@sysadmin_required
def user_list_view(request):
    """
    System Administrator: view all user accounts and their roles.
    """
    users = User.objects.select_related('role').order_by('username')
    roles = Role.objects.filter(is_active=True)

    # Optional role filter
    role_filter = request.GET.get('role', '')
    if role_filter:
        users = users.filter(role__code=role_filter)

    context = {
        'active_menu': 'system_users',
        'page_title': 'User Management',
        'users': users,
        'roles': roles,
        'role_filter': role_filter,
    }
    return render(request, 'accounts/user_list.html', context)


# ---------------------------------------------------------------------------
# 6. USER CREATE  (Admin only)
# ---------------------------------------------------------------------------

@sysadmin_required
def user_create_view(request):
    """
    System Administrator: create a new system user account.
    """
    form = UserCreateForm()

    if request.method == 'POST':
        form = UserCreateForm(request.POST)
        if form.is_valid():
            new_user = form.save()
            _audit(request, 'CREATE', 'User', new_user.pk, {
                'created_username': new_user.username,
                'role': new_user.role.code if new_user.role else 'None',
                'by': request.user.username,
            })
            messages.success(
                request,
                f'User account "{new_user.username}" created successfully. '
                f'Role: {new_user.role.name if new_user.role else "None"}.'
            )
            return redirect('user_list')

    context = {
        'active_menu': 'system_users',
        'page_title': 'Create New User',
        'form': form,
    }
    return render(request, 'accounts/user_create.html', context)


# ---------------------------------------------------------------------------
# 7. USER EDIT  (Admin only)
# ---------------------------------------------------------------------------

@sysadmin_required
def user_edit_view(request, user_id):
    """
    System Administrator: edit an existing user's profile and role.
    Admins cannot edit other superusers via this view (use Django admin).
    """
    target_user = get_object_or_404(User, pk=user_id)

    # Protect superuser accounts from being modified via this form
    if target_user.is_superuser and not request.user.is_superuser:
        raise PermissionDenied

    form = UserEditForm(instance=target_user)

    if request.method == 'POST':
        old_role = target_user.role.code if target_user.role else 'None'
        form = UserEditForm(request.POST, instance=target_user)
        if form.is_valid():
            updated_user = form.save()
            new_role = updated_user.role.code if updated_user.role else 'None'
            _audit(request, 'UPDATE', 'User', updated_user.pk, {
                'edited_username': updated_user.username,
                'old_role': old_role,
                'new_role': new_role,
                'fields_changed': list(form.changed_data),
                'by': request.user.username,
            })
            messages.success(
                request,
                f'User account "{updated_user.username}" updated successfully.'
            )
            return redirect('user_list')

    context = {
        'active_menu': 'system_users',
        'page_title': f'Edit User: {target_user.username}',
        'form': form,
        'target_user': target_user,
    }
    return render(request, 'accounts/user_edit.html', context)


# ---------------------------------------------------------------------------
# 8. TOGGLE ACCOUNT ACTIVE STATUS  (Admin only)
# ---------------------------------------------------------------------------

@sysadmin_required
@require_POST
def user_toggle_active_view(request, user_id):
    """
    System Administrator: activate or deactivate a user account.
    Superusers cannot be deactivated through this view.
    """
    target_user = get_object_or_404(User, pk=user_id)

    if target_user == request.user:
        messages.error(request, 'You cannot deactivate your own account.')
        return redirect('user_list')

    if target_user.is_superuser:
        messages.error(request, 'Superuser accounts cannot be modified here.')
        return redirect('user_list')

    old_status = target_user.is_active
    target_user.is_active = not old_status
    target_user.save(update_fields=['is_active'])

    action_label = 'ACTIVATED' if target_user.is_active else 'DEACTIVATED'
    _audit(request, 'UPDATE', 'User', target_user.pk, {
        'username': target_user.username,
        'event': action_label,
        'by': request.user.username,
    })

    messages.success(
        request,
        f'Account "{target_user.username}" has been {action_label.lower()} successfully.'
    )
    return redirect('user_list')


# ---------------------------------------------------------------------------
# 9. ADMIN PASSWORD RESET  (Admin sets password for another user)
# ---------------------------------------------------------------------------

@sysadmin_required
def admin_password_reset_view(request, user_id):
    """
    System Administrator: reset another user's password directly.
    Used as a replacement for email-based password reset (not available on LAN).
    """
    target_user = get_object_or_404(User, pk=user_id)

    if target_user.is_superuser and not request.user.is_superuser:
        raise PermissionDenied

    form = AdminPasswordResetForm()

    if request.method == 'POST':
        form = AdminPasswordResetForm(request.POST)
        if form.is_valid():
            target_user.set_password(form.cleaned_data['new_password1'])
            target_user.save()
            _audit(request, 'UPDATE', 'User', target_user.pk, {
                'event': 'PASSWORD_RESET_BY_ADMIN',
                'target_username': target_user.username,
                'by': request.user.username,
            })
            messages.success(
                request,
                f'Password for "{target_user.username}" has been reset successfully. '
                f'Inform the user of their new password in person.'
            )
            return redirect('user_list')

    context = {
        'active_menu': 'system_users',
        'page_title': f'Reset Password: {target_user.username}',
        'form': form,
        'target_user': target_user,
    }
    return render(request, 'accounts/admin_password_reset.html', context)


# ---------------------------------------------------------------------------
# 10. 403 ACCESS DENIED  (custom 403 handler)
# ---------------------------------------------------------------------------

def access_denied_view(request, exception=None):
    """
    Custom 403 Forbidden page.
    Renders a friendly error page with the user's role and a back button.
    """
    return render(request, 'accounts/403.html', status=403)
