"""
Student Management Views for SSMS.

Handles:
  - student_list_view     : Directory listing with search, multi-filter, pagination, and role scoping
  - student_register_view : Comprehensive student admission with optional class assignment (Registrar only)
  - student_detail_view   : Longitudinal student profile with history, marks, and attendance
  - student_edit_view     : Profile and contact editing (Registrar only)
  - student_enroll_view   : Classroom enrollment assignment (Registrar only)
  - student_status_view   : Status transitions (Active, Transferred, Withdrawn, Graduated) (Registrar only)
"""

from urllib.parse import urlencode
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST
from django.db.models import Count, Q

from accounts.decorators import (
    any_authenticated_role_required,
    registrar_required,
)
from students.models import Student, StudentEnrollment, PromotionRecord
from academics.models import AcademicYear, Grade, Section, Stream, ClassOffering
from teachers.models import Teacher, TeacherAssignment
from attendance.models import AttendanceRecord
from results.models import Mark
from students.forms import (
    StudentRegistrationForm,
    StudentEditForm,
    StudentEnrollmentForm,
    StudentStatusUpdateForm,
)
from students.services import StudentService


# ---------------------------------------------------------------------------
# 1. STUDENT LIST (DIRECTORY)
# ---------------------------------------------------------------------------

@any_authenticated_role_required
def student_list_view(request):
    """
    Renders the student directory.
    - Teachers see only students in their assigned classrooms.
    - Principals, Registrars, and Administrators see the full institution directory.
    - Includes search, multi-field filtering, sorting, and pagination.
    """
    scoped_qs = StudentService.get_scoped_queryset(request.user)
    filtered_qs = StudentService.filter_students(scoped_qs, request.GET)

    # Prefetch active enrollment for display
    current_year = AcademicYear.objects.filter(is_current=True).first()
    filtered_qs = filtered_qs.prefetch_related(
        'enrollments__class_offering__grade',
        'enrollments__class_offering__section',
        'enrollments__class_offering__stream',
        'enrollments__academic_year'
    )

    # Pagination: 20 students per page
    paginator = Paginator(filtered_qs, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Clean query parameters for pagination links (excluding 'page')
    params = request.GET.copy()
    if 'page' in params:
        del params['page']
    pagination_query = f"&{params.urlencode()}" if params else ""

    user_role = request.user.role.code if request.user.role else ('ADMIN' if request.user.is_superuser else None)

    context = {
        'page_obj': page_obj,
        'total_count': paginator.count,
        'grades': Grade.objects.all().order_by('level'),
        'sections': Section.objects.all().order_by('name'),
        'streams': Stream.objects.all().order_by('name'),
        'academic_years': AcademicYear.objects.all().order_by('-start_date'),
        'status_choices': Student.STATUS_CHOICES,
        'current_filters': request.GET,
        'pagination_query': pagination_query,
        'is_registrar': user_role in ('REGISTRAR', 'ADMIN') or request.user.is_superuser,
        'is_teacher': user_role == 'TEACHER',
        'is_principal': user_role == 'PRINCIPAL',
        'active_menu': 'students',
        'page_title': 'Student Directory',
    }
    return render(request, 'students/student_list.html', context)


# ---------------------------------------------------------------------------
# 2. STUDENT REGISTRATION
# ---------------------------------------------------------------------------

@registrar_required
def student_register_view(request):
    """
    Registers a new student.
    Strictly restricted to Registrars (and System Administrators).
    """
    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            student = form.save()

            # Optional immediate class enrollment
            offering = form.cleaned_data.get('class_offering')
            academic_year = form.cleaned_data.get('academic_year')
            if offering and academic_year:
                StudentEnrollment.objects.create(
                    student=student,
                    class_offering=offering,
                    academic_year=academic_year,
                    status='ACTIVE'
                )

            # Audit log
            StudentService.log_audit(
                request,
                'CREATE',
                student,
                {
                    'admission_number': student.admission_number,
                    'full_name': student.full_name,
                    'gender': student.gender,
                    'class_offering': str(offering) if offering else 'Not Assigned',
                }
            )

            messages.success(
                request,
                f"Student '{student.full_name}' was successfully registered with Admission Number: {student.admission_number}."
            )
            return redirect('student_detail', student_id=student.pk)
    else:
        form = StudentRegistrationForm()

    current_year = AcademicYear.objects.filter(is_current=True).first()

    context = {
        'form': form,
        'current_year': current_year,
        'active_menu': 'students',
        'page_title': 'Register New Student',
    }
    return render(request, 'students/student_register.html', context)


# ---------------------------------------------------------------------------
# 3. STUDENT DETAIL & LONGITUDINAL PROFILE
# ---------------------------------------------------------------------------

@any_authenticated_role_required
def student_detail_view(request, student_id):
    """
    Detailed student profile including personal, contact, guardian, enrollment history,
    attendance performance, and exam mark summary.
    Enforces teacher-scoping: Teachers can only view profiles of students in their assigned classes.
    """
    student = get_object_or_404(Student, pk=student_id)
    user_role = request.user.role.code if request.user.role else ('ADMIN' if request.user.is_superuser else None)

    # Permission check for Teacher
    if user_role == 'TEACHER':
        teacher = getattr(request.user, 'teacher_profile', None) or Teacher.objects.filter(user=request.user).first()
        if not teacher:
            raise PermissionDenied("No teacher profile linked to your user account.")
        assigned_classes = ClassOffering.objects.filter(teacher_assignments__teacher=teacher)
        is_assigned = StudentEnrollment.objects.filter(
            student=student,
            class_offering__in=assigned_classes
        ).exists()
        if not is_assigned:
            raise PermissionDenied("You are not assigned to any classroom containing this student.")

    # Current / Latest Active Enrollment
    current_enrollment = (
        student.enrollments.select_related('class_offering__grade', 'class_offering__section', 'class_offering__stream', 'academic_year')
        .order_by('-academic_year__start_date')
        .first()
    )

    # Longitudinal Enrollments
    all_enrollments = (
        student.enrollments.select_related('class_offering__grade', 'class_offering__section', 'class_offering__stream', 'academic_year')
        .order_by('-academic_year__start_date')
    )

    # Promotion & Academic Progression Records
    promotions = student.promotion_records.select_related(
        'from_academic_year', 'to_academic_year', 'from_grade', 'to_grade', 'approved_by'
    ).order_by('-created_at')

    # Attendance Statistics
    att_records = AttendanceRecord.objects.filter(student_enrollment__student=student)
    total_attendance_sessions = att_records.count()
    present_count = att_records.filter(status='PRESENT').count()
    late_count = att_records.filter(status='LATE').count()
    absent_count = att_records.filter(status='ABSENT').count()
    excused_count = att_records.filter(status='EXCUSED').count()
    
    if total_attendance_sessions > 0:
        attendance_percentage = round(((present_count + late_count) / total_attendance_sessions) * 100, 1)
    else:
        attendance_percentage = None

    # Examination Marks Summary
    marks = (
        Mark.objects.filter(student_enrollment__student=student)
        .select_related(
            'exam_subject__examination__academic_year',
            'exam_subject__subject',
            'exam_subject__grade',
            'entered_by'
        )
        .order_by('-exam_subject__examination__start_date')[:15]
    )

    context = {
        'student': student,
        'current_enrollment': current_enrollment,
        'all_enrollments': all_enrollments,
        'promotions': promotions,
        'attendance_stats': {
            'total': total_attendance_sessions,
            'present': present_count,
            'late': late_count,
            'absent': absent_count,
            'excused': excused_count,
            'percentage': attendance_percentage,
        },
        'marks': marks,
        'status_form': StudentStatusUpdateForm(initial={'status': student.status}),
        'is_registrar': user_role in ('REGISTRAR', 'ADMIN') or request.user.is_superuser,
        'is_principal': user_role == 'PRINCIPAL',
        'is_teacher': user_role == 'TEACHER',
        'active_menu': 'students',
        'page_title': f"{student.full_name} ({student.admission_number})",
    }
    return render(request, 'students/student_detail.html', context)


# ---------------------------------------------------------------------------
# 4. STUDENT EDIT (UPDATE)
# ---------------------------------------------------------------------------

@registrar_required
def student_edit_view(request, student_id):
    """
    Edits an existing student's personal, contact, and guardian information.
    Restricted to Registrar and Administrator roles. Logs changes to AuditLog.
    """
    student = get_object_or_404(Student, pk=student_id)

    if request.method == 'POST':
        # Track initial state for audit log diff
        old_values = {
            'first_name': student.first_name,
            'father_name': student.father_name,
            'grandfather_name': student.grandfather_name,
            'gender': student.gender,
            'date_of_birth': str(student.date_of_birth),
            'address': student.address,
            'emergency_contact_phone': student.emergency_contact_phone,
            'status': student.status,
        }

        form = StudentEditForm(request.POST, request.FILES, instance=student)
        if form.is_valid():
            updated_student = form.save()

            # Calculate changes
            changes = {}
            for field, old_val in old_values.items():
                new_val = str(getattr(updated_student, field))
                if old_val != new_val:
                    changes[field] = {'old': old_val, 'new': new_val}

            if 'photo' in form.changed_data:
                changes['photo'] = {'old': 'Previous Photo', 'new': 'Updated Photo'}

            StudentService.log_audit(
                request,
                'UPDATE',
                updated_student,
                changes
            )

            messages.success(
                request,
                f"Student record for '{updated_student.full_name}' has been updated successfully."
            )
            return redirect('student_detail', student_id=updated_student.pk)
    else:
        form = StudentEditForm(instance=student)

    context = {
        'form': form,
        'student': student,
        'active_menu': 'students',
        'page_title': f"Edit Student: {student.full_name}",
    }
    return render(request, 'students/student_edit.html', context)


# ---------------------------------------------------------------------------
# 5. STUDENT ENROLLMENT ASSIGNMENT
# ---------------------------------------------------------------------------

@registrar_required
def student_enroll_view(request, student_id):
    """
    Enrolls a student into an academic class offering for a specified academic year.
    Prevents duplicate enrollments in the same academic year while preserving historical enrollments.
    """
    student = get_object_or_404(Student, pk=student_id)

    if request.method == 'POST':
        form = StudentEnrollmentForm(request.POST, student=student)
        if form.is_valid():
            enrollment = form.save(commit=False)
            enrollment.student = student
            enrollment.save()

            StudentService.log_audit(
                request,
                'ENROLL',
                student,
                {
                    'academic_year': enrollment.academic_year.name,
                    'class_offering': str(enrollment.class_offering),
                    'status': enrollment.status,
                }
            )

            messages.success(
                request,
                f"Student '{student.full_name}' was successfully enrolled in {enrollment.class_offering}."
            )
            return redirect('student_detail', student_id=student.pk)
    else:
        form = StudentEnrollmentForm(student=student)

    context = {
        'form': form,
        'student': student,
        'active_menu': 'students',
        'page_title': f"Enroll Student: {student.full_name}",
    }
    return render(request, 'students/student_enroll.html', context)


# ---------------------------------------------------------------------------
# 6. STUDENT STATUS TRANSITION
# ---------------------------------------------------------------------------

@require_POST
@registrar_required
def student_status_view(request, student_id):
    """
    Updates the academic status of a student (e.g. Active, Transferred, Withdrawn, Graduated).
    Permanently retains the record in the database for historical and transcript purposes.
    """
    student = get_object_or_404(Student, pk=student_id)
    form = StudentStatusUpdateForm(request.POST)

    if form.is_valid():
        old_status = student.status
        new_status = form.cleaned_data['status']
        remarks = form.cleaned_data['remarks']

        student.status = new_status
        student.save(update_fields=['status'])

        # If student is no longer active, update current active enrollment status if appropriate
        if new_status in ('TRANSFERRED', 'WITHDRAWN', 'DROPPED'):
            StudentEnrollment.objects.filter(
                student=student,
                status='ACTIVE'
            ).update(status='WITHDRAWN')

        StudentService.log_audit(
            request,
            'STATUS_CHANGE',
            student,
            {
                'old_status': old_status,
                'new_status': new_status,
                'remarks': remarks,
            }
        )

        messages.success(
            request,
            f"Status for student '{student.full_name}' updated from {old_status} to {new_status}."
        )
    else:
        messages.error(request, "Failed to update status. Please provide a mandatory reason.")

    return redirect('student_detail', student_id=student.pk)
