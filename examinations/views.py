"""
Examinations Management Views for SSMS.
"""

from datetime import date
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied, ValidationError
from django.views.decorators.http import require_POST
from django.db.models import Count, Q
from django.utils import timezone

from accounts.decorators import (
    any_authenticated_role_required,
    management_staff_required,
    principal_or_registrar_required,
)
from academics.models import AcademicYear, Grade, Stream, Subject, ClassOffering
from teachers.models import Teacher, TeacherAssignment
from examinations.models import ExamType, Examination, ExamSubject
from examinations.forms import (
    ExaminationCreateForm,
    ExamSubjectConfigForm,
    ExaminationFilterForm,
)
from examinations.services import ExaminationService, ExamSubjectService


def _get_user_role(user):
    if user.is_superuser:
        return 'ADMIN'
    if user.role:
        return user.role.code
    return None


@any_authenticated_role_required
def examination_dashboard_view(request):
    """
    Main examination management dashboard.
    Displays exam cycles, KPIs, pending marks submissions, and Chart.js analytics.
    """
    user_role = _get_user_role(request.user)
    current_year = AcademicYear.objects.filter(is_current=True).first()

    total_exams = Examination.objects.count()
    active_exams = Examination.objects.filter(status='ACTIVE').count()
    completed_exams = Examination.objects.filter(status__in=['PUBLISHED', 'CLOSED']).count()

    # Pending marks entries (ExamSubjects pending submission)
    pending_submissions = ExamSubject.objects.filter(status='PENDING').count()
    pending_approvals = ExamSubject.objects.filter(status='SUBMITTED').count()
    published_results = ExamSubject.objects.filter(status='PUBLISHED').count()

    recent_exams = Examination.objects.select_related(
        'academic_year', 'exam_type', 'grade'
    ).order_by('-start_date')[:6]

    # Teacher assigned subjects shortcut
    teacher_assignments = []
    if user_role == 'TEACHER':
        teacher_profile = getattr(request.user, 'teacher_profile', None)
        if teacher_profile:
            teacher_assignments = TeacherAssignment.objects.filter(
                teacher=teacher_profile,
                class_offering__academic_year=current_year
            ).select_related('class_offering__grade', 'class_offering__section', 'subject')

    context = {
        'active_menu': 'examinations',
        'page_title': 'Examination Management Dashboard',
        'current_year': current_year,
        'user_role': user_role,
        'total_exams': total_exams,
        'active_exams': active_exams,
        'completed_exams': completed_exams,
        'pending_submissions': pending_submissions,
        'pending_approvals': pending_approvals,
        'published_results': published_results,
        'recent_exams': recent_exams,
        'teacher_assignments': teacher_assignments,
        'is_teacher': user_role == 'TEACHER',
        'is_management': user_role in ('ADMIN', 'REGISTRAR', 'PRINCIPAL'),
    }
    return render(request, 'examinations/dashboard.html', context)


@any_authenticated_role_required
def examination_list_view(request):
    """Directory of all examination cycles with multi-criteria filtering and pagination."""
    user_role = _get_user_role(request.user)
    exams_qs = Examination.objects.select_related('academic_year', 'exam_type', 'grade').order_by('-start_date')

    form = ExaminationFilterForm(request.GET)
    if form.is_valid():
        ay = form.cleaned_data.get('academic_year')
        sem = form.cleaned_data.get('semester')
        exam_type = form.cleaned_data.get('exam_type')
        grade = form.cleaned_data.get('grade')
        status = form.cleaned_data.get('status')

        if ay:
            exams_qs = exams_qs.filter(academic_year=ay)
        if sem:
            exams_qs = exams_qs.filter(semester=sem)
        if exam_type:
            exams_qs = exams_qs.filter(exam_type=exam_type)
        if grade:
            exams_qs = exams_qs.filter(grade=grade)
        if status:
            exams_qs = exams_qs.filter(status=status)

    paginator = Paginator(exams_qs, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'active_menu': 'examinations',
        'page_title': 'Examinations Directory',
        'filter_form': form,
        'page_obj': page_obj,
        'exams': page_obj,
        'user_role': user_role,
        'can_manage': user_role in ('ADMIN', 'REGISTRAR'),
    }
    return render(request, 'examinations/examination_list.html', context)


@management_staff_required
def examination_create_view(request):
    """Initiates and creates a new examination cycle."""
    user_role = _get_user_role(request.user)
    if request.method == 'POST':
        form = ExaminationCreateForm(request.POST)
        if form.is_valid():
            try:
                exam = ExaminationService.create_examination(
                    name=form.cleaned_data['name'],
                    exam_type=form.cleaned_data['exam_type'],
                    academic_year=form.cleaned_data['academic_year'],
                    semester=form.cleaned_data['semester'],
                    start_date=form.cleaned_data['start_date'],
                    end_date=form.cleaned_data['end_date'],
                    grade=form.cleaned_data.get('grade'),
                    class_offering=form.cleaned_data.get('class_offering'),
                    created_by=request.user,
                    request=request
                )
                messages.success(request, f"Examination cycle '{exam.name}' created successfully. Now configure the examination subjects.")
                return redirect('examination_detail', exam_id=exam.id)
            except ValidationError as e:
                form.add_error(None, e.message if hasattr(e, 'message') else str(e))
    else:
        form = ExaminationCreateForm()

    context = {
        'active_menu': 'examinations',
        'page_title': 'Schedule New Examination Cycle',
        'form': form,
        'user_role': user_role,
    }
    return render(request, 'examinations/examination_form.html', context)


