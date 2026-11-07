"""
URL routing configuration for the Academics app.
"""

from django.urls import path
from academics import views

urlpatterns = [
    # Academic Years
    path('years/', views.academic_year_list_view, name='academics_years'),
    path('years/create/', views.academic_year_create_view, name='academic_year_create'),
    path('years/<int:year_id>/edit/', views.academic_year_edit_view, name='academic_year_edit'),
    path('years/<int:year_id>/activate/', views.academic_year_activate_view, name='academic_year_activate'),
    path('years/<int:year_id>/close/', views.academic_year_close_view, name='academic_year_close'),
    path('years/<int:year_id>/reopen/', views.academic_year_reopen_view, name='academic_year_reopen'),

    # Grades, Sections & Streams
    path('grades-sections/', views.grades_sections_view, name='academics_grades'),
    path('grades/', views.grades_sections_view, name='academics_grades_alias'),
    path('grades/create/', views.grade_create_view, name='grade_create'),
    path('grades/<int:grade_id>/edit/', views.grade_edit_view, name='grade_edit'),
    path('grades/<int:grade_id>/toggle/', views.grade_toggle_view, name='grade_toggle'),

    path('sections/create/', views.section_create_view, name='section_create'),
    path('sections/<int:section_id>/edit/', views.section_edit_view, name='section_edit'),
    path('sections/<int:section_id>/toggle/', views.section_toggle_view, name='section_toggle'),

    path('streams/create/', views.stream_create_view, name='stream_create'),
    path('streams/<int:stream_id>/edit/', views.stream_edit_view, name='stream_edit'),
    path('streams/<int:stream_id>/toggle/', views.stream_toggle_view, name='stream_toggle'),

    # Master Subjects
    path('subjects/', views.subject_list_view, name='academics_subjects'),
    path('subjects/create/', views.subject_create_view, name='subject_create'),
    path('subjects/<int:subject_id>/edit/', views.subject_edit_view, name='subject_edit'),
    path('subjects/<int:subject_id>/toggle/', views.subject_toggle_view, name='subject_toggle'),

    # Class Offerings (Classrooms)
    path('classes/', views.class_offering_list_view, name='class_offering_list'),
    path('classes/create/', views.class_offering_create_view, name='class_offering_create'),
    path('classes/<int:offering_id>/', views.class_offering_detail_view, name='class_offering_detail'),
    path('classes/<int:offering_id>/edit/', views.class_offering_edit_view, name='class_offering_edit'),

    # Classroom Student Enrollment
    path('classes/<int:offering_id>/enroll/', views.class_enroll_student_view, name='class_enroll_student'),
    path('classes/<int:offering_id>/enrollments/<int:enrollment_id>/remove/', views.class_remove_student_view, name='class_remove_student'),

    # Classroom Teacher Allocation
    path('classes/<int:offering_id>/assign-teacher/', views.class_assign_teacher_view, name='class_assign_teacher'),
    path('classes/<int:offering_id>/assignments/<int:assignment_id>/remove/', views.class_remove_teacher_view, name='class_remove_teacher'),

    # Curriculum Subject Allocations
    path('curriculum/', views.curriculum_list_view, name='academics_curriculum'),
    path('curriculum/create/', views.curriculum_create_view, name='curriculum_create'),
    path('curriculum/<int:curriculum_id>/delete/', views.curriculum_delete_view, name='curriculum_delete'),
]
