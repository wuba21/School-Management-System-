from django.contrib import admin
from .models import AcademicYear, Grade, Section, Stream, Subject, CurriculumSubject, ClassOffering

@admin.register(AcademicYear)
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'start_date', 'end_date', 'is_current', 'is_closed')
    list_filter = ('is_current', 'is_closed')
    search_fields = ('name', 'code')

@admin.register(Grade)
class GradeAdmin(admin.ModelAdmin):
    list_display = ('name', 'level', 'description')
    ordering = ('level',)

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)

@admin.register(Stream)
class StreamAdmin(admin.ModelAdmin):
    list_display = ('code', 'name')
    search_fields = ('code', 'name')

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('code', 'name')

@admin.register(CurriculumSubject)
class CurriculumSubjectAdmin(admin.ModelAdmin):
    list_display = ('grade', 'stream', 'subject', 'credit_hours', 'is_elective')
    list_filter = ('grade', 'stream', 'is_elective')

@admin.register(ClassOffering)
class ClassOfferingAdmin(admin.ModelAdmin):
    list_display = ('academic_year', 'grade', 'section', 'stream', 'max_capacity')
    list_filter = ('academic_year', 'grade', 'stream')