@any_authenticated_role_required
def examination_detail_view(request, exam_id):
    """
    Detailed examination hub showing configured subjects, score thresholds,
    teacher mark submissions, and approval status.
    """
    exam = get_object_or_404(
        Examination.objects.select_related('academic_year', 'exam_type', 'grade', 'class_offering'),
        pk=exam_id
    )
    user_role = _get_user_role(request.user)

    exam_subjects = exam.exam_subjects.select_related(
        'subject', 'grade', 'stream', 'submitted_by', 'verified_by'
    ).order_by('grade__level', 'subject__name')

    # Teacher visibility constraint
    teacher_profile = getattr(request.user, 'teacher_profile', None) if user_role == 'TEACHER' else None
    if user_role == 'TEACHER' and teacher_profile:
        # Identify subjects taught by this teacher
        assigned_subject_ids = TeacherAssignment.objects.filter(
            teacher=teacher_profile
        ).values_list('subject_id', flat=True)
        # We don't hide the overall structure from teachers, but highlight their subjects

    context = {
        'active_menu': 'examinations',
        'page_title': f"Examination: {exam.name}",
        'exam': exam,
        'exam_subjects': exam_subjects,
        'total_subjects': exam_subjects.count(),
        'user_role': user_role,
        'can_manage': user_role in ('ADMIN', 'REGISTRAR') and not exam.is_closed,
        'can_publish': user_role in ('ADMIN', 'PRINCIPAL', 'REGISTRAR'),
        'teacher_profile': teacher_profile,
    }
    return render(request, 'examinations/examination_detail.html', context)


@management_staff_required
def examination_subject_config_view(request, exam_id):
    """Adds a single subject to an examination with marks thresholds."""
    exam = get_object_or_404(Examination, pk=exam_id)
    if exam.is_closed:
        messages.error(request, "Cannot modify subjects in a closed examination.")
        return redirect('examination_detail', exam_id=exam.id)

    grades = Grade.objects.filter(is_active=True).order_by('level')

    if request.method == 'POST':
        form = ExamSubjectConfigForm(request.POST, examination=exam)
        grade_id = request.POST.get('grade')
        grade = get_object_or_404(Grade, pk=grade_id) if grade_id else exam.grade

        if not grade:
            messages.error(request, "Please specify a target grade for this examination subject.")
        elif form.is_valid():
            try:
                ExamSubjectService.configure_subject(
                    examination=exam,
                    grade=grade,
                    subject=form.cleaned_data['subject'],
                    max_marks=form.cleaned_data['max_marks'],
                    pass_marks=form.cleaned_data['pass_marks'],
                    weight_percentage=form.cleaned_data['weight_percentage'],
                    exam_date=form.cleaned_data.get('exam_date'),
                    start_time=form.cleaned_data.get('start_time'),
                    end_time=form.cleaned_data.get('end_time'),
                    request=request
                )
                messages.success(request, f"Subject '{form.cleaned_data['subject'].name}' added to {exam.name}.")
                return redirect('examination_detail', exam_id=exam.id)
            except ValidationError as e:
                form.add_error(None, e.message if hasattr(e, 'message') else str(e))
    else:
        form = ExamSubjectConfigForm(examination=exam, grade=exam.grade)

    context = {
        'active_menu': 'examinations',
        'page_title': f"Configure Subject - {exam.name}",
        'exam': exam,
        'form': form,
        'grades': grades,
    }
    return render(request, 'examinations/subject_config_form.html', context)


@require_POST
@management_staff_required
def examination_auto_configure_view(request, exam_id):
    """Bulk populates examination subjects from the approved secondary curriculum."""
    exam = get_object_or_404(Examination, pk=exam_id)
    if exam.is_closed:
        messages.error(request, "Cannot modify a closed examination.")
        return redirect('examination_detail', exam_id=exam.id)

    grade_id = request.POST.get('grade_id')
    target_grades = Grade.objects.filter(pk=grade_id) if grade_id else (
        Grade.objects.filter(pk=exam.grade_id) if exam.grade else Grade.objects.filter(is_active=True)
    )

    total_added = 0
    for g in target_grades:
        added = ExamSubjectService.auto_configure_from_curriculum(
            examination=exam,
            grade=g,
            default_max=100.00,
            default_pass=50.00,
            request=request
        )
        total_added += added

    messages.success(request, f"Successfully populated {total_added} subject(s) from curriculum into '{exam.name}'.")
    return redirect('examination_detail', exam_id=exam.id)


@require_POST
@management_staff_required
def examination_close_view(request, exam_id):
    """Locks an examination to prevent further modifications."""
    exam = get_object_or_404(Examination, pk=exam_id)
    ExaminationService.close_examination(exam, user=request.user, request=request)
    messages.success(request, f"Examination '{exam.name}' has been closed and locked.")
    return redirect('examination_detail', exam_id=exam.id)


@require_POST
@management_staff_required
def examination_reopen_view(request, exam_id):
    """Reopens a locked examination for administrative updates."""
    exam = get_object_or_404(Examination, pk=exam_id)
    try:
        ExaminationService.reopen_examination(exam, user=request.user, request=request)
        messages.success(request, f"Examination '{exam.name}' reopened.")
    except ValidationError as e:
        messages.error(request, str(e))
    return redirect('examination_detail', exam_id=exam.id)
