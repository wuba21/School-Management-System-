from django.contrib import admin
from .models import Teacher, TeacherAssignment

@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('employee_id', 'first_name', 'father_name', 'gender', 'qualification', 'specialization', 'is_active')
    search_fields = ('employee_id', 'first_name', 'father_name', 'specialization')
    list_filter = ('gender', 'is_active', 'specialization')

@admin.register(TeacherAssignment)
class TeacherAssignmentAdmin(admin.ModelAdmin):
    list_display = ('teacher', 'class_offering', 'subject', 'is_primary')
    list_filter = ('is_primary', 'subject')
    search_fields = ('teacher__first_name', 'teacher__father_name', 'subject__name')
