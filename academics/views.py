"""
Academic Management Views for SSMS.

Implements role-gated views for:
  - Academic Year lifecycle (creation, activation, closing, reopening)
  - Grade levels, Sections, Curriculum Streams, and Subjects
  - Class Offerings (classroom section provisioning per year)
  - Curriculum Matrix (allocating subjects to grades and streams)
  - Student Class Enrollment (individual & batch with duplicate prevention)
  - Teacher Classroom Allocation (integrating TeacherAssignment)
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied, ValidationError
from django.views.decorators.http import require_POST
from django.db.models import Count, Q

from accounts.decorators import (
    any_authenticated_role_required,
    management_staff_required,
    principal_or_registrar_required,
)
from academics.models import AcademicYear, Grade, Section, Stream, Subject, CurriculumSubject, ClassOffering
from students.models import Student, StudentEnrollment
from teachers.models import Teacher, TeacherAssignment
from core.models import AuditLog
from academics.forms import (
    AcademicYearForm,
    GradeForm,
    SectionForm,
    StreamForm,
    SubjectForm,
    ClassOfferingForm,
    CurriculumSubjectForm,
    ClassEnrollmentForm,
    ClassTeacherAssignmentForm,
)
from academics.services import (
    AcademicYearService,
    StructureService,
    ClassOfferingService,
    CurriculumService,
    ClassEnrollmentService,
    AcademicAuditService,
)


# -----------------------------------------------------------------------------
# ACADEMIC YEARS
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def academic_year_list_view(request):
    """Lists all academic years with current year highlight and management actions."""
    years = AcademicYear.objects.annotate(
        offering_count=Count('class_offerings', distinct=True),
        enrollment_count=Count('class_offerings__student_enrollments', distinct=True)
    ).order_by('-start_date')

    current_year = AcademicYearService.get_current_year()
    user_role = request.user.role.code if request.user.role else ('ADMIN' if request.user.is_superuser else None)
    can_manage = user_role in ['REGISTRAR', 'ADMIN']

    context = {
        'years': years,
        'current_year': current_year,
        'can_manage': can_manage,
        'active_menu': 'academics_years',
        'page_title': 'Academic Years & Calendar',
    }
    return render(request, 'academics/academic_years.html', context)


@management_staff_required
def academic_year_create_view(request):
    """Creates a new academic year."""
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    if request.method == 'POST':
        form = AcademicYearForm(request.POST)
        if form.is_valid():
            year = form.save()
            AcademicAuditService.log(
                request,
                'CREATE',
                'AcademicYear',
                year.code,
                {'name': year.name, 'start_date': str(year.start_date), 'end_date': str(year.end_date)}
            )
            messages.success(request, f"Academic Year '{year.name}' created successfully.")
            return redirect('academics_years')
    else:
        form = AcademicYearForm()

    context = {
        'form': form,
        'is_edit': False,
        'active_menu': 'academics_years',
        'page_title': 'Create Academic Year',
    }
    return render(request, 'academics/academic_year_form.html', context)


@management_staff_required
def academic_year_edit_view(request, year_id):
    """Edits an existing academic year."""
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    year = get_object_or_404(AcademicYear, pk=year_id)

    if request.method == 'POST':
        form = AcademicYearForm(request.POST, instance=year)
        if form.is_valid():
            year = form.save()
            AcademicAuditService.log(
                request,
                'UPDATE',
                'AcademicYear',
                year.code,
                {'name': year.name, 'is_current': year.is_current, 'is_closed': year.is_closed}
            )
            messages.success(request, f"Academic Year '{year.name}' updated successfully.")
            return redirect('academics_years')
    else:
        form = AcademicYearForm(instance=year)

    context = {
        'form': form,
        'year': year,
        'is_edit': True,
        'active_menu': 'academics_years',
        'page_title': f"Edit Academic Year - {year.name}",
    }
    return render(request, 'academics/academic_year_form.html', context)


@require_POST
@management_staff_required
def academic_year_activate_view(request, year_id):
    """Sets the designated academic year as active and deactivates others."""
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    year = get_object_or_404(AcademicYear, pk=year_id)
    try:
        AcademicYearService.activate_year(year, request=request)
        messages.success(request, f"Academic Year '{year.name}' is now the active academic session.")
    except ValidationError as e:
        messages.error(request, str(e))
    return redirect('academics_years')


@require_POST
@management_staff_required
def academic_year_close_view(request, year_id):
    """Locks an academic year against further grade/enrollment changes."""
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    year = get_object_or_404(AcademicYear, pk=year_id)
    AcademicYearService.close_year(year, request=request)
    messages.warning(request, f"Academic Year '{year.name}' is now closed and locked.")
    return redirect('academics_years')


@require_POST
@management_staff_required
def academic_year_reopen_view(request, year_id):
    """Re-opens a closed academic year for administrative adjustments."""
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    year = get_object_or_404(AcademicYear, pk=year_id)
    AcademicYearService.reopen_year(year, request=request)
    messages.info(request, f"Academic Year '{year.name}' has been re-opened.")
    return redirect('academics_years')


# -----------------------------------------------------------------------------
# GRADES, SECTIONS & STREAMS
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def grades_sections_view(request):
    """Consolidated dashboard for Grades, Sections, and Streams."""
    grades = Grade.objects.annotate(offerings_count=Count('class_offerings')).order_by('level')
    sections = Section.objects.annotate(offerings_count=Count('class_offerings')).order_by('name')
    streams = Stream.objects.annotate(offerings_count=Count('class_offerings')).order_by('name')

    user_role = request.user.role.code if request.user.role else ('ADMIN' if request.user.is_superuser else None)
    can_manage = user_role in ['REGISTRAR', 'ADMIN']

    context = {
        'grades': grades,
        'sections': sections,
        'streams': streams,
        'can_manage': can_manage,
        'active_menu': 'academics_grades',
        'page_title': 'Grades, Sections & Streams',
    }
    return render(request, 'academics/grades_sections.html', context)


@management_staff_required
def grade_create_view(request):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    if request.method == 'POST':
        form = GradeForm(request.POST)
        if form.is_valid():
            g = form.save()
            AcademicAuditService.log(request, 'CREATE', 'Grade', g.name, {'level': g.level})
            messages.success(request, f"Grade Level '{g.name}' created.")
            return redirect('academics_grades')
    else:
        form = GradeForm()
    return render(request, 'academics/structure_form.html', {
        'form': form, 'title': 'Add Grade Level', 'active_menu': 'academics_grades'
    })


@management_staff_required
def grade_edit_view(request, grade_id):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    grade = get_object_or_404(Grade, pk=grade_id)
    if request.method == 'POST':
        form = GradeForm(request.POST, instance=grade)
        if form.is_valid():
            g = form.save()
            AcademicAuditService.log(request, 'UPDATE', 'Grade', g.name, {'level': g.level, 'is_active': g.is_active})
            messages.success(request, f"Grade Level '{g.name}' updated.")
            return redirect('academics_grades')
    else:
        form = GradeForm(instance=grade)
    return render(request, 'academics/structure_form.html', {
        'form': form, 'title': f"Edit {grade.name}", 'active_menu': 'academics_grades'
    })


@require_POST
@management_staff_required
def grade_toggle_view(request, grade_id):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    g = StructureService.toggle_active_state(Grade, grade_id, request=request)
    state_str = "activated" if g.is_active else "deactivated"
    messages.info(request, f"Grade '{g.name}' has been {state_str}.")
    return redirect('academics_grades')


@management_staff_required
def section_create_view(request):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    if request.method == 'POST':
        form = SectionForm(request.POST)
        if form.is_valid():
            s = form.save()
            AcademicAuditService.log(request, 'CREATE', 'Section', s.name)
            messages.success(request, f"Section '{s.name}' created.")
            return redirect('academics_grades')
    else:
        form = SectionForm()
    return render(request, 'academics/structure_form.html', {
        'form': form, 'title': 'Add Classroom Section', 'active_menu': 'academics_grades'
    })


@management_staff_required
def section_edit_view(request, section_id):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    sec = get_object_or_404(Section, pk=section_id)
    if request.method == 'POST':
        form = SectionForm(request.POST, instance=sec)
        if form.is_valid():
            s = form.save()
            AcademicAuditService.log(request, 'UPDATE', 'Section', s.name, {'is_active': s.is_active})
            messages.success(request, f"Section '{s.name}' updated.")
            return redirect('academics_grades')
    else:
        form = SectionForm(instance=sec)
    return render(request, 'academics/structure_form.html', {
        'form': form, 'title': f"Edit Section {sec.name}", 'active_menu': 'academics_grades'
    })


@require_POST
@management_staff_required
def section_toggle_view(request, section_id):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    s = StructureService.toggle_active_state(Section, section_id, request=request)
    state_str = "activated" if s.is_active else "deactivated"
    messages.info(request, f"Section '{s.name}' has been {state_str}.")
    return redirect('academics_grades')


@management_staff_required
def stream_create_view(request):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    if request.method == 'POST':
        form = StreamForm(request.POST)
        if form.is_valid():
            st = form.save()
            AcademicAuditService.log(request, 'CREATE', 'Stream', st.code, {'name': st.name})
            messages.success(request, f"Stream '{st.name}' created.")
            return redirect('academics_grades')
    else:
        form = StreamForm()
    return render(request, 'academics/structure_form.html', {
        'form': form, 'title': 'Add Curriculum Stream', 'active_menu': 'academics_grades'
    })


@management_staff_required
def stream_edit_view(request, stream_id):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    st = get_object_or_404(Stream, pk=stream_id)
    if request.method == 'POST':
        form = StreamForm(request.POST, instance=st)
        if form.is_valid():
            s = form.save()
            AcademicAuditService.log(request, 'UPDATE', 'Stream', s.code, {'is_active': s.is_active})
            messages.success(request, f"Stream '{s.name}' updated.")
            return redirect('academics_grades')
    else:
        form = StreamForm(instance=st)
    return render(request, 'academics/structure_form.html', {
        'form': form, 'title': f"Edit Stream {st.name}", 'active_menu': 'academics_grades'
    })


@require_POST
@management_staff_required
def stream_toggle_view(request, stream_id):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    s = StructureService.toggle_active_state(Stream, stream_id, request=request)
    state_str = "activated" if s.is_active else "deactivated"
    messages.info(request, f"Stream '{s.name}' has been {state_str}.")
    return redirect('academics_grades')


# -----------------------------------------------------------------------------
# MASTER SUBJECTS
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def subject_list_view(request):
    """Lists all master catalog subjects with curriculum mappings and workload count."""
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()

    subjects = Subject.objects.annotate(
        curriculum_count=Count('curriculum_allocations', distinct=True),
        assignment_count=Count('teacher_assignments', distinct=True)
    ).all()

    if search_query:
        subjects = subjects.filter(
            Q(code__icontains=search_query) | Q(name__icontains=search_query) | Q(description__icontains=search_query)
        )

    if status_filter == 'active':
        subjects = subjects.filter(is_active=True)
    elif status_filter == 'inactive':
        subjects = subjects.filter(is_active=False)

    user_role = request.user.role.code if request.user.role else ('ADMIN' if request.user.is_superuser else None)
    can_manage = user_role in ['REGISTRAR', 'ADMIN']

    context = {
        'subjects': subjects,
        'search_query': search_query,
        'status_filter': status_filter,
        'can_manage': can_manage,
        'active_menu': 'academics_subjects',
        'page_title': 'Master Subject Catalog',
    }
    return render(request, 'academics/subjects.html', context)


@management_staff_required
def subject_create_view(request):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    if request.method == 'POST':
        form = SubjectForm(request.POST)
        if form.is_valid():
            s = form.save()
            AcademicAuditService.log(request, 'CREATE', 'Subject', s.code, {'name': s.name})
            messages.success(request, f"Subject '{s.name}' ({s.code}) added successfully.")
            return redirect('academics_subjects')
    else:
        form = SubjectForm()

    context = {
        'form': form,
        'title': 'Add New Subject',
        'active_menu': 'academics_subjects',
    }
    return render(request, 'academics/structure_form.html', context)


@management_staff_required
def subject_edit_view(request, subject_id):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    subj = get_object_or_404(Subject, pk=subject_id)
    if request.method == 'POST':
        form = SubjectForm(request.POST, instance=subj)
        if form.is_valid():
            s = form.save()
            AcademicAuditService.log(request, 'UPDATE', 'Subject', s.code, {'name': s.name, 'is_active': s.is_active})
            messages.success(request, f"Subject '{s.name}' updated successfully.")
            return redirect('academics_subjects')
    else:
        form = SubjectForm(instance=subj)

    context = {
        'form': form,
        'title': f"Edit Subject - {subj.name}",
        'active_menu': 'academics_subjects',
    }
    return render(request, 'academics/structure_form.html', context)


@require_POST
@management_staff_required
def subject_toggle_view(request, subject_id):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    s = StructureService.toggle_active_state(Subject, subject_id, request=request)
    state_str = "activated" if s.is_active else "deactivated"
    messages.info(request, f"Subject '{s.name}' has been {state_str}.")
    return redirect('academics_subjects')


# -----------------------------------------------------------------------------
# CLASS OFFERINGS & CLASSROOM MANAGEMENT
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def class_offering_list_view(request):
    """Lists class offerings for an academic year with enrollment counts, filters, and capacity."""
    selected_year_id = request.GET.get('year')
    selected_grade_id = request.GET.get('grade')
    selected_stream_id = request.GET.get('stream')

    academic_years = AcademicYear.objects.all().order_by('-start_date')
    current_year = AcademicYearService.get_current_year()

    # Default to current academic year if none selected
    if not selected_year_id and current_year:
        selected_year_id = str(current_year.pk)

    offerings = ClassOffering.objects.select_related(
        'academic_year', 'grade', 'section', 'stream'
    ).prefetch_related('student_enrollments', 'teacher_assignments').annotate(
        enrolled_count=Count('student_enrollments', filter=Q(student_enrollments__status='ACTIVE'), distinct=True),
        assigned_teacher_count=Count('teacher_assignments', distinct=True),
    ).order_by('grade__level', 'section__name', 'stream__name')

    if selected_year_id:
        offerings = offerings.filter(academic_year_id=selected_year_id)
    if selected_grade_id:
        offerings = offerings.filter(grade_id=selected_grade_id)
    if selected_stream_id:
        offerings = offerings.filter(stream_id=selected_stream_id)

    grades = Grade.objects.filter(is_active=True).order_by('level')
    streams = Stream.objects.filter(is_active=True).order_by('name')

    total_offerings = offerings.count()
    total_enrolled = sum(o.enrolled_count for o in offerings)

    # Paginate
    paginator = Paginator(offerings, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    user_role = request.user.role.code if request.user.role else ('ADMIN' if request.user.is_superuser else None)
    can_manage = user_role in ['REGISTRAR', 'ADMIN']

    context = {
        'offerings': page_obj,
        'page_obj': page_obj,
        'academic_years': academic_years,
        'grades': grades,
        'streams': streams,
        'selected_year': selected_year_id,
        'selected_grade': selected_grade_id,
        'selected_stream': selected_stream_id,
        'total_offerings': total_offerings,
        'total_enrolled': total_enrolled,
        'current_year': current_year,
        'can_manage': can_manage,
        'active_menu': 'academics_classes',
        'page_title': 'Classroom Offerings Directory',
    }
    return render(request, 'academics/class_offerings.html', context)


@management_staff_required
def class_offering_create_view(request):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    if request.method == 'POST':
        form = ClassOfferingForm(request.POST)
        if form.is_valid():
            offering = form.save()
            AcademicAuditService.log(
                request,
                'CREATE',
                'ClassOffering',
                str(offering),
                {'capacity': offering.max_capacity}
            )
            messages.success(request, f"Classroom '{offering}' created successfully.")
            return redirect('class_offering_detail', offering_id=offering.pk)
    else:
        form = ClassOfferingForm()

    context = {
        'form': form,
        'active_menu': 'academics_classes',
        'page_title': 'Add New Class Offering',
    }
    return render(request, 'academics/class_offering_form.html', context)


@management_staff_required
def class_offering_edit_view(request, offering_id):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    offering = get_object_or_404(ClassOffering, pk=offering_id)
    if request.method == 'POST':
        form = ClassOfferingForm(request.POST, instance=offering)
        if form.is_valid():
            off = form.save()
            AcademicAuditService.log(
                request,
                'UPDATE',
                'ClassOffering',
                str(off),
                {'capacity': off.max_capacity}
            )
            messages.success(request, f"Classroom '{off}' updated successfully.")
            return redirect('class_offering_detail', offering_id=off.pk)
    else:
        form = ClassOfferingForm(instance=offering)

    context = {
        'form': form,
        'offering': offering,
        'active_menu': 'academics_classes',
        'page_title': f"Edit Class Offering - {offering.display_name}",
    }
    return render(request, 'academics/class_offering_form.html', context)


@any_authenticated_role_required
def class_offering_detail_view(request, offering_id):
    """
    Detailed classroom dashboard showing:
      - Enrolled students list (with gender, admission number, status)
      - Assigned faculty & subjects
      - Capacity & enrollment KPI metrics
      - Enrollment and assignment forms

    Access control:
      - ADMIN / PRINCIPAL / REGISTRAR: can view any class offering
      - TEACHER: can only view class offerings they are assigned to
    """
    offering = get_object_or_404(
        ClassOffering.objects.select_related('academic_year', 'grade', 'section', 'stream'),
        pk=offering_id
    )

    user_role = request.user.role.code if request.user.role else ('ADMIN' if request.user.is_superuser else None)

    # Teachers may only see their own assigned classes
    if user_role == 'TEACHER':
        teacher_profile = getattr(request.user, 'teacher_profile', None)
        if teacher_profile is None:
            raise PermissionDenied
        is_assigned = offering.teacher_assignments.filter(teacher=teacher_profile).exists()
        if not is_assigned:
            raise PermissionDenied

    enrollments = offering.student_enrollments.select_related('student').order_by('student__first_name', 'student__father_name')
    assignments = offering.teacher_assignments.select_related('teacher', 'subject').order_by('subject__name')

    # Student gender stats
    male_count = enrollments.filter(student__gender='M', status='ACTIVE').count()
    female_count = enrollments.filter(student__gender='F', status='ACTIVE').count()
    active_enrollment_count = male_count + female_count

    # user_role already determined above for access control
    can_manage = user_role in ['REGISTRAR', 'ADMIN'] and not offering.academic_year.is_closed

    enrollment_form = ClassEnrollmentForm(class_offering=offering) if can_manage else None
    teacher_form = ClassTeacherAssignmentForm(class_offering=offering) if can_manage else None

    context = {
        'offering': offering,
        'enrollments': enrollments,
        'assignments': assignments,
        'male_count': male_count,
        'female_count': female_count,
        'active_enrollment_count': active_enrollment_count,
        'can_manage': can_manage,
        'enrollment_form': enrollment_form,
        'teacher_form': teacher_form,
        'active_menu': 'academics_classes',
        'page_title': f"Classroom: {offering.display_name}",
    }
    return render(request, 'academics/class_offering_detail.html', context)


# -----------------------------------------------------------------------------
# CLASSROOM ENROLLMENT ACTIONS
# -----------------------------------------------------------------------------

@require_POST
@management_staff_required
def class_enroll_student_view(request, offering_id):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    offering = get_object_or_404(ClassOffering, pk=offering_id)
    form = ClassEnrollmentForm(request.POST, class_offering=offering)

    if form.is_valid():
        student = form.cleaned_data['student']
        try:
            ClassEnrollmentService.enroll_student(
                student=student,
                class_offering=offering,
                request=request
            )
            messages.success(request, f"Enrolled {student.full_name} ({student.admission_number}) into {offering.display_name}.")
        except ValidationError as e:
            messages.error(request, str(e))
    else:
        messages.error(request, "Failed to enroll student. Please check the selection.")

    return redirect('class_offering_detail', offering_id=offering.pk)


@require_POST
@management_staff_required
def class_remove_student_view(request, offering_id, enrollment_id):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    offering = get_object_or_404(ClassOffering, pk=offering_id)
    enrollment = get_object_or_404(StudentEnrollment, pk=enrollment_id, class_offering=offering)

    student_name = enrollment.student.full_name
    adm_num = enrollment.student.admission_number

    AcademicAuditService.log(
        request,
        'DELETE',
        'StudentEnrollment',
        f"{adm_num} removed from {offering}",
        {'student': student_name}
    )

    enrollment.delete()
    messages.warning(request, f"Removed {student_name} ({adm_num}) from {offering.display_name}.")
    return redirect('class_offering_detail', offering_id=offering.pk)


# -----------------------------------------------------------------------------
# CLASSROOM TEACHER ALLOCATION ACTIONS
# -----------------------------------------------------------------------------

@require_POST
@management_staff_required
def class_assign_teacher_view(request, offering_id):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    offering = get_object_or_404(ClassOffering, pk=offering_id)
    form = ClassTeacherAssignmentForm(request.POST, class_offering=offering)

    if form.is_valid():
        assignment = form.save(commit=False)
        assignment.class_offering = offering
        assignment.academic_year = offering.academic_year
        assignment.save()

        AcademicAuditService.log(
            request,
            'CREATE',
            'TeacherAssignment',
            f"{assignment.teacher.employee_id} -> {offering} [{assignment.subject.code}]",
            {'teacher': assignment.teacher.full_name, 'subject': assignment.subject.name}
        )
        messages.success(request, f"Assigned {assignment.teacher.full_name} for {assignment.subject.name}.")
    else:
        for err in form.non_field_errors():
            messages.error(request, err)

    return redirect('class_offering_detail', offering_id=offering.pk)


@require_POST
@management_staff_required
def class_remove_teacher_view(request, offering_id, assignment_id):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    offering = get_object_or_404(ClassOffering, pk=offering_id)
    assignment = get_object_or_404(TeacherAssignment, pk=assignment_id, class_offering=offering)

    teacher_name = assignment.teacher.full_name
    subj_name = assignment.subject.name

    AcademicAuditService.log(
        request,
        'DELETE',
        'TeacherAssignment',
        f"{assignment.teacher.employee_id} removed from {offering} [{assignment.subject.code}]"
    )

    assignment.delete()
    messages.warning(request, f"Removed {teacher_name} ({subj_name}) from {offering.display_name}.")
    return redirect('class_offering_detail', offering_id=offering.pk)


# -----------------------------------------------------------------------------
# CURRICULUM MANAGEMENT
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def curriculum_list_view(request):
    """Curriculum matrix allocating subjects to Grade levels and Streams."""
    selected_grade_id = request.GET.get('grade')
    grades = Grade.objects.filter(is_active=True).order_by('level')

    curriculum_qs = CurriculumSubject.objects.select_related('grade', 'stream', 'subject').order_by(
        'grade__level', 'stream__name', 'subject__name'
    )

    if selected_grade_id:
        curriculum_qs = curriculum_qs.filter(grade_id=selected_grade_id)

    user_role = request.user.role.code if request.user.role else ('ADMIN' if request.user.is_superuser else None)
    can_manage = user_role in ['REGISTRAR', 'ADMIN']

    form = CurriculumSubjectForm() if can_manage else None

    context = {
        'curriculum_items': curriculum_qs,
        'grades': grades,
        'selected_grade_id': int(selected_grade_id) if selected_grade_id else None,
        'can_manage': can_manage,
        'form': form,
        'active_menu': 'academics_curriculum',
        'page_title': 'Curriculum Subject Allocations',
    }
    return render(request, 'academics/curriculum.html', context)


@require_POST
@management_staff_required
def curriculum_create_view(request):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    form = CurriculumSubjectForm(request.POST)
    if form.is_valid():
        curr = form.save()
        AcademicAuditService.log(
            request,
            'CREATE',
            'CurriculumSubject',
            str(curr),
            {'grade': curr.grade.name, 'subject': curr.subject.name}
        )
        messages.success(request, f"Subject '{curr.subject.name}' added to {curr.grade.name} curriculum.")
    else:
        for err in form.non_field_errors():
            messages.error(request, err)

    return redirect('academics_curriculum')


@require_POST
@management_staff_required
def curriculum_delete_view(request, curriculum_id):
    user_role = request.user.role.code if request.user.role else None
    if user_role == 'PRINCIPAL':
        raise PermissionDenied

    curr = get_object_or_404(CurriculumSubject, pk=curriculum_id)
    AcademicAuditService.log(
        request,
        'DELETE',
        'CurriculumSubject',
        str(curr)
    )
    curr.delete()
    messages.warning(request, "Subject removed from curriculum.")
    return redirect('academics_curriculum')
