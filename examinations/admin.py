from django.contrib import admin
from .models import ExamType, Examination, ExamSubject


class ExamSubjectInline(admin.TabularInline):
    model = ExamSubject
    extra = 0
    fields = ('subject', 'grade', 'stream', 'max_marks', 'pass_marks', 'weight_percentage', 'status')


@admin.register(ExamType)
class ExamTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'default_weight', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'code')


@admin.register(Examination)
class ExaminationAdmin(admin.ModelAdmin):
    list_display = ('name', 'exam_type', 'academic_year', 'semester', 'grade', 'status', 'start_date', 'end_date', 'is_locked')
    list_filter = ('academic_year', 'semester', 'exam_type', 'status', 'is_locked', 'grade')
    search_fields = ('name',)
    inlines = [ExamSubjectInline]


@admin.register(ExamSubject)
class ExamSubjectAdmin(admin.ModelAdmin):
    list_display = ('examination', 'subject', 'grade', 'max_marks', 'pass_marks', 'weight_percentage', 'status', 'submitted_by', 'verified_by')
    list_filter = ('examination__academic_year', 'status', 'grade', 'stream')
    search_fields = ('subject__name', 'subject__code', 'examination__name')
