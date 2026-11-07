from django.contrib import admin
from attendance.models import AttendanceSession, AttendanceRecord


class AttendanceRecordInline(admin.TabularInline):
    model = AttendanceRecord
    extra = 0
    raw_id_fields = ('student_enrollment',)
    fields = ('student_enrollment', 'status', 'reason', 'recorded_by')


@admin.register(AttendanceSession)
class AttendanceSessionAdmin(admin.ModelAdmin):
    list_display = ('class_offering', 'date', 'session_type', 'subject', 'status', 'recorded_by', 'attendance_percentage')
    list_filter = ('session_type', 'status', 'date', 'class_offering__grade')
    search_fields = ('class_offering__grade__name', 'class_offering__section__name', 'recorded_by__first_name', 'recorded_by__father_name')
    date_hierarchy = 'date'
    inlines = [AttendanceRecordInline]


@admin.register(AttendanceRecord)
class AttendanceRecordAdmin(admin.ModelAdmin):
    list_display = ('student_enrollment', 'attendance_session', 'status', 'reason', 'recorded_by', 'created_at')
    list_filter = ('status', 'attendance_session__date', 'attendance_session__class_offering__grade')
    search_fields = ('student_enrollment__student__admission_number', 'student_enrollment__student__first_name', 'student_enrollment__student__father_name')
