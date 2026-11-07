"""
Teacher Management Views for SSMS.

Implements role-based access control, secure directory search/filter/pagination,
profile view, assignment workflows, and employment status lifecycle tracking.
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_POST
from django.db.models import Count, Q

from accounts.decorators import (
    any_authenticated_role_required,
    management_staff_required,
    teacher_required,
    registrar_required,
)
from teachers.models import Teacher, TeacherAssignment
from academics.models import AcademicYear, ClassOffering, Subject
from students.models import StudentEnrollment
from attendance.models import AttendanceSession
from core.models import AuditLog
from teachers.forms import (
    TeacherRegistrationForm,
    TeacherEditForm,
    TeacherStatusUpdateForm,
    TeacherAssignmentForm,
)
from teachers.services import TeacherService


@any_authenticated_role_required
def teacher_list_view(request):
    """
    Teacher Directory.
    Principals, Registrars, and Admins have administrative oversight.
    Teachers have read-only visibility into faculty directory.
    """
    search_query = request.GET.get('q', '').strip()
    specialization = request.GET.get('specialization', '').strip()
    qualification = request.GET.get('qualification', '').strip()
    status = request.GET.get('status', '').strip()
    sort_by = request.GET.get('sort_by', 'name_asc')
    page_number = request.GET.get('page', 1)

    teachers_qs = TeacherService.get_teachers_directory(
        user=request.user,
        search_query=search_query,
        qualification=qualification,
        specialization=specialization,
        status=status,
        sort_by=sort_by
    )

    paginator = Paginator(teachers_qs, 20)
    page_obj = paginator.get_page(page_number)

    # Distinct specializations for filter dropdown
    specializations = (
        Teacher.objects.values_list('specialization', flat=True)
        .distinct()
        .order_by('specialization')
    )

    user_role = request.user.role.code if request.user.role else ('ADMIN' if request.user.is_superuser else None)
    can_manage = user_role in ['REGISTRAR', 'ADMIN']

    context = {
        'page_obj': page_obj,
        'teachers': page_obj.object_list,
        'specializations': [s for s in specializations if s],
        'status_choices': Teacher.STATUS_CHOICES,
        'total_teachers': Teacher.objects.count(),
        'active_teachers': Teacher.objects.filter(employment_status='ACTIVE').count(),
        'on_leave_teachers': Teacher.objects.filter(employment_status='ON_LEAVE').count(),
        'search_query': search_query,
        'selected_specialization': specialization,
        'selected_status': status,
        'selected_sort': sort_by,
        'can_manage': can_manage,
        'active_menu': 'teachers',
        'page_title': 'Teacher Management',
    }
    return render(request, 'teachers/teacher_list.html', context)


@management_staff_required
def teacher_register_view(request):
    """
    Registers a new teacher.
    Restricted to Registrar and Admin (Principal has review/view-only access).
    """
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        messages.error(request, "Principals have view-only access to faculty records.")
        raise PermissionDenied

    if request.method == 'POST':
        form = TeacherRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            teacher = form.save()

            # Log audit
            TeacherService.log_audit(
                request,
                'CREATE',
                teacher,
                {
                    'employee_id': teacher.employee_id,
                    'full_name': teacher.full_name,
                    'specialization': teacher.specialization,
                    'qualification': teacher.qualification,
                    'employment_status': teacher.employment_status,
                }
            )

            messages.success(request, f"Teacher {teacher.full_name} ({teacher.employee_id}) successfully registered.")
            return redirect('teacher_detail', teacher_id=teacher.pk)
    else:
        form = TeacherRegistrationForm()

    context = {
        'form': form,
        'active_menu': 'teachers',
        'page_title': 'Register New Teacher',
    }
    return render(request, 'teachers/teacher_register.html', context)


@any_authenticated_role_required
def teacher_detail_view(request, teacher_id):
    """
    Detailed teacher profile view with assignments, workload, and audit logs.
    Teachers can ONLY view their own profile.
    Principals, Registrars, and Admins can view any teacher.
    """
    teacher = get_object_or_404(Teacher, pk=teacher_id)
    user_role = request.user.role.code if request.user.role else ('ADMIN' if request.user.is_superuser else None)

    # Scoped access for teachers: only their own profile
    if user_role == 'TEACHER':
        if not teacher.user or teacher.user_id != request.user.id:
            raise PermissionDenied("You are only permitted to view your own teacher profile.")

    can_manage = user_role in ['REGISTRAR', 'ADMIN']
    can_review = user_role in ['PRINCIPAL', 'REGISTRAR', 'ADMIN']

    # Current academic year
    current_ay = AcademicYear.objects.filter(is_current=True).first()

    # Active and historical assignments
    assignments = (
        TeacherAssignment.objects.filter(teacher=teacher)
        .select_related(
            'class_offering__grade',
            'class_offering__section',
            'class_offering__stream',
            'class_offering__academic_year',
            'subject',
            'academic_year'
        )
        .order_by('-academic_year__start_date', 'class_offering__grade__level', 'subject__name')
    )

    current_assignments = []
    past_assignments = []
    assigned_class_ids = set()

    for a in assignments:
        is_curr = False
        if current_ay and (a.academic_year_id == current_ay.id or (a.class_offering and a.class_offering.academic_year_id == current_ay.id)):
            is_curr = True
            current_assignments.append(a)
            if a.class_offering_id:
                assigned_class_ids.add(a.class_offering_id)
        else:
            past_assignments.append(a)

    # Workload summary
    total_students = StudentEnrollment.objects.filter(
        class_offering_id__in=assigned_class_ids,
        status='ACTIVE'
    ).count()

    # Recent attendance sessions recorded
    recent_attendance = AttendanceSession.objects.filter(
        recorded_by=teacher
    ).select_related('class_offering__grade', 'class_offering__section').order_by('-date')[:5]

    # Audit log history
    audit_logs = AuditLog.objects.filter(
        entity_name__in=['Teacher', 'TeacherAssignment'],
        record_id__icontains=teacher.employee_id
    ).order_by('-timestamp')[:10]

    context = {
        'teacher': teacher,
        'current_assignments': current_assignments,
        'past_assignments': past_assignments,
        'total_assigned_classes': len(assigned_class_ids),
        'total_students_taught': total_students,
        'recent_attendance': recent_attendance,
        'audit_logs': audit_logs,
        'can_manage': can_manage,
        'can_review': can_review,
        'current_ay': current_ay,
        'active_menu': 'teachers',
        'page_title': f"Teacher Profile - {teacher.full_name}",
    }
    return render(request, 'teachers/teacher_detail.html', context)


@teacher_required
def teacher_my_profile_view(request):
    """
    Dedicated shortcut view allowing logged-in teachers to jump directly to their own profile.
    """
    teacher = Teacher.objects.filter(user=request.user).first()
    if not teacher:
        messages.warning(request, "No teacher staff profile has been linked to your user account yet.")
        return redirect('dashboard')
    return teacher_detail_view(request, teacher_id=teacher.pk)


@management_staff_required
def teacher_edit_view(request, teacher_id):
    """
    Updates teacher profile data and logs structured field-level diffs.
    Restricted to Registrar and Admin.
    """
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    teacher = get_object_or_404(Teacher, pk=teacher_id)

    if request.method == 'POST':
        form = TeacherEditForm(request.POST, request.FILES, instance=teacher)
        if form.is_valid():
            diff = form.get_diff()
            teacher = form.save()

            if diff:
                TeacherService.log_audit(request, 'UPDATE', teacher, diff)

            messages.success(request, f"Profile for {teacher.full_name} successfully updated.")
            return redirect('teacher_detail', teacher_id=teacher.pk)
    else:
        form = TeacherEditForm(instance=teacher)

    context = {
        'form': form,
        'teacher': teacher,
        'active_menu': 'teachers',
        'page_title': f"Edit Teacher - {teacher.full_name}",
    }
    return render(request, 'teachers/teacher_edit.html', context)


@management_staff_required
def teacher_status_view(request, teacher_id):
    """
    Manages teacher employment status (Active, Inactive, On Leave, Transferred).
    Preserves all historical records; soft lifecycle changes only.
    """
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    teacher = get_object_or_404(Teacher, pk=teacher_id)

    if request.method == 'POST':
        form = TeacherStatusUpdateForm(request.POST, teacher=teacher)
        if form.is_valid():
            new_status = form.cleaned_data['employment_status']
            remarks = form.cleaned_data['remarks']

            TeacherService.update_teacher_status(
                teacher=teacher,
                new_status=new_status,
                remarks=remarks,
                request=request
            )
            messages.success(
                request,
                f"Status for {teacher.full_name} updated to {dict(Teacher.STATUS_CHOICES).get(new_status)}."
            )
            return redirect('teacher_detail', teacher_id=teacher.pk)
    else:
        form = TeacherStatusUpdateForm(teacher=teacher)

    context = {
        'form': form,
        'teacher': teacher,
        'active_menu': 'teachers',
        'page_title': f"Update Status - {teacher.full_name}",
    }
    return render(request, 'teachers/teacher_status.html', context)


@management_staff_required
def teacher_assign_view(request, teacher_id):
    """
    Allocates a teacher to a specific Class Offering and Subject.
    Restricted to Registrar and Admin.
    """
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    teacher = get_object_or_404(Teacher, pk=teacher_id)

    if request.method == 'POST':
        form = TeacherAssignmentForm(request.POST, teacher=teacher)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.teacher = teacher
            assignment.save()

            TeacherService.log_assignment_audit(
                request,
                'CREATE',
                assignment,
                {
                    'teacher_id': teacher.employee_id,
                    'class_offering': str(assignment.class_offering),
                    'subject': assignment.subject.name,
                    'academic_year': assignment.academic_year.name if assignment.academic_year else '',
                    'is_primary': assignment.is_primary,
                }
            )

            messages.success(
                request,
                f"Successfully assigned {teacher.full_name} to teach {assignment.subject.name} in {assignment.class_offering}."
            )
            return redirect('teacher_detail', teacher_id=teacher.pk)
    else:
        form = TeacherAssignmentForm(teacher=teacher)

    context = {
        'form': form,
        'teacher': teacher,
        'active_menu': 'teachers',
        'page_title': f"Assign Class & Subject - {teacher.full_name}",
    }
    return render(request, 'teachers/teacher_assign.html', context)


@require_POST
@management_staff_required
def teacher_assignment_delete_view(request, assignment_id):
    """
    Removes a teacher assignment.
    Restricted to Registrar and Admin.
    """
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    assignment = get_object_or_404(TeacherAssignment, pk=assignment_id)
    teacher = assignment.teacher

    TeacherService.log_assignment_audit(
        request,
        'DELETE',
        assignment,
        {
            'deleted_assignment': f"{teacher.employee_id} from {assignment.class_offering} [{assignment.subject.code}]",
        }
    )

    assignment.delete()
    messages.success(request, "Teaching assignment removed successfully.")
    return redirect('teacher_detail', teacher_id=teacher.pk)
