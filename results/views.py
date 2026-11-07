"""
Results Management Views for SSMS.

Implements role-gated interfaces for:
  - Results Hub & Marks Entry Dashboard
  - High-Speed Student Marks Recording (Bulk & Single)
  - Teacher Marks Submission for Verification
  - Verification & Approval Workflow (Registrar / Principal)
  - Result Calculation (Totals, Percentages, Averages, Grades, Ranks)
  - Official Student Report Cards (Web & ReportLab PDF)
  - Master Gradebook Export (OpenPyXL Excel)
  - Academic Performance Analytics & Configurable Grading Scales
"""

from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied, ValidationError
from django.views.decorators.http import require_POST
from django.db.models import Count, Avg, Max, Min, Sum, Q
from django.utils import timezone

from accounts.decorators import (
    any_authenticated_role_required,
    management_staff_required,
    principal_or_registrar_required,
)
from academics.models import AcademicYear, Grade, Stream, Subject, ClassOffering
from students.models import Student, StudentEnrollment
from teachers.models import Teacher, TeacherAssignment
from examinations.models import Examination, ExamSubject
from results.models import GradingScale, GradingRange, Mark, ResultApproval, StudentResultSummary
from results.forms import GradingScaleForm, GradingRangeForm, MarksReviewForm
from results.services import MarksService, ResultCalculationService, ReportCardService


def _get_user_role(user):
    if user.is_superuser:
        return 'ADMIN'
    if user.role:
        return user.role.code
    return None


def _is_teacher_assigned_to_exam_subject(teacher, exam_subject):
    """Checks if a teacher is assigned to teach this subject in this grade."""
    if not teacher or not exam_subject:
        return False
    return TeacherAssignment.objects.filter(
        teacher=teacher,
        subject=exam_subject.subject,
        class_offering__grade=exam_subject.grade
    ).exists()


# -----------------------------------------------------------------------------
# 1. RESULTS HUB / DASHBOARD
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def results_index_view(request):
    """
    Central results overview showing ongoing marks entry, verification queue,
    and published examination cycles.
    """
    user_role = _get_user_role(request.user)
    current_year = AcademicYear.objects.filter(is_current=True).first()

    # Active examinations
    active_exams = Examination.objects.filter(
        academic_year=current_year
    ).select_related('academic_year', 'exam_type', 'grade').order_by('-start_date')

    # Teacher specific subjects
    teacher_subjects = []
    teacher_profile = getattr(request.user, 'teacher_profile', None) if user_role == 'TEACHER' else None

    if user_role == 'TEACHER' and teacher_profile:
        assigned_subject_ids = TeacherAssignment.objects.filter(
            teacher=teacher_profile
        ).values_list('subject_id', flat=True)

        teacher_subjects = ExamSubject.objects.filter(
            examination__academic_year=current_year,
            subject_id__in=assigned_subject_ids
        ).select_related('examination', 'subject', 'grade').order_by('-examination__start_date')

    # Verification Queue for Registrars & Principals
    pending_verification_qs = ExamSubject.objects.filter(
        status='SUBMITTED'
    ).select_related('examination', 'subject', 'grade', 'submitted_by')

    recent_published = Examination.objects.filter(
        status='PUBLISHED'
    ).select_related('academic_year', 'exam_type').order_by('-start_date')[:5]

    context = {
        'active_menu': 'results',
        'page_title': 'Examination Results & Marks Processing',
        'current_year': current_year,
        'user_role': user_role,
        'active_exams': active_exams,
        'teacher_subjects': teacher_subjects,
        'pending_verification': pending_verification_qs,
        'recent_published': recent_published,
        'is_teacher': user_role == 'TEACHER',
        'is_management': user_role in ('ADMIN', 'REGISTRAR', 'PRINCIPAL'),
    }
    return render(request, 'results/dashboard.html', context)


