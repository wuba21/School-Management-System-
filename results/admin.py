from django.contrib import admin
from .models import Mark

@admin.register(Mark)
class MarkAdmin(admin.ModelAdmin):
    list_display = ('student_enrollment', 'exam_subject', 'marks_obtained', 'is_absent', 'entered_by', 'entered_at')
    list_filter = ('is_absent', 'exam_subject__examination')
    search_fields = ('student_enrollment__student__admission_number', 'exam_subject__subject__name')
