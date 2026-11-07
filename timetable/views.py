"""
Views for Timetable and Class Scheduling Management System.
Implements:
- Timetable Dashboard and Scheduling Hub
- Class and Teacher Weekly Visual Matrices
- Conflict Detection and Pre-saving Alerts
- Working Days, Periods, and Classroom Management
- Approval, Publication, and Revision Lifecycle
- ReportLab PDF and OpenPyXL Excel Exports
"""

from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_POST
from django.db.models import Count, Q

from accounts.decorators import (
    any_authenticated_role_required,
    management_staff_required,
    principal_or_registrar_required,
    principal_required,
    teacher_required,
    registrar_required
)
from academics.models import AcademicYear, Grade, Section, Stream, ClassOffering, Subject
from teachers.models import Teacher, TeacherAssignment

from timetable.models import (
    Classroom,
    SchoolDay,
    Period,
    Timetable,
    TimetableEntry,
    TimetableVersion,
    DAY_OF_WEEK_CHOICES,
    DAY_NAME_MAP,
)
from timetable.forms import (
    ClassroomForm,
    SchoolDayForm,
    PeriodForm,
    TimetableCreateForm,
    TimetableEntryForm,
    TimetableApprovalForm,
    TimetableCopyForm,
    TimetableFilterForm,
)
from timetable.services import (
    TimetableConfigService,
    ConflictDetectionService,
    TimetableService,
    TimetablePublicationService,
    TimetableMatrixService,
    TimetableReportService,
    TimetableAuditHelper,
)


def _get_user_role(user):
    if user.is_superuser:
        return 'ADMIN'
    if hasattr(user, 'role') and user.role:
        return user.role.code
    return 'USER'


# -----------------------------------------------------------------------------
# 1. TIMETABLE DASHBOARD
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def timetable_dashboard_view(request):
    """
    Main timetable dashboard displaying active schedules, breakdown by status,
    detected conflicts, classroom statistics, and teacher assignment metrics.
    """
    user_role = _get_user_role(request.user)
    current_year = AcademicYear.objects.filter(is_current=True).first()

    # Querysets
    timetables_qs = Timetable.objects.select_related(
        'academic_year', 'class_offering__grade', 'class_offering__section', 'created_by'
    ).order_by('-updated_at')

    # Selected year filter
    selected_year_id = request.GET.get('academic_year')
    if selected_year_id:
        timetables_qs = timetables_qs.filter(academic_year_id=selected_year_id)
        active_year = AcademicYear.objects.filter(pk=selected_year_id).first()
    else:
        active_year = current_year
        if active_year:
            timetables_qs = timetables_qs.filter(academic_year=active_year)

    # KPIs
    total_timetables = timetables_qs.count()
    published_count = timetables_qs.filter(status='PUBLISHED').count()
    draft_count = timetables_qs.filter(status='DRAFT').count()
    submitted_count = timetables_qs.filter(status='SUBMITTED').count()
    approved_count = timetables_qs.filter(status='APPROVED').count()

    total_lessons = TimetableEntry.objects.filter(
        timetable__in=timetables_qs
    ).count()

    total_classrooms = Classroom.objects.filter(is_active=True).count()
    total_periods = Period.objects.filter(is_active=True).count()

    # Detect conflicts across published timetables in active year
    all_published = timetables_qs.filter(status='PUBLISHED')
    total_conflicts = 0
    for tt in all_published:
        confs = ConflictDetectionService.validate_entire_timetable(tt)
        total_conflicts += len([c for c in confs if c['severity'] == 'ERROR'])

    recent_timetables = timetables_qs[:8]
    all_years = AcademicYear.objects.all().order_by('-start_date')

    # If teacher user, find their teacher profile for quick link
    teacher_profile = None
    if user_role == 'TEACHER':
        teacher_profile = Teacher.objects.filter(user=request.user).first()

    context = {
        'active_menu': 'timetable',
        'page_title': 'Timetable & Scheduling Dashboard',
        'user_role': user_role,
        'current_year': active_year,
        'all_years': all_years,
        'total_timetables': total_timetables,
        'published_count': published_count,
        'draft_count': draft_count,
        'submitted_count': submitted_count,
        'approved_count': approved_count,
        'total_lessons': total_lessons,
        'total_classrooms': total_classrooms,
        'total_periods': total_periods,
        'total_conflicts': total_conflicts,
        'recent_timetables': recent_timetables,
        'teacher_profile': teacher_profile,
        'is_management': user_role in ['ADMIN', 'REGISTRAR', 'PRINCIPAL'],
        'can_approve': user_role in ['ADMIN', 'PRINCIPAL'],
    }
    return render(request, 'timetable/dashboard.html', context)