# -----------------------------------------------------------------------------
# 2. MARKS ENTRY SHEET
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def marks_entry_view(request, exam_subject_id):
    """
    Spreadsheet-like score recording interface for a specific examination subject.
    Validates boundary conditions: 0 <= score <= max_marks.
    Missing marks remain empty without automatically becoming zero.
    """
    exam_subject = get_object_or_404(
        ExamSubject.objects.select_related('examination__academic_year', 'subject', 'grade', 'stream'),
        pk=exam_subject_id
    )

    user_role = _get_user_role(request.user)
    teacher_profile = getattr(request.user, 'teacher_profile', None) if user_role == 'TEACHER' else None

    # Permission check: Teacher must be assigned to this subject/grade (or be management)
    if user_role == 'TEACHER':
        if not _is_teacher_assigned_to_exam_subject(teacher_profile, exam_subject):
            raise PermissionDenied("You can only enter marks for subjects and classes assigned to you.")

    # Locked verification check
    if exam_subject.is_locked:
        messages.warning(
            request,
            f"Marks entry for {exam_subject.subject.name} is locked because the examination is closed or marks are approved."
        )
        return redirect('marks_verify', exam_subject_id=exam_subject.id)

    # Fetch enrolled students in this grade
    enrollments_qs = StudentEnrollment.objects.filter(
        class_offering__grade=exam_subject.grade,
        academic_year=exam_subject.examination.academic_year,
        status='ACTIVE'
    ).select_related('student', 'class_offering__section').order_by(
        'class_offering__section__name',
        'student__first_name',
        'student__father_name'
    )

    if exam_subject.stream:
        enrollments_qs = enrollments_qs.filter(class_offering__stream=exam_subject.stream)

    # Pre-load existing marks
    existing_marks = {
        m.student_enrollment_id: m
        for m in Mark.objects.filter(exam_subject=exam_subject)
    }

    if request.method == 'POST':
        marks_data = []
        for enr in enrollments_qs:
            raw_score = (request.POST.get(f"marks_{enr.id}") or request.POST.get(f"score_{enr.id}") or '').strip()
            absent_key = f"absent_{enr.id}"
            remarks = (request.POST.get(f"remarks_{enr.id}") or '').strip()
            is_absent = (absent_key in request.POST)

            marks_data.append({
                'enrollment_id': enr.id,
                'marks_obtained': raw_score if (raw_score != '' and not is_absent) else None,
                'is_absent': is_absent,
                'remarks': remarks,
            })

        try:
            result = MarksService.record_bulk_marks(
                exam_subject=exam_subject,
                marks_data=marks_data,
                entered_by_user=request.user,
                request=request
            )
            messages.success(
                request,
                f"Marks saved successfully for {exam_subject.subject.name} ({result['updated'] + result['created']} students recorded)."
            )

            # If user clicked 'Save & Submit for Review'
            if 'submit_for_review' in request.POST:
                return redirect('marks_submit', exam_subject_id=exam_subject.id)

            return redirect('marks_entry', exam_subject_id=exam_subject.id)
        except ValidationError as e:
            messages.error(request, str(e.message if hasattr(e, 'message') else e))

    student_rows = []
    for enr in enrollments_qs:
        mk = existing_marks.get(enr.id)
        student_rows.append({
            'enrollment': enr,
            'student': enr.student,
            'class_section': enr.class_offering.section.name,
            'marks_obtained': mk.marks_obtained if (mk and mk.marks_obtained is not None) else '',
            'is_absent': mk.is_absent if mk else False,
            'remarks': mk.remarks if mk else '',
            'has_mark': mk is not None and (mk.marks_obtained is not None or mk.is_absent),
        })

    context = {
        'active_menu': 'results',
        'page_title': f"Marks Entry: {exam_subject.subject.name} ({exam_subject.grade.name})",
        'exam_subject': exam_subject,
        'student_rows': student_rows,
        'total_students': len(student_rows),
        'user_role': user_role,
        'can_submit': exam_subject.status in ('PENDING', 'RETURNED') and len(student_rows) > 0,
    }
    return render(request, 'results/marks_entry.html', context)


