from django.contrib import admin
from .models import Examination, ExamSubject

@admin.register(Examination)
class ExaminationAdmin(admin.ModelAdmin):
    list_display = ('name', 'academic_year', 'semester', 'start_date', 'end_date', 'is_active', 'is_locked')
    list_filter = ('academic_year', 'semester', 'is_active', 'is_locked')
    search_fields = ('name',)

@admin.register(ExamSubject)
class ExamSubjectAdmin(admin.ModelAdmin):
    list_display = ('examination', 'grade', 'stream', 'subject', 'max_marks', 'pass_marks', 'weight_percentage')
    list_filter = ('examination', 'grade', 'stream')
    search_fields = ('subject__name',)
