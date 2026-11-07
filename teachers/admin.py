from django.contrib import admin
from .models import Teacher, TeacherAssignment

@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'first_name', 'father_name', 'gender', 'qualification', 'specialization', 'employment_status', 'is_active', 'joining_date')
    search_fields = ('employee_id', 'first_name', 'father_name', 'specialization', 'phone_number', 'email')
    list_filter = ('employment_status', 'gender', 'is_active', 'specialization')
    readonly_fields = ('is_active',)

@admin.register(TeacherAssignment)
class TeacherAssignmentAdmin(admin.ModelAdmin):
    list_display = ('teacher', 'class_offering', 'subject', 'academic_year', 'is_primary', 'assigned_at')
    list_filter = ('academic_year', 'is_primary', 'subject')
    search_fields = ('teacher__first_name', 'teacher__father_name', 'teacher__employee_id', 'subject__name', 'class_offering__grade__name')