# -----------------------------------------------------------------------------
# 3. MARKS SUBMISSION FOR VERIFICATION
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def marks_submit_view(request, exam_subject_id):
    """
    Teacher confirms marks completeness and submits to the examination office.
    """
    exam_subject = get_object_or_404(ExamSubject, pk=exam_subject_id)
    user_role = _get_user_role(request.user)

    if request.method == 'POST':
        try:
            MarksService.submit_marks_for_verification(
                exam_subject=exam_subject,
                teacher_user=request.user,
                request=request
            )
            messages.success(
                request,
                f"Marks for '{exam_subject.subject.name}' submitted to the Examination Office for verification."
            )
            return redirect('examination_detail', exam_id=exam_subject.examination.id)
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('marks_entry', exam_subject_id=exam_subject.id)

    # Summary of marks for confirmation dialog
    marks_qs = Mark.objects.filter(exam_subject=exam_subject)
    total_entered = marks_qs.filter(Q(marks_obtained__isnull=False) | Q(is_absent=True)).count()
    total_students = StudentEnrollment.objects.filter(
        class_offering__grade=exam_subject.grade,
        academic_year=exam_subject.examination.academic_year,
        status='ACTIVE'
    ).count()

    context = {
        'active_menu': 'results',
        'page_title': f"Submit Marks: {exam_subject.subject.name}",
        'exam_subject': exam_subject,
        'total_entered': total_entered,
        'total_students': total_students,
    }
    return render(request, 'results/marks_submit_confirm.html', context)


# -----------------------------------------------------------------------------
# 4. MARKS VERIFICATION & APPROVAL WORKFLOW
# -----------------------------------------------------------------------------

@principal_or_registrar_required
def marks_verify_view(request, exam_subject_id):
    """
    Administrative review hub where Examination Officers / Registrars
    inspect scores, approve marks, or return them with specific correction comments.
    """
    exam_subject = get_object_or_404(
        ExamSubject.objects.select_related('examination__academic_year', 'subject', 'grade', 'submitted_by'),
        pk=exam_subject_id
    )

    marks = Mark.objects.filter(
        exam_subject=exam_subject
    ).select_related('student_enrollment__student', 'student_enrollment__class_offering__section').order_by(
        'student_enrollment__class_offering__section__name',
        'student_enrollment__student__first_name'
    )

    # Statistical summary of entered scores
    valid_scores = [m.marks_obtained for m in marks if m.marks_obtained is not None and not m.is_absent]
    avg_score = round(sum(valid_scores) / len(valid_scores), 2) if valid_scores else 0.0
    highest_score = max(valid_scores) if valid_scores else 0.0
    lowest_score = min(valid_scores) if valid_scores else 0.0
    absent_count = marks.filter(is_absent=True).count()
    pass_count = sum(1 for m in marks if m.is_passing)

    # Verification form
    if request.method == 'POST':
        form = MarksReviewForm(request.POST)
        if form.is_valid():
            decision = form.cleaned_data['decision']
            comments = form.cleaned_data['comments']
            try:
                MarksService.review_and_verify_marks(
                    exam_subject=exam_subject,
                    reviewer_user=request.user,
                    decision=decision,
                    comments=comments,
                    request=request
                )
                if decision == 'APPROVED':
                    messages.success(request, f"Marks for '{exam_subject.subject.name}' have been approved and verified.")
                else:
                    messages.warning(request, f"Marks for '{exam_subject.subject.name}' returned to teacher for correction.")
                return redirect('examination_detail', exam_id=exam_subject.examination.id)
            except ValidationError as e:
                messages.error(request, str(e))
    else:
        form = MarksReviewForm(initial={'decision': 'APPROVED'})

    approvals = exam_subject.approvals.select_related('reviewed_by').order_by('-reviewed_at')

    context = {
        'active_menu': 'results',
        'page_title': f"Verify Marks: {exam_subject.subject.name} ({exam_subject.grade.name})",
        'exam_subject': exam_subject,
        'marks': marks,
        'total_students': marks.count(),
        'avg_score': avg_score,
        'highest_score': highest_score,
        'lowest_score': lowest_score,
        'absent_count': absent_count,
        'pass_count': pass_count,
        'form': form,
        'approvals': approvals,
    }
    return render(request, 'results/marks_verify.html', context)


# -----------------------------------------------------------------------------
# 5. RESULT CALCULATION & PUBLICATION
# -----------------------------------------------------------------------------

@management_staff_required
def calculate_results_view(request, exam_id):
    """
    Triggers decimal-safe mathematical aggregation of examination totals,
    percentages, grade brackets, and class rankings.
    """
    exam = get_object_or_404(Examination, pk=exam_id)

    if request.method == 'POST':
        scale_id = request.POST.get('grading_scale')
        scale = GradingScale.objects.filter(pk=scale_id).first() if scale_id else None

        summaries = ResultCalculationService.calculate_examination_results(
            examination=exam,
            grading_scale=scale,
            request=request
        )
        messages.success(request, f"Result calculations completed for {len(summaries)} students in '{exam.name}'.")
        return redirect('published_results', exam_id=exam.id)

    grading_scales = GradingScale.objects.all().order_by('-is_default')

    context = {
        'active_menu': 'results',
        'page_title': f"Calculate Results - {exam.name}",
        'exam': exam,
        'grading_scales': grading_scales,
    }
    return render(request, 'results/calculate_confirm.html', context)


