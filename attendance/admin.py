from django.contrib import admin
from .models import AttendanceSession, AttendanceRecord

@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ('class_offering', 'date', 'session_type', 'recorded_by')
    list_filter = ('session_type', 'date')
    search_fields = ('class_offering__grade__name', 'class_offering__section__name')

@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('attendance_session', 'student_enrollment', 'status', 'reason')
    list_filter = ('status',)
    search_fields = ('student_enrollment__student__admission_number',)