# -----------------------------------------------------------------------------
# 2. TIMETABLE LIST
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def timetable_list_view(request):
    """Filterable directory of all class offering timetables across grades and years."""
    user_role = _get_user_role(request.user)
    timetables_qs = Timetable.objects.select_related(
        'academic_year', 'class_offering__grade', 'class_offering__section', 'class_offering__stream', 'created_by'
    ).order_by('-academic_year__start_date', 'class_offering__grade__level', 'class_offering__section__name', '-version')

    # Filtering
    year_id = request.GET.get('academic_year')
    if year_id:
        timetables_qs = timetables_qs.filter(academic_year_id=year_id)

    grade_id = request.GET.get('grade')
    if grade_id:
        timetables_qs = timetables_qs.filter(class_offering__grade_id=grade_id)

    status_filter = request.GET.get('status')
    if status_filter:
        timetables_qs = timetables_qs.filter(status=status_filter)

    search_q = request.GET.get('q', '').strip()
    if search_q:
        timetables_qs = timetables_qs.filter(
            Q(name__icontains=search_q) |
            Q(class_offering__grade__name__icontains=search_q) |
            Q(class_offering__section__name__icontains=search_q)
        )

    paginator = Paginator(timetables_qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    all_years = AcademicYear.objects.all().order_by('-start_date')
    all_grades = Grade.objects.filter(is_active=True).order_by('level')

    context = {
        'active_menu': 'timetable',
        'page_title': 'Class Timetables Directory',
        'user_role': user_role,
        'page_obj': page_obj,
        'timetables': page_obj,
        'all_years': all_years,
        'all_grades': all_grades,
        'selected_year': year_id,
        'selected_grade': grade_id,
        'status_filter': status_filter,
        'search_q': search_q,
        'is_management': user_role in ['ADMIN', 'REGISTRAR', 'PRINCIPAL'],
    }
    return render(request, 'timetable/timetable_list.html', context)


# -----------------------------------------------------------------------------
# 3. TIMETABLE CREATION
# -----------------------------------------------------------------------------

@management_staff_required
def timetable_create_view(request):
    """Creates a new draft timetable for a class offering."""
    user_role = _get_user_role(request.user)
    if request.method == 'POST':
        form = TimetableCreateForm(request.POST)
        if form.is_valid():
            try:
                tt = TimetableService.create_timetable(
                    academic_year=form.cleaned_data['academic_year'],
                    class_offering=form.cleaned_data['class_offering'],
                    name=form.cleaned_data.get('name'),
                    valid_from=form.cleaned_data.get('valid_from'),
                    valid_until=form.cleaned_data.get('valid_until'),
                    user=request.user,
                    request=request
                )
                messages.success(request, f"Timetable draft '{tt.name}' created successfully. Now add lessons to the schedule.")
                return redirect('timetable_detail', timetable_id=tt.id)
            except ValidationError as e:
                form.add_error(None, e.message if hasattr(e, 'message') else str(e))
    else:
        form = TimetableCreateForm()

    context = {
        'active_menu': 'timetable',
        'page_title': 'Create Class Timetable',
        'form': form,
        'user_role': user_role,
    }
    return render(request, 'timetable/timetable_create.html', context)


# -----------------------------------------------------------------------------
# 4. TIMETABLE DETAIL & WEEKLY MATRIX EDITOR
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def timetable_detail_view(request, timetable_id):
    """
    Weekly interactive timetable matrix for a specific ClassOffering schedule.
    Displays days as columns, periods as rows, subject/teacher/classroom cells.
    Allows adding/editing lesson blocks and running real-time conflict audits.
    """
    timetable = get_object_or_404(
        Timetable.objects.select_related(
            'academic_year', 'class_offering__grade', 'class_offering__section', 'class_offering__stream', 'created_by', 'approved_by'
        ),
        pk=timetable_id
    )
    user_role = _get_user_role(request.user)

    matrix = TimetableMatrixService.get_class_matrix(timetable)
    conflicts = ConflictDetectionService.validate_entire_timetable(timetable)
    has_blocking = any(c['severity'] == 'ERROR' for c in conflicts)

    entry_form = TimetableEntryForm(timetable=timetable) if timetable.is_editable else None
    copy_form = TimetableCopyForm(source_timetable=timetable)

    context = {
        'active_menu': 'timetable',
        'page_title': f"Timetable: {timetable.class_offering.display_name}",
        'timetable': timetable,
        'matrix': matrix,
        'conflicts': conflicts,
        'has_blocking_conflicts': has_blocking,
        'entry_form': entry_form,
        'copy_form': copy_form,
        'user_role': user_role,
        'can_edit': timetable.is_editable and user_role in ['ADMIN', 'REGISTRAR'],
        'can_submit': timetable.status in ['DRAFT', 'REJECTED'] and timetable.entries.count() > 0 and not has_blocking and user_role in ['ADMIN', 'REGISTRAR'],
        'can_approve': timetable.status == 'SUBMITTED' and user_role in ['ADMIN', 'PRINCIPAL'],
        'can_publish': timetable.status == 'APPROVED' and user_role in ['ADMIN', 'PRINCIPAL', 'REGISTRAR'],
        'can_revise': timetable.status == 'PUBLISHED' and user_role in ['ADMIN', 'PRINCIPAL', 'REGISTRAR'],
    }
    return render(request, 'timetable/timetable_detail.html', context)


# -----------------------------------------------------------------------------
# 5. TIMETABLE LESSON ENTRY CREATION & DELETION
# -----------------------------------------------------------------------------

@require_POST
@management_staff_required
def timetable_entry_create_view(request, timetable_id):
    """Saves an individual lesson entry to the timetable with conflict validation."""
    timetable = get_object_or_404(Timetable, pk=timetable_id)
    form = TimetableEntryForm(timetable=timetable, data=request.POST)

    if form.is_valid():
        try:
            entry = TimetableService.add_lesson_entry(
                timetable=timetable,
                day_of_week=form.cleaned_data['day_of_week'],
                period=form.cleaned_data['period'],
                subject=form.cleaned_data['subject'],
                teacher=form.cleaned_data['teacher'],
                classroom=form.cleaned_data.get('classroom'),
                notes=form.cleaned_data.get('notes', ''),
                user=request.user,
                request=request
            )
            messages.success(request, f"Scheduled {entry.subject.code} on {entry.day_name} {entry.period.name}.")
        except ValidationError as e:
            msg = e.message if hasattr(e, 'message') else str(e)
            messages.error(request, msg)
    else:
        err_list = [f"{field}: {', '.join(errs)}" for field, errs in form.errors.items()]
        messages.error(request, f"Error adding lesson: {'; '.join(err_list)}")

    return redirect('timetable_detail', timetable_id=timetable.id)


@require_POST
@management_staff_required
def timetable_entry_delete_view(request, entry_id):
    """Deletes a lesson entry from an editable timetable."""
    entry = get_object_or_404(TimetableEntry, pk=entry_id)
    timetable_id = entry.timetable_id
    try:
        TimetableService.delete_lesson_entry(entry_id=entry.id, user=request.user, request=request)
        messages.success(request, "Lesson slot removed from schedule.")
    except ValidationError as e:
        messages.error(request, str(e.message if hasattr(e, 'message') else e))

    return redirect('timetable_detail', timetable_id=timetable_id)


# -----------------------------------------------------------------------------
# 6. TIMETABLE COPY / CLONE
# -----------------------------------------------------------------------------

@require_POST
@management_staff_required
def timetable_copy_view(request, timetable_id):
    """Copies an entire timetable structure to another class offering."""
    source_timetable = get_object_or_404(Timetable, pk=timetable_id)
    form = TimetableCopyForm(source_timetable=source_timetable, data=request.POST)

    if form.is_valid():
        target_offering = form.cleaned_data['target_class_offering']
        try:
            new_tt, copied, skipped = TimetableService.copy_timetable(
                source_timetable=source_timetable,
                target_class_offering=target_offering,
                user=request.user,
                request=request
            )
            skip_msg = f" ({skipped} slots skipped due to teacher/room conflicts)" if skipped > 0 else ""
            messages.success(request, f"Timetable successfully cloned to {target_offering.display_name}! Copied {copied} lessons{skip_msg}.")
            return redirect('timetable_detail', timetable_id=new_tt.id)
        except ValidationError as e:
            messages.error(request, str(e))
    else:
        messages.error(request, "Invalid class selected for cloning.")

    return redirect('timetable_detail', timetable_id=source_timetable.id)


# -----------------------------------------------------------------------------
# 7. TIMETABLE REVIEW & PUBLICATION WORKFLOW
# -----------------------------------------------------------------------------

@require_POST
@management_staff_required
def timetable_submit_view(request, timetable_id):
    """Submits draft timetable for review by Principal."""
    timetable = get_object_or_404(Timetable, pk=timetable_id)
    try:
        TimetablePublicationService.submit_for_review(timetable, user=request.user, request=request)
        messages.success(request, f"Timetable '{timetable.name}' submitted for administrative review.")
    except ValidationError as e:
        messages.error(request, str(e.message if hasattr(e, 'message') else e))

    return redirect('timetable_detail', timetable_id=timetable.id)


@principal_or_registrar_required
def timetable_approval_view(request, timetable_id):
    """Principal or Committee review form for authorization or returning timetable."""
    timetable = get_object_or_404(Timetable, pk=timetable_id)

    if request.method == 'POST':
        form = TimetableApprovalForm(request.POST)
        if form.is_valid():
            decision = form.cleaned_data['decision']
            comments = form.cleaned_data['comments']
            try:
                TimetablePublicationService.review_batch_decision = decision
                TimetablePublicationService.review_timetable(
                    timetable=timetable,
                    decision=decision,
                    reviewer_user=request.user,
                    comments=comments,
                    request=request
                )
                if decision == 'APPROVED':
                    messages.success(request, f"Timetable '{timetable.name}' approved successfully. Ready for publication.")
                else:
                    messages.warning(request, f"Timetable '{timetable.name}' returned to draft for corrections.")
                return redirect('timetable_detail', timetable_id=timetable.id)
            except ValidationError as e:
                form.add_error(None, str(e))
    else:
        form = TimetableApprovalForm(initial={'decision': 'APPROVED'})

    conflicts = ConflictDetectionService.validate_entire_timetable(timetable)

    context = {
        'active_menu': 'timetable',
        'page_title': f"Review Timetable: {timetable.name}",
        'timetable': timetable,
        'form': form,
        'conflicts': conflicts,
    }
    return render(request, 'timetable/timetable_approval.html', context)


@require_POST
@management_staff_required
def timetable_publish_view(request, timetable_id):
    """Publishes approved timetable, archives previous version, creates audit snapshot."""
    timetable = get_object_or_404(Timetable, pk=timetable_id)
    try:
        TimetablePublicationService.publish_timetable(timetable, user=request.user, request=request)
        messages.success(request, f"Timetable '{timetable.name}' is now PUBLISHED and live for teachers and students!")
    except ValidationError as e:
        messages.error(request, str(e.message if hasattr(e, 'message') else e))

    return redirect('timetable_detail', timetable_id=timetable.id)


@require_POST
@management_staff_required
def timetable_revise_view(request, timetable_id):
    """Clones a published timetable into a new revision version (vN+1)."""
    timetable = get_object_or_404(Timetable, pk=timetable_id)
    try:
        new_tt = TimetablePublicationService.create_revised_version(timetable, user=request.user, request=request)
        messages.success(request, f"New revision draft (v{new_tt.version}) initiated. Published schedule remains live until this is published.")
        return redirect('timetable_detail', timetable_id=new_tt.id)
    except ValidationError as e:
        messages.error(request, str(e.message if hasattr(e, 'message') else e))

    return redirect('timetable_detail', timetable_id=timetable.id)


# -----------------------------------------------------------------------------
# 8. TEACHER TIMETABLE VIEW
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def teacher_timetable_view(request, teacher_id=None):
    """
    Weekly timetable view for an individual teacher.
    Teachers can strictly only view their own schedule unless they hold management roles.
    """
    user_role = _get_user_role(request.user)

    if user_role == 'TEACHER':
        # Enforce that teachers can only view their own timetable
        teacher = Teacher.objects.filter(user=request.user).first()
        if not teacher:
            messages.error(request, "No teacher profile associated with your user account.")
            return redirect('dashboard')
    else:
        # Management staff can inspect any teacher's timetable
        if teacher_id:
            teacher = get_object_or_404(Teacher, pk=teacher_id)
        else:
            teacher = Teacher.objects.filter(is_active=True).first()

    current_year = AcademicYear.objects.filter(is_current=True).first()
    selected_year_id = request.GET.get('academic_year')
    year = AcademicYear.objects.filter(pk=selected_year_id).first() if selected_year_id else current_year

    matrix = TimetableMatrixService.get_teacher_matrix(teacher, academic_year=year) if teacher else None
    all_teachers = Teacher.objects.filter(is_active=True).order_by('first_name', 'father_name')
    all_years = AcademicYear.objects.all().order_by('-start_date')

    context = {
        'active_menu': 'timetable',
        'page_title': f"Teacher Timetable: {teacher.full_name if teacher else 'Select Teacher'}",
        'teacher': teacher,
        'matrix': matrix,
        'all_teachers': all_teachers,
        'all_years': all_years,
        'selected_year': year,
        'user_role': user_role,
        'is_management': user_role in ['ADMIN', 'REGISTRAR', 'PRINCIPAL'],
    }
    return render(request, 'timetable/teacher_timetable.html', context)


# -----------------------------------------------------------------------------
# 9. CLASS TIMETABLE VIEW
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def class_timetable_view(request, class_offering_id=None):
    """Public / staff weekly view of a published class offering schedule."""
    current_year = AcademicYear.objects.filter(is_current=True).first()
    selected_year_id = request.GET.get('academic_year')
    year = AcademicYear.objects.filter(pk=selected_year_id).first() if selected_year_id else current_year

    class_offerings = ClassOffering.objects.filter(
        academic_year=year
    ).select_related('grade', 'section', 'stream').order_by('grade__level', 'section__name')

    selected_offering = None
    if class_offering_id:
        selected_offering = get_object_or_404(ClassOffering, pk=class_offering_id)
    elif class_offerings.exists():
        selected_offering = class_offerings.first()

    timetable = None
    matrix = None
    if selected_offering:
        timetable = Timetable.objects.filter(
            class_offering=selected_offering,
            status='PUBLISHED'
        ).first()
        if not timetable:
            # Fall back to latest draft if management staff
            timetable = Timetable.objects.filter(
                class_offering=selected_offering
            ).order_by('-version').first()

        if timetable:
            matrix = TimetableMatrixService.get_class_matrix(timetable)

    all_years = AcademicYear.objects.all().order_by('-start_date')

    context = {
        'active_menu': 'timetable',
        'page_title': f"Class Timetable: {selected_offering.display_name if selected_offering else 'Select Class'}",
        'class_offering': selected_offering,
        'timetable': timetable,
        'matrix': matrix,
        'class_offerings': class_offerings,
        'all_years': all_years,
        'selected_year': year,
    }
    return render(request, 'timetable/class_timetable.html', context)


# -----------------------------------------------------------------------------
# 10. CLASSROOM MANAGEMENT
# -----------------------------------------------------------------------------

@management_staff_required
def classroom_list_view(request):
    """Lists all physical learning spaces and laboratories."""
    user_role = _get_user_role(request.user)
    rooms_qs = Classroom.objects.all().order_by('building', 'name')

    room_type_filter = request.GET.get('room_type')
    if room_type_filter:
        rooms_qs = rooms_qs.filter(room_type=room_type_filter)

    search_q = request.GET.get('q', '').strip()
    if search_q:
        rooms_qs = rooms_qs.filter(
            Q(name__icontains=search_q) |
            Q(code__icontains=search_q) |
            Q(building__icontains=search_q)
        )

    context = {
        'active_menu': 'timetable',
        'page_title': 'Classroom & Laboratory Directory',
        'classrooms': rooms_qs,
        'total_count': rooms_qs.count(),
        'room_types': Classroom.ROOM_TYPE_CHOICES,
        'room_type_filter': room_type_filter,
        'search_q': search_q,
        'user_role': user_role,
    }
    return render(request, 'timetable/classroom_list.html', context)


@management_staff_required
def classroom_create_view(request):
    """Adds a new physical classroom or laboratory."""
    if request.method == 'POST':
        form = ClassroomForm(request.POST)
        if form.is_valid():
            room = form.save()
            TimetableAuditHelper.log(request, 'CREATE', 'Classroom', room.id, {'name': room.name, 'code': room.code})
            messages.success(request, f"Classroom '{room.name}' added successfully.")
            return redirect('classroom_list')
    else:
        form = ClassroomForm()

    context = {
        'active_menu': 'timetable',
        'page_title': 'Add New Classroom / Laboratory',
        'form': form,
    }
    return render(request, 'timetable/classroom_form.html', context)


@management_staff_required
def classroom_edit_view(request, room_id):
    """Edits classroom details or capacity."""
    room = get_object_or_404(Classroom, pk=room_id)
    if request.method == 'POST':
        form = ClassroomForm(request.POST, instance=room)
        if form.is_valid():
            room = form.save()
            TimetableAuditHelper.log(request, 'UPDATE', 'Classroom', room.id, {'name': room.name, 'code': room.code})
            messages.success(request, f"Classroom '{room.name}' updated successfully.")
            return redirect('classroom_list')
    else:
        form = ClassroomForm(instance=room)

    context = {
        'active_menu': 'timetable',
        'page_title': f"Edit Classroom: {room.name}",
        'form': form,
        'room': room,
    }
    return render(request, 'timetable/classroom_form.html', context)


@require_POST
@management_staff_required
def classroom_toggle_view(request, room_id):
    """Toggles active/inactive status of a classroom."""
    room = get_object_or_404(Classroom, pk=room_id)
    room.is_active = not room.is_active
    room.save(update_fields=['is_active'])
    status_str = "activated" if room.is_active else "deactivated"
    TimetableAuditHelper.log(request, 'UPDATE', 'Classroom', room.id, {'is_active': room.is_active})
    messages.success(request, f"Classroom '{room.name}' {status_str}.")
    return redirect('classroom_list')


# -----------------------------------------------------------------------------
# 11. PERIOD & WORKING DAYS CONFIGURATION
# -----------------------------------------------------------------------------

@management_staff_required
def period_list_view(request):
    """Lists configured periods and break slots for daily schedule."""
    current_year = AcademicYear.objects.filter(is_current=True).first()
    selected_year_id = request.GET.get('academic_year')
    year = AcademicYear.objects.filter(pk=selected_year_id).first() if selected_year_id else current_year

    periods = TimetableConfigService.get_active_periods(academic_year=year)
    all_years = AcademicYear.objects.all().order_by('-start_date')

    context = {
        'active_menu': 'timetable',
        'page_title': 'Period Schedule Configuration',
        'periods': periods,
        'academic_year': year,
        'all_years': all_years,
    }
    return render(request, 'timetable/period_list.html', context)


@management_staff_required
def period_create_view(request):
    """Creates a new period or break slot."""
    if request.method == 'POST':
        form = PeriodForm(request.POST)
        if form.is_valid():
            period = form.save()
            TimetableAuditHelper.log(request, 'CREATE', 'Period', period.id, {'name': period.name, 'start': str(period.start_time)})
            messages.success(request, f"Period '{period.name}' created.")
            return redirect('period_list')
    else:
        current_year = AcademicYear.objects.filter(is_current=True).first()
        next_num = Period.objects.count() + 1
        form = PeriodForm(initial={'academic_year': current_year, 'period_number': next_num})

    context = {
        'active_menu': 'timetable',
        'page_title': 'Add Daily Schedule Period',
        'form': form,
    }
    return render(request, 'timetable/period_form.html', context)


@management_staff_required
def period_edit_view(request, period_id):
    """Edits period name, start/end time, or break status."""
    period = get_object_or_404(Period, pk=period_id)
    if request.method == 'POST':
        form = PeriodForm(request.POST, instance=period)
        if form.is_valid():
            period = form.save()
            TimetableAuditHelper.log(request, 'UPDATE', 'Period', period.id, {'name': period.name})
            messages.success(request, f"Period '{period.name}' updated.")
            return redirect('period_list')
    else:
        form = PeriodForm(instance=period)

    context = {
        'active_menu': 'timetable',
        'page_title': f"Edit Period: {period.name}",
        'form': form,
        'period': period,
    }
    return render(request, 'timetable/period_form.html', context)


@management_staff_required
def working_days_view(request):
    """Configures active days of the week for school operations."""
    current_year = AcademicYear.objects.filter(is_current=True).first()
    selected_year_id = request.GET.get('academic_year')
    year = AcademicYear.objects.filter(pk=selected_year_id).first() if selected_year_id else current_year

    if request.method == 'POST':
        # Batch update active days
        active_dow_ids = request.POST.getlist('active_days')
        active_dow_ints = [int(x) for x in active_dow_ids if x.isdigit()]

        days = TimetableConfigService.get_active_working_days(year)
        for day in days:
            day.is_active = (day.day_of_week in active_dow_ints)
            day.save(update_fields=['is_active'])

        messages.success(request, "School working days configuration updated.")
        return redirect('working_days')

    days = TimetableConfigService.get_active_working_days(year)
    all_years = AcademicYear.objects.all().order_by('-start_date')

    context = {
        'active_menu': 'timetable',
        'page_title': 'School Working Days Configuration',
        'days': days,
        'academic_year': year,
        'all_years': all_years,
    }
    return render(request, 'timetable/working_days.html', context)


# -----------------------------------------------------------------------------
# 12. CONFLICT DETECTION AUDIT REPORT
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def conflict_detection_view(request):
    """
    School-wide conflict audit dashboard. Scans all active and published
    timetables for teacher double-booking, class clashes, and room conflicts.
    """
    current_year = AcademicYear.objects.filter(is_current=True).first()
    selected_year_id = request.GET.get('academic_year')
    year = AcademicYear.objects.filter(pk=selected_year_id).first() if selected_year_id else current_year

    timetables = Timetable.objects.filter(
        academic_year=year,
        status__in=['PUBLISHED', 'APPROVED', 'SUBMITTED']
    ).select_related('class_offering__grade', 'class_offering__section')

    all_conflicts = []
    for tt in timetables:
        confs = ConflictDetectionService.validate_entire_timetable(tt)
        for c in confs:
            c['timetable_name'] = tt.name
            c['timetable_id'] = tt.id
            c['class_name'] = tt.class_offering.display_name
            all_conflicts.append(c)

    all_years = AcademicYear.objects.all().order_by('-start_date')

    context = {
        'active_menu': 'timetable',
        'page_title': 'Timetable Conflict Audit & Resolution',
        'conflicts': all_conflicts,
        'total_conflicts': len(all_conflicts),
        'error_conflicts': len([c for c in all_conflicts if c['severity'] == 'ERROR']),
        'warning_conflicts': len([c for c in all_conflicts if c['severity'] == 'WARNING']),
        'academic_year': year,
        'all_years': all_years,
    }
    return render(request, 'timetable/conflicts.html', context)


# -----------------------------------------------------------------------------
# 13. PDF & EXCEL EXPORTS
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def export_class_timetable_pdf_view(request, timetable_id):
    """Exports official printable class timetable as ReportLab PDF."""
    timetable = get_object_or_404(Timetable, pk=timetable_id)
    filename = f"Timetable_{timetable.class_offering.grade.name}_{timetable.class_offering.section.name}_{timetable.academic_year.code}.pdf".replace(" ", "_")
    return TimetableReportService.export_class_timetable_pdf(timetable, filename=filename)


@any_authenticated_role_required
def export_class_timetable_excel_view(request, timetable_id):
    """Exports class timetable as Microsoft Excel spreadsheet."""
    timetable = get_object_or_404(Timetable, pk=timetable_id)
    filename = f"Timetable_{timetable.class_offering.grade.name}_{timetable.class_offering.section.name}_{timetable.academic_year.code}.xlsx".replace(" ", "_")
    return TimetableReportService.export_class_timetable_excel(timetable, filename=filename)


@any_authenticated_role_required
def export_teacher_timetable_pdf_view(request, teacher_id):
    """Exports official printable teacher timetable as ReportLab PDF."""
    user_role = _get_user_role(request.user)
    if user_role == 'TEACHER':
        teacher = get_object_or_404(Teacher, user=request.user)
    else:
        teacher = get_object_or_404(Teacher, pk=teacher_id)

    current_year = AcademicYear.objects.filter(is_current=True).first()
    filename = f"Teacher_Timetable_{teacher.first_name}_{teacher.father_name}_{teacher.employee_id}.pdf".replace(" ", "_")
    return TimetableReportService.export_teacher_timetable_pdf(teacher, academic_year=current_year, filename=filename)


@any_authenticated_role_required
def export_teacher_timetable_excel_view(request, teacher_id):
    """Exports teacher timetable as Microsoft Excel spreadsheet."""
    user_role = _get_user_role(request.user)
    if user_role == 'TEACHER':
        teacher = get_object_or_404(Teacher, user=request.user)
    else:
        teacher = get_object_or_404(Teacher, pk=teacher_id)

    current_year = AcademicYear.objects.filter(is_current=True).first()
    filename = f"Teacher_Timetable_{teacher.first_name}_{teacher.father_name}_{teacher.employee_id}.xlsx".replace(" ", "_")
    return TimetableReportService.export_teacher_timetable_excel(teacher, academic_year=current_year, filename=filename)
