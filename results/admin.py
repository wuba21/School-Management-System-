from django.contrib import admin
from .models import GradingScale, GradingRange, Mark, ResultApproval, StudentResultSummary


class GradingRangeInline(admin.TabularInline):
    model = GradingRange
    extra = 1
    fields = ('grade_label', 'min_score', 'max_score', 'gpa_point', 'description', 'is_passing')


@admin.register(GradingScale)
class GradingScaleAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_default')
    list_filter = ('is_default',)
    search_fields = ('name', 'code')
    inlines = [GradingRangeInline]


@admin.register(GradingRange)
class GradingRangeAdmin(admin.ModelAdmin):
    list_display = ('grading_scale', 'grade_label', 'min_score', 'max_score', 'gpa_point', 'is_passing')
    list_filter = ('grading_scale', 'is_passing')
    search_fields = ('grade_label', 'description')


@admin.register(Mark)
class MarkAdmin(admin.ModelAdmin):
    list_display = ('student_enrollment', 'exam_subject', 'marks_obtained', 'is_absent', 'status', 'entered_by', 'entered_at')
    list_filter = ('status', 'is_absent', 'exam_subject__examination')
    search_fields = ('student_enrollment__student__admission_number', 'student_enrollment__student__first_name', 'exam_subject__subject__name')


@admin.register(ResultApproval)
class ResultApprovalAdmin(admin.ModelAdmin):
    list_display = ('exam_subject', 'decision', 'reviewed_by', 'reviewed_at')
    list_filter = ('decision', 'reviewed_at')
    search_fields = ('exam_subject__subject__name', 'reviewed_by__username')


@admin.register(StudentResultSummary)
class StudentResultSummaryAdmin(admin.ModelAdmin):
    list_display = ('student_enrollment', 'examination', 'total_obtained', 'average_mark', 'overall_grade', 'rank', 'status')
    list_filter = ('examination', 'overall_grade', 'status')
    search_fields = ('student_enrollment__student__admission_number', 'student_enrollment__student__first_name')
