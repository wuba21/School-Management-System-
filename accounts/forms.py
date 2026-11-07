"""
Authentication and User Management Forms for SSMS.

Forms:
  - LoginForm              : Username + password staff login
  - PasswordChangeForm     : Secure self-service password change
  - ProfileEditForm        : Limited self-editable profile fields
  - UserCreateForm         : Admin creates a new system user
  - UserEditForm           : Admin edits an existing user (role, status, approval)
"""

from django import forms
from django.contrib.auth import authenticate, password_validation
from django.core.exceptions import ValidationError

from accounts.models import User, Role


# ---------------------------------------------------------------------------
# 1. LOGIN FORM
# ---------------------------------------------------------------------------

class LoginForm(forms.Form):
    """
    Staff authentication form.
    Accepts username (not email) as per school deployment standard.
    """
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control border-start-0',
            'id': 'usernameInput',
            'name': 'username',
            'placeholder': 'e.g. principal_kebede or teacher_abebe',
            'autofocus': True,
            'autocomplete': 'username',
        }),
        label='Username',
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control border-start-0 border-end-0',
            'id': 'passwordInput',
            'name': 'password',
            'placeholder': '••••••••',
            'autocomplete': 'current-password',
        }),
        label='Password',
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self._user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get('username')
        password = cleaned_data.get('password')

        if username and password:
            # Authenticate against Django's auth backend
            self._user_cache = authenticate(
                self.request, username=username, password=password
            )
            if self._user_cache is None:
                # Generic message — do not reveal whether username exists
                raise ValidationError(
                    'Invalid username or password. Please try again.',
                    code='invalid_login',
                )
            if not self._user_cache.is_active:
                raise ValidationError(
                    'This account has been deactivated. '
                    'Contact your System Administrator.',
                    code='inactive',
                )
            if not getattr(self._user_cache, 'is_approved', True):
                raise ValidationError(
                    'Your account is pending administrative approval. '
                    'Contact your System Administrator.',
                    code='not_approved',
                )
        return cleaned_data

    def get_user(self):
        return self._user_cache


# ---------------------------------------------------------------------------
# 2. PASSWORD CHANGE FORM  (self-service, no email required)
# ---------------------------------------------------------------------------

class PasswordChangeForm(forms.Form):
    """
    Allows a logged-in user to change their own password.
    Requires current password for verification.
    """
    current_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'current-password',
        }),
        label='Current Password',
    )
    new_password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'new-password',
        }),
        label='New Password',
        help_text=password_validation.password_validators_help_text_html(),
    )
    new_password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'autocomplete': 'new-password',
        }),
        label='Confirm New Password',
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_current_password(self):
        current_password = self.cleaned_data.get('current_password')
        if not self.user.check_password(current_password):
            raise ValidationError(
                'Your current password is incorrect.',
                code='password_incorrect',
            )
        return current_password

    def clean(self):
        cleaned_data = super().clean()
        pw1 = cleaned_data.get('new_password1')
        pw2 = cleaned_data.get('new_password2')
        if pw1 and pw2 and pw1 != pw2:
            raise ValidationError(
                'The two new passwords do not match.',
                code='password_mismatch',
            )
        if pw1:
            try:
                password_validation.validate_password(pw1, self.user)
            except ValidationError as e:
                self.add_error('new_password1', e)
        return cleaned_data

    def save(self, commit=True):
        self.user.set_password(self.cleaned_data['new_password1'])
        if commit:
            self.user.save()
        return self.user


# ---------------------------------------------------------------------------
# 3. PROFILE EDIT FORM  (user edits their own limited fields)
# ---------------------------------------------------------------------------

class ProfileEditForm(forms.ModelForm):
    """
    Allows authenticated users to edit their own permitted profile fields.
    Role and permissions are NOT editable by the user.
    """
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone_number']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 0911 123 456',
            }),
        }
        labels = {
            'first_name': 'First Name',
            'last_name': 'Last Name',
            'email': 'Email Address',
            'phone_number': 'Phone Number',
        }


# ---------------------------------------------------------------------------
# 4. USER CREATE FORM  (Admin creates a new system user)
# ---------------------------------------------------------------------------

class UserCreateForm(forms.ModelForm):
    """
    System Administrator form for creating a new user account.
    Sets a temporary password that must be changed on first login.
    """
    password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Password',
        help_text='Must be at least 8 characters.',
    )
    password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Confirm Password',
    )

    class Meta:
        model = User
        fields = [
            'username', 'first_name', 'last_name',
            'email', 'phone_number', 'role', 'is_approved',
        ]
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'is_approved': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'is_approved': 'Account Approved',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only show active roles in the dropdown
        self.fields['role'].queryset = Role.objects.filter(is_active=True)
        self.fields['role'].empty_label = '— Select Role —'
        self.fields['email'].required = False

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exists():
            raise ValidationError('This username is already taken.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        pw1 = cleaned_data.get('password1')
        pw2 = cleaned_data.get('password2')
        if pw1 and pw2 and pw1 != pw2:
            raise ValidationError('The two passwords do not match.')
        if pw1:
            try:
                password_validation.validate_password(pw1)
            except ValidationError as e:
                self.add_error('password1', e)
        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        return user


# ---------------------------------------------------------------------------
# 5. USER EDIT FORM  (Admin edits an existing user)
# ---------------------------------------------------------------------------

class UserEditForm(forms.ModelForm):
    """
    System Administrator form for editing an existing user account.
    Cannot change passwords here — use a separate admin password reset flow.
    """
    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'email',
            'phone_number', 'role', 'is_active', 'is_approved',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_approved': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'is_active': 'Account Active',
            'is_approved': 'Account Approved',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['role'].queryset = Role.objects.filter(is_active=True)
        self.fields['role'].empty_label = '— Select Role —'
        self.fields['email'].required = False


# ---------------------------------------------------------------------------
# 6. ADMIN RESET PASSWORD FORM  (Admin sets a new password for another user)
# ---------------------------------------------------------------------------

class AdminPasswordResetForm(forms.Form):
    """
    Allows a System Administrator to set a new password for any user.
    Used instead of email-based reset (no email server available on LAN).
    """
    new_password1 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='New Password',
    )
    new_password2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label='Confirm New Password',
    )

    def clean(self):
        cleaned_data = super().clean()
        pw1 = cleaned_data.get('new_password1')
        pw2 = cleaned_data.get('new_password2')
        if pw1 and pw2 and pw1 != pw2:
            raise ValidationError('The two passwords do not match.')
        if pw1:
            try:
                password_validation.validate_password(pw1)
            except ValidationError as e:
                self.add_error('new_password1', e)
        return cleaned_data
