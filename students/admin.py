from django.contrib import admin
from .models import Student, StudentEnrollment, PromotionRecord

@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('admission_number', 'first_name', 'father_name', 'grandfather_name', 'gender', 'date_of_birth', 'status')
    search_fields = ('admission_number', 'first_name', 'father_name', 'grandfather_name')
    list_filter = ('gender', 'status')

@admin.register(StudentEnrollment)
class StudentEnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'class_offering', 'academic_year', 'status', 'enrollment_date')
    list_filter = ('academic_year', 'status')
    search_fields = ('student__admission_number', 'student__first_name', 'student__father_name')

@admin.register(PromotionRecord)
class PromotionRecordAdmin(admin.ModelAdmin):
    list_display = ('student', 'from_academic_year', 'to_academic_year', 'from_grade', 'to_grade', 'decision', 'average_mark')
    list_filter = ('decision', 'from_grade', 'to_grade')
    search_fields = ('student__admission_number', 'student__first_name')
