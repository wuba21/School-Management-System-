from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Role

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')
    search_fields = ('code', 'name')
    list_filter = ('is_active',)

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'role', 'phone_number', 'is_approved', 'is_active', 'is_staff')
    list_filter = ('role', 'is_approved', 'is_active', 'is_staff')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('School Role & Metadata', {'fields': ('role', 'phone_number', 'is_approved')}),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('School Role & Metadata', {'fields': ('role', 'phone_number', 'is_approved')}),
    )
