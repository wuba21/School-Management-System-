"""
Views for Student Promotion, Batch Workflows, Academic History, Graduation, and Status Tracking.
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
    registrar_required
)
from academics.models import AcademicYear, Grade, Section, Stream, ClassOffering
from students.models import Student, StudentEnrollment
from promotion.models import (
    PromotionCriteria,
    PromotionBatch,
    PromotionRecord,
    GraduationRecord,
    StudentStatusHistory
)
from promotion.forms import (
    PromotionCriteriaForm,
    PromotionBatchCreateForm,
    PromotionRecordEditForm,
    PromotionApprovalForm,
    StudentStatusChangeForm,
    GraduationActionForm,
    PromotionFilterForm
)
from promotion.services import (
    PromotionAssessmentService,
    PromotionBatchService,
    PromotionApprovalService,
    StudentAcademicHistoryService,
    GraduationService,
    PromotionReportService
)


def _get_user_role(user):
    if user.is_superuser:
        return 'ADMIN'
    if hasattr(user, 'role') and user.role:
        return user.role.code
    return 'USER'


# -----------------------------------------------------------------------------
# 1. PROMOTION DASHBOARD
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def promotion_dashboard_view(request):
    """
    Main promotion analytics dashboard displaying active cohorts,
    breakdown of proposed outcomes, pending reviews, and recent batches.
    """
    user_role = _get_user_role(request.user)
    current_year = AcademicYear.objects.filter(is_current=True).first()

    batches_qs = PromotionBatch.objects.select_related(
        'academic_year', 'target_academic_year', 'grade', 'created_by'
    ).order_by('-created_at')

    # Counts and KPIs
    total_candidates = PromotionRecord.objects.count()
    promoted_count = PromotionRecord.objects.filter(final_outcome='PROMOTED').count()
    repeated_count = PromotionRecord.objects.filter(final_outcome='REPEATED').count()
    graduated_count = PromotionRecord.objects.filter(final_outcome='GRADUATED').count()
    pending_count = PromotionRecord.objects.filter(final_outcome='PENDING').count()
    transferred_count = StudentStatusHistory.objects.filter(status_type='TRANSFER_OUT').count()

    active_batches = batches_qs.filter(status__in=['DRAFT', 'SUBMITTED', 'APPROVED'])[:5]
    recent_batches = batches_qs[:8]
    recent_status_changes = StudentStatusHistory.objects.select_related('student', 'authorized_by').order_by('-created_at')[:6]

    context = {
        'active_menu': 'promotion',
        'page_title': 'Student Promotion Management Dashboard',
        'current_year': current_year,
        'user_role': user_role,
        'total_candidates': total_candidates,
        'promoted_count': promoted_count,
        'repeated_count': repeated_count,
        'graduated_count': graduated_count,
        'pending_count': pending_count,
        'transferred_count': transferred_count,
        'active_batches': active_batches,
        'recent_batches': recent_batches,
        'recent_status_changes': recent_status_changes,
        'is_management': user_role in ['ADMIN', 'REGISTRAR', 'PRINCIPAL'],
        'can_approve': user_role in ['ADMIN', 'PRINCIPAL'],
    }
    return render(request, 'promotion/dashboard.html', context)


# -----------------------------------------------------------------------------
# 2. PROMOTION PREPARATION (CREATE BATCH)
# -----------------------------------------------------------------------------

@management_staff_required
def promotion_prepare_view(request):
    """
    Step 1: Select source academic year, target academic year, grade, and policy criteria
    to assemble a promotion cohort.
    """
    user_role = _get_user_role(request.user)

    if request.method == 'POST':
        form = PromotionBatchCreateForm(request.POST)
        if form.is_valid():
            try:
                batch = PromotionBatchService.create_batch(
                    name=form.cleaned_data['name'],
                    academic_year=form.cleaned_data['academic_year'],
                    target_academic_year=form.cleaned_data['target_academic_year'],
                    grade=form.cleaned_data['grade'],
                    criteria=form.cleaned_data.get('promotion_criteria'),
                    user=request.user,
                    request=request
                )
                messages.success(
                    request,
                    f"Promotion batch '{batch.name}' initiated with {batch.total_candidates} candidates evaluated."
                )
                return redirect('promotion_batch_detail', batch_id=batch.id)
            except ValidationError as e:
                form.add_error(None, e.message if hasattr(e, 'message') else str(e))
    else:
        form = PromotionBatchCreateForm()

    context = {
        'active_menu': 'promotion',
        'page_title': 'Initiate Promotion Batch',
        'form': form,
        'user_role': user_role,
    }
    return render(request, 'promotion/prepare.html', context)


# -----------------------------------------------------------------------------
# 3. PROMOTION BATCH DETAIL & CANDIDATE ROSTER
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def promotion_batch_detail_view(request, batch_id):
    """
    Interactive candidate evaluation roster for a specific cohort.
    Displays academic averages, failing marks, attendance %, and proposed outcomes.
    Allows adjusting student decisions before committee submission.
    """
    batch = get_object_or_404(
        PromotionBatch.objects.select_related(
            'academic_year', 'target_academic_year', 'grade', 'promotion_criteria', 'created_by', 'approved_by'
        ),
        pk=batch_id
    )
    user_role = _get_user_role(request.user)

    records_qs = batch.records.select_related(
        'student',
        'student_enrollment',
        'previous_class_offering__section',
        'next_grade',
        'next_class_offering__grade',
        'next_class_offering__section'
    ).order_by('student__first_name', 'student__father_name')

    # Optional outcome filter
    outcome_filter = request.GET.get('outcome')
    if outcome_filter:
        records_qs = records_qs.filter(final_outcome=outcome_filter)

    search_q = request.GET.get('q', '').strip()
    if search_q:
        records_qs = records_qs.filter(
            Q(student__first_name__icontains=search_q) |
            Q(student__father_name__icontains=search_q) |
            Q(student__admission_number__icontains=search_q)
        )

    # Available classes in target year for inline assignment
    target_classes = ClassOffering.objects.filter(
        academic_year=batch.target_academic_year
    ).select_related('grade', 'section')

    context = {
        'active_menu': 'promotion',
        'page_title': f"Promotion Cohort: {batch.name}",
        'batch': batch,
        'records': records_qs,
        'total_count': records_qs.count(),
        'outcome_filter': outcome_filter,
        'search_q': search_q,
        'target_classes': target_classes,
        'user_role': user_role,
        'can_edit': batch.status in ['DRAFT', 'REJECTED'] and user_role in ['ADMIN', 'REGISTRAR'],
        'can_submit': batch.status in ['DRAFT', 'REJECTED'] and user_role in ['ADMIN', 'REGISTRAR'] and batch.total_candidates > 0,
        'can_approve': batch.status == 'SUBMITTED' and user_role in ['ADMIN', 'PRINCIPAL'],
        'can_finalize': batch.status == 'APPROVED' and user_role in ['ADMIN', 'PRINCIPAL', 'REGISTRAR'],
    }
    return render(request, 'promotion/batch_detail.html', context)


# -----------------------------------------------------------------------------
# 4. PROMOTION RECORD OUTCOME UPDATE
# -----------------------------------------------------------------------------

@require_POST
@management_staff_required
def promotion_record_update_view(request, record_id):
    """Saves human adjustment of candidate outcome or target class."""
    record = get_object_or_404(PromotionRecord, pk=record_id)
    final_outcome = request.POST.get('final_outcome')
    next_class_id = request.POST.get('next_class_offering') or None
    remarks = request.POST.get('remarks', '').strip()

    try:
        PromotionBatchService.update_record_outcome(
            record_id=record.id,
            final_outcome=final_outcome,
            next_class_offering_id=next_class_id,
            remarks=remarks,
            user=request.user,
            request=request
        )
        messages.success(request, f"Outcome for {record.student.full_name} updated to {final_outcome}.")
    except ValidationError as e:
        messages.error(request, str(e.message if hasattr(e, 'message') else e))

    return redirect('promotion_batch_detail', batch_id=record.batch_id)


# -----------------------------------------------------------------------------
# 5. SUBMIT BATCH FOR COMMITTEE REVIEW
# -----------------------------------------------------------------------------

@require_POST
@management_staff_required
def promotion_batch_submit_view(request, batch_id):
    """Registrar submits prepared batch to Principal / Examination Committee."""
    batch = get_object_or_404(PromotionBatch, pk=batch_id)
    try:
        PromotionApprovalService.submit_for_review(batch, user=request.user, request=request)
        messages.success(request, f"Batch '{batch.name}' submitted for administrative review and approval.")
    except ValidationError as e:
        messages.error(request, str(e))
    return redirect('promotion_batch_detail', batch_id=batch.id)


# -----------------------------------------------------------------------------
# 6. PROMOTION PREVIEW
# -----------------------------------------------------------------------------

@management_staff_required
def promotion_preview_view(request, batch_id):
    """
    Formal preview screen before confirmation showing complete cohort breakdown,
    transition projections, and validation checks.
    """
    batch = get_object_or_404(
        PromotionBatch.objects.select_related('academic_year', 'target_academic_year', 'grade', 'promotion_criteria'),
        pk=batch_id
    )
    user_role = _get_user_role(request.user)

    records = batch.records.select_related(
        'student', 'previous_class_offering__section', 'next_grade', 'next_class_offering__grade', 'next_class_offering__section'
    ).order_by('student__first_name')

    # Outcome breakdown counts
    counts = {
        'promoted': batch.promoted_count,
        'repeated': batch.repeated_count,
        'graduated': batch.graduated_count,
        'pending': batch.pending_count,
        'transferred': batch.records.filter(final_outcome='TRANSFERRED').count(),
        'withdrawn': batch.records.filter(final_outcome='WITHDRAWN').count(),
        'total': batch.total_candidates,
    }

    context = {
        'active_menu': 'promotion',
        'page_title': f"Promotion Preview - {batch.name}",
        'batch': batch,
        'records': records,
        'counts': counts,
        'user_role': user_role,
        'can_approve': batch.status == 'SUBMITTED' and user_role in ['ADMIN', 'PRINCIPAL'],
        'can_finalize': batch.status == 'APPROVED' and user_role in ['ADMIN', 'PRINCIPAL', 'REGISTRAR'],
    }
    return render(request, 'promotion/preview.html', context)


# -----------------------------------------------------------------------------
# 7. PROMOTION COMMITTEE APPROVAL
# -----------------------------------------------------------------------------

@principal_or_registrar_required
def promotion_approval_view(request, batch_id):
    """Principal / Committee approval form to authorize or return promotion batch."""
    batch = get_object_or_404(PromotionBatch, pk=batch_id)

    if request.method == 'POST':
        form = PromotionApprovalForm(request.POST)
        if form.is_valid():
            decision = form.cleaned_data['decision']
            comments = form.cleaned_data['comments']
            try:
                PromotionApprovalService.review_batch(
                    batch=batch,
                    decision=decision,
                    reviewer_user=request.user,
                    comments=comments,
                    request=request
                )
                if decision == 'APPROVED':
                    messages.success(request, f"Promotion Batch '{batch.name}' approved successfully. Ready for final enrollment.")
                else:
                    messages.warning(request, f"Promotion Batch '{batch.name}' returned for revision.")
                return redirect('promotion_batch_detail', batch_id=batch.id)
            except ValidationError as e:
                form.add_error(None, str(e))
    else:
        form = PromotionApprovalForm(initial={'decision': 'APPROVED'})

    context = {
        'active_menu': 'promotion',
        'page_title': f"Review Promotion Batch: {batch.name}",
        'batch': batch,
        'form': form,
    }
    return render(request, 'promotion/approval.html', context)


# -----------------------------------------------------------------------------
# 8. FINALIZE & EXECUTE PROMOTIONS (ENROLL IN NEXT YEAR)
# -----------------------------------------------------------------------------

@require_POST
@management_staff_required
def promotion_finalize_view(request, batch_id):
    """
    Executes transaction-safe atomic batch enrollment into target academic year.
    Closes old enrollments and creates new StudentEnrollment records.
    """
    batch = get_object_or_404(PromotionBatch, pk=batch_id)
    try:
        result = PromotionApprovalService.finalize_promotions(batch, user=request.user, request=request)
        messages.success(
            request,
            f"Batch '{batch.name}' finalized successfully! "
            f"({result['promoted']} Promoted, {result['repeated']} Repeated, "
            f"{result['graduated']} Graduated, {result['transferred']} Transferred, "
            f"{result['withdrawn']} Withdrawn)."
        )
    except ValidationError as e:
        messages.error(request, str(e.message if hasattr(e, 'message') else e))

    return redirect('promotion_batch_detail', batch_id=batch.id)


# -----------------------------------------------------------------------------
# 9. STUDENT ACADEMIC HISTORY (LONGITUDINAL TRANSCRIPT)
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def student_academic_history_view(request, student_id):
    """
    Comprehensive chronological transcript of the student across all grades,
    including enrollments, examination results, attendance statistics, promotion decisions,
    and official status records.
    """
    student = get_object_or_404(Student, pk=student_id)
    history = StudentAcademicHistoryService.get_student_academic_history(student)

    context = {
        'active_menu': 'promotion',
        'page_title': f"Academic History: {student.full_name}",
        'student': student,
        'history': history,
    }
    return render(request, 'promotion/academic_history.html', context)


# -----------------------------------------------------------------------------
# 10. GRADUATION MANAGEMENT (GRADE 12)
# -----------------------------------------------------------------------------

@management_staff_required
def graduation_management_view(request):
    """Grade 12 graduation candidates review, approval, and certification registry."""
    current_year = AcademicYear.objects.filter(is_current=True).first()
    selected_year_id = request.GET.get('academic_year')
    year = AcademicYear.objects.filter(pk=selected_year_id).first() if selected_year_id else current_year

    candidates = GraduationService.get_graduation_candidates(academic_year=year)
    all_years = AcademicYear.objects.all().order_by('-start_date')

    # Status update action
    if request.method == 'POST':
        grad_id = request.POST.get('graduation_id')
        status = request.POST.get('status')
        cert_no = request.POST.get('certificate_number', '').strip()
        remarks = request.POST.get('remarks', '').strip()

        grad_rec = get_object_or_404(GraduationRecord, pk=grad_id)
        grad_rec.status = status
        grad_rec.certificate_number = cert_no
        grad_rec.remarks = remarks
        grad_rec.approved_by = request.user
        grad_rec.save()

        # Update student status if graduated
        if status == 'GRADUATED':
            grad_rec.student.status = 'GRADUATED'
            grad_rec.student.save(update_fields=['status'])

        messages.success(request, f"Graduation record for {grad_rec.student.full_name} updated to {status}.")
        return redirect('graduation_management')

    context = {
        'active_menu': 'promotion',
        'page_title': 'Grade 12 Graduation Management',
        'academic_year': year,
        'all_years': all_years,
        'candidates': candidates,
        'total_candidates': len(candidates),
    }
    return render(request, 'promotion/graduation.html', context)


# -----------------------------------------------------------------------------
# 11. STUDENT TRANSFERS & WITHDRAWALS
# -----------------------------------------------------------------------------

@management_staff_required
def student_status_change_view(request):
    """Records student transfers, formal withdrawals, dropouts, or readmissions."""
    student_id = request.GET.get('student_id') or request.POST.get('student_id')
    student = get_object_or_404(Student, pk=student_id) if student_id else None

    if request.method == 'POST':
        form = StudentStatusChangeForm(request.POST)
        if form.is_valid():
            history = form.save(commit=False)
            history.student = student
            history.authorized_by = request.user
            history.previous_status = student.status

            new_status_map = {
                'TRANSFER_OUT': 'TRANSFERRED',
                'WITHDRAWAL': 'WITHDRAWN',
                'DROPOUT': 'DROPPED',
                'SUSPENSION': 'ACTIVE',
                'READMISSION': 'ACTIVE',
                'GRADUATION': 'GRADUATED'
            }
            new_status = new_status_map.get(history.status_type, 'ACTIVE')
            history.new_status = new_status
            history.save()

            # Update student record
            student.status = new_status
            student.save(update_fields=['status'])

            # Close active enrollment if transferring or withdrawing
            if new_status in ['TRANSFERRED', 'WITHDRAWN', 'DROPPED']:
                active_enr = student.enrollments.filter(status='ACTIVE').first()
                if active_enr:
                    active_enr.status = 'WITHDRAWN'
                    active_enr.save(update_fields=['status'])

            messages.success(request, f"Status updated for {student.full_name} to {new_status}.")
            return redirect('student_academic_history', student_id=student.id)
    else:
        form = StudentStatusChangeForm(initial={'student_id': student.id if student else ''})

    context = {
        'active_menu': 'promotion',
        'page_title': f"Student Status Change: {student.full_name if student else 'Select Student'}",
        'student': student,
        'form': form,
    }
    return render(request, 'promotion/status_change.html', context)


@any_authenticated_role_required
def student_status_history_view(request):
    """School-wide audit directory of student transfers, withdrawals, and departures."""
    histories_qs = StudentStatusHistory.objects.select_related('student', 'authorized_by').order_by('-effective_date')

    status_filter = request.GET.get('status_type')
    if status_filter:
        histories_qs = histories_qs.filter(status_type=status_filter)

    search_q = request.GET.get('q', '').strip()
    if search_q:
        histories_qs = histories_qs.filter(
            Q(student__first_name__icontains=search_q) |
            Q(student__father_name__icontains=search_q) |
            Q(student__admission_number__icontains=search_q) |
            Q(destination_school__icontains=search_q)
        )

    paginator = Paginator(histories_qs, 15)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'active_menu': 'promotion',
        'page_title': 'Transfers & Withdrawals Registry',
        'page_obj': page_obj,
        'histories': page_obj,
        'status_filter': status_filter,
        'search_q': search_q,
    }
    return render(request, 'promotion/status_history.html', context)


# -----------------------------------------------------------------------------
# 12. PROMOTION REPORTS & EXPORTS
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def promotion_reports_view(request):
    """Promotion and academic progression reports directory."""
    batches = PromotionBatch.objects.select_related('academic_year', 'target_academic_year', 'grade').order_by('-created_at')
    current_year = AcademicYear.objects.filter(is_current=True).first()

    selected_batch_id = request.GET.get('batch')
    selected_batch = PromotionBatch.objects.filter(pk=selected_batch_id).first() if selected_batch_id else batches.first()

    context = {
        'active_menu': 'promotion',
        'page_title': 'Student Promotion & Progression Reports',
        'batches': batches,
        'selected_batch': selected_batch,
        'current_year': current_year,
    }
    return render(request, 'promotion/reports.html', context)


@any_authenticated_role_required
def export_promotion_pdf_view(request, batch_id):
    """Exports batch promotion roster as official PDF."""
    batch = get_object_or_404(PromotionBatch, pk=batch_id)
    filename = f"Promotion_Roster_{batch.name.replace(' ', '_')}_{batch.academic_year.code}.pdf"
    return PromotionReportService.export_promotion_batch_pdf(batch, filename=filename)


@any_authenticated_role_required
def export_promotion_excel_view(request, batch_id):
    """Exports batch promotion roster as Microsoft Excel spreadsheet."""
    batch = get_object_or_404(PromotionBatch, pk=batch_id)
    filename = f"Promotion_Roster_{batch.name.replace(' ', '_')}_{batch.academic_year.code}.xlsx"
    return PromotionReportService.export_promotion_batch_excel(batch, filename=filename)


# -----------------------------------------------------------------------------
# 13. PROMOTION POLICY CRITERIA MANAGEMENT
# -----------------------------------------------------------------------------

@management_staff_required
def promotion_criteria_view(request):
    """Manages configurable promotion policy criteria."""
    criteria_list = PromotionCriteria.objects.all().order_by('-is_default', 'name')
    form = PromotionCriteriaForm()

    if request.method == 'POST':
        form = PromotionCriteriaForm(request.POST)
        if form.is_valid():
            c = form.save()
            messages.success(request, f"Promotion Criteria Policy '{c.name}' saved successfully.")
            return redirect('promotion_criteria')

    context = {
        'active_menu': 'promotion',
        'page_title': 'Configurable Promotion Criteria Policies',
        'criteria_list': criteria_list,
        'form': form,
    }
    return render(request, 'promotion/criteria.html', context)