@require_POST
@management_staff_required
def publish_results_view(request, exam_id):
    """Officially publishes calculated results for public/student view."""
    exam = get_object_or_404(Examination, pk=exam_id)
    exam.status = 'PUBLISHED'
    exam.save(update_fields=['status', 'updated_at'])

    # Update summaries
    StudentResultSummary.objects.filter(examination=exam).update(status='PUBLISHED')

    messages.success(request, f"Results for '{exam.name}' have been officially published.")
    return redirect('published_results', exam_id=exam.id)


@any_authenticated_role_required
def published_results_view(request, exam_id=None):
    """
    Master roster of computed examination results with class filtering,
    averages, grades, ranks, and report-card shortcuts.
    """
    user_role = _get_user_role(request.user)
    current_year = AcademicYear.objects.filter(is_current=True).first()

    if exam_id:
        exam = get_object_or_404(Examination, pk=exam_id)
    else:
        exam = Examination.objects.filter(academic_year=current_year).order_by('-start_date').first()

    selected_class_id = request.GET.get('class_offering')

    summaries = []
    classes = []
    if exam:
        classes = ClassOffering.objects.filter(academic_year=exam.academic_year).select_related('grade', 'section')
        if exam.grade:
            classes = classes.filter(grade=exam.grade)

        summaries_qs = StudentResultSummary.objects.filter(
            examination=exam
        ).select_related('student_enrollment__student', 'student_enrollment__class_offering').order_by('rank', '-average_mark')

        if selected_class_id:
            summaries_qs = summaries_qs.filter(student_enrollment__class_offering_id=selected_class_id)

        summaries = summaries_qs

    all_exams = Examination.objects.all().order_by('-start_date')

    context = {
        'active_menu': 'results',
        'page_title': 'Examination Results & Rankings',
        'exam': exam,
        'all_exams': all_exams,
        'classes': classes,
        'selected_class_id': selected_class_id,
        'summaries': summaries,
        'total_evaluated': summaries.count() if hasattr(summaries, 'count') else len(summaries),
        'user_role': user_role,
        'can_publish': user_role in ('ADMIN', 'PRINCIPAL') and exam and not exam.is_published,
    }
    return render(request, 'results/published_results.html', context)


# -----------------------------------------------------------------------------
# 6. STUDENT REPORT CARDS (WEB & PDF)
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def student_report_card_view(request, exam_id, student_id):
    """
    Displays an individual student report card, with 1-click PDF download.
    """
    exam = get_object_or_404(Examination, pk=exam_id)
    student = get_object_or_404(Student, pk=student_id)

    enrollment = StudentEnrollment.objects.filter(
        student=student,
        academic_year=exam.academic_year
    ).first()

    if not enrollment:
        messages.error(request, "Student has no active enrollment record for this examination's academic year.")
        return redirect('results_index')

    report_data = ReportCardService.get_report_card_data(enrollment, exam)

    # Check for PDF export request
    if request.GET.get('format') == 'pdf':
        filename = f"ReportCard_{student.admission_number}_{exam.academic_year.code}_{exam.semester}.pdf"
        return ReportCardService.export_report_card_pdf(report_data, filename=filename)

    context = {
        'active_menu': 'results',
        'page_title': f"Report Card: {student.full_name}",
        'data': report_data,
        'exam': exam,
        'student': student,
    }
    return render(request, 'results/report_card.html', context)


# -----------------------------------------------------------------------------
# 7. EXCEL GRADEBOOK EXPORT
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def export_class_results_excel_view(request, exam_id):
    """Exports full classroom gradebook spreadsheet via openpyxl."""
    exam = get_object_or_404(Examination, pk=exam_id)
    class_id = request.GET.get('class_offering')
    class_offering = get_object_or_404(ClassOffering, pk=class_id) if class_id else None

    filename = f"Gradebook_{exam.name.replace(' ', '_')}_{timezone.now():%Y%m%d}.xlsx"
    return ReportCardService.export_class_results_excel(exam, class_offering=class_offering, filename=filename)


