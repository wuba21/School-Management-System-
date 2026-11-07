"""
Django Admin registrations for Timetable and Class Scheduling models.
"""

from django.contrib import admin
from timetable.models import (
    Classroom,
    SchoolDay,
    Period,
    Timetable,
    TimetableEntry,
    TimetableVersion
)


class TimetableEntryInline(admin.TabularInline):
    model = TimetableEntry
    extra = 1
    autocomplete_fields = ['teacher', 'subject', 'classroom']
    fields = ['day_of_week', 'period', 'subject', 'teacher', 'classroom', 'notes']


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ['code', 'name', 'building', 'room_type', 'capacity', 'is_active']
    list_filter = ['room_type', 'is_active', 'building']
    search_fields = ['name', 'code', 'building']
    list_editable = ['is_active']


@admin.register(SchoolDay)
class SchoolDayAdmin(admin.ModelAdmin):
    list_display = ['day_of_week', 'name', 'short_name', 'order', 'academic_year', 'is_active']
    list_filter = ['is_active', 'academic_year']
    list_editable = ['is_active', 'order']
    ordering = ['order', 'day_of_week']


@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ['period_number', 'name', 'start_time', 'end_time', 'is_break', 'break_type', 'is_active', 'academic_year']
    list_filter = ['is_break', 'break_type', 'is_active', 'academic_year']
    list_editable = ['is_active', 'is_break']
    search_fields = ['name']
    ordering = ['period_number']


@admin.register(Timetable)
class TimetableAdmin(admin.ModelAdmin):
    list_display = ['name', 'class_offering', 'academic_year', 'version', 'status', 'total_scheduled_lessons', 'published_at']
    list_filter = ['status', 'academic_year', 'class_offering__grade']
    search_fields = ['name', 'class_offering__grade__name', 'class_offering__section__name']
    inlines = [TimetableEntryInline]


@admin.register(TimetableEntry)
class TimetableEntryAdmin(admin.ModelAdmin):
    list_display = ['timetable', 'day_name', 'period', 'subject', 'teacher', 'classroom']
    list_filter = ['day_of_week', 'period', 'timetable__academic_year']
    search_fields = ['subject__name', 'teacher__first_name', 'teacher__father_name', 'classroom__name']


@admin.register(TimetableVersion)
class TimetableVersionAdmin(admin.ModelAdmin):
    list_display = ['timetable', 'version_number', 'status', 'created_by', 'created_at']
    list_filter = ['status', 'created_at']
    readonly_fields = ['timetable', 'version_number', 'status', 'snapshot_data', 'change_summary', 'created_by', 'created_at']
