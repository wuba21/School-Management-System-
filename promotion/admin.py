from django.contrib import admin
from promotion.models import (
    PromotionCriteria,
    PromotionBatch,
    PromotionRecord,
    GraduationRecord,
    StudentStatusHistory
)


class PromotionRecordInline(admin.TabularInline):
    model = PromotionRecord
    extra = 0
    fields = ('student', 'recommended_outcome', 'final_outcome', 'decision_status', 'academic_average', 'total_failing_subjects')
    readonly_fields = ('student', 'recommended_outcome', 'academic_average', 'total_failing_subjects')


@admin.register(PromotionCriteria)
class PromotionCriteriaAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'minimum_average', 'max_failing_subjects', 'minimum_attendance_percentage', 'is_active', 'is_default')
    list_filter = ('is_active', 'is_default')
    search_fields = ('name', 'code')


@admin.register(PromotionBatch)
class PromotionBatchAdmin(admin.ModelAdmin):
    list_display = ('name', 'academic_year', 'target_academic_year', 'grade', 'status', 'created_by', 'approved_by', 'approval_date')
    list_filter = ('status', 'academic_year', 'target_academic_year', 'grade')
    search_fields = ('name',)
    inlines = [PromotionRecordInline]


@admin.register(PromotionRecord)
class PromotionRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'batch', 'previous_grade', 'next_grade', 'final_outcome', 'decision_status', 'academic_average', 'is_enrolled_in_next_year')
    list_filter = ('final_outcome', 'decision_status', 'batch__academic_year', 'previous_grade')
    search_fields = ('student__admission_number', 'student__first_name', 'student__father_name')


@admin.register(GraduationRecord)
class GraduationRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'academic_year', 'grade', 'graduation_date', 'status', 'cumulative_average', 'certificate_number')
    list_filter = ('status', 'academic_year', 'grade')
    search_fields = ('student__admission_number', 'student__first_name', 'student__father_name', 'certificate_number')


@admin.register(StudentStatusHistory)
class StudentStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('student', 'status_type', 'effective_date', 'previous_status', 'new_status', 'authorized_by')
    list_filter = ('status_type', 'effective_date')
    search_fields = ('student__admission_number', 'student__first_name', 'destination_school', 'reason')