# -----------------------------------------------------------------------------
# 8. STUDENT LONGITUDINAL RESULT HISTORY
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def student_result_history_view(request, student_id):
    """
    Longitudinal academic transcript showing marks and report cards across all academic years.
    """
    student = get_object_or_404(Student, pk=student_id)
    enrollments = student.enrollments.select_related('academic_year', 'class_offering__grade', 'class_offering__section').order_by('-academic_year__start_date')

    # Gather all marks and summaries
    summaries = StudentResultSummary.objects.filter(
        student_enrollment__student=student
    ).select_related('examination__academic_year', 'examination__exam_type').order_by('-examination__start_date')

    all_marks = Mark.objects.filter(
        student_enrollment__student=student
    ).select_related(
        'exam_subject__examination',
        'exam_subject__subject'
    ).order_by('-exam_subject__examination__start_date')

    context = {
        'active_menu': 'results',
        'page_title': f"Academic Transcript: {student.full_name}",
        'student': student,
        'enrollments': enrollments,
        'summaries': summaries,
        'all_marks': all_marks,
    }
    return render(request, 'results/student_result_history.html', context)


# -----------------------------------------------------------------------------
# 9. ACADEMIC PERFORMANCE REPORTS
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def performance_reports_view(request):
    """
    School-wide examination performance reports with subject-level averages,
    highest/lowest marks, pass/fail ratios, and grade comparisons.
    """
    current_year = AcademicYear.objects.filter(is_current=True).first()
    exams = Examination.objects.filter(academic_year=current_year).order_by('-start_date')

    selected_exam_id = request.GET.get('exam')
    selected_exam = Examination.objects.filter(pk=selected_exam_id).first() if selected_exam_id else exams.first()

    subject_stats = []
    if selected_exam:
        for es in selected_exam.exam_subjects.select_related('subject', 'grade', 'stream'):
            marks = Mark.objects.filter(exam_subject=es, is_absent=False, marks_obtained__isnull=False)
            scores = [m.marks_obtained for m in marks]
            if scores:
                avg_m = round(sum(scores) / len(scores), 2)
                hi_m = max(scores)
                lo_m = min(scores)
                passed = sum(1 for s in scores if s >= es.pass_marks)
                failed = len(scores) - passed
                pass_rate = round((passed / len(scores)) * 100, 1)
            else:
                avg_m = hi_m = lo_m = passed = failed = pass_rate = 0.0

            subject_stats.append({
                'exam_subject': es,
                'total_students': len(scores),
                'average': avg_m,
                'highest': hi_m,
                'lowest': lo_m,
                'passed': passed,
                'failed': failed,
                'pass_rate': pass_rate,
            })

    context = {
        'active_menu': 'reports_academic',
        'page_title': 'Academic Performance & Subject Reports',
        'exams': exams,
        'selected_exam': selected_exam,
        'subject_stats': subject_stats,
    }
    return render(request, 'results/performance_reports.html', context)


# -----------------------------------------------------------------------------
# 10. CONFIGURABLE GRADING SCALE MANAGEMENT
# -----------------------------------------------------------------------------

@management_staff_required
def grading_configuration_view(request):
    """
    Manages configurable grading policies (e.g. Ethiopian Secondary A-F, GPA values).
    """
    scales = GradingScale.objects.prefetch_related('ranges').order_by('-is_default', 'name')
    default_scale = GradingScale.objects.filter(is_default=True).first()

    range_form = GradingRangeForm()
    scale_form = GradingScaleForm()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_range':
            target_scale_id = request.POST.get('scale_id')
            target_scale = get_object_or_404(GradingScale, pk=target_scale_id)
            range_form = GradingRangeForm(request.POST)
            if range_form.is_valid():
                r = range_form.save(commit=False)
                r.grading_scale = target_scale
                r.save()
                messages.success(request, f"Grade bracket '{r.grade_label}' added to {target_scale.name}.")
                return redirect('grading_config')

    context = {
        'active_menu': 'results',
        'page_title': 'Grading Policy Configuration',
        'scales': scales,
        'default_scale': default_scale,
        'range_form': range_form,
        'scale_form': scale_form,
    }
    return render(request, 'results/grading_config.html', context)
