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
from django.utils import timezone

from accounts.decorators import (
    any_authenticated_role_required,
    registrar_required,
    principal_required,
    principal_or_registrar_required,
)
from students.models import (
    Student,
    StudentEnrollment,
    PromotionRecord,
    StudentIDCard,
    StudentCertificate,
)
from academics.models import AcademicYear, Grade, Section, Stream, ClassOffering
from teachers.models import Teacher, TeacherAssignment
from attendance.models import AttendanceRecord
from results.models import Mark
from students.forms import (
    StudentRegistrationForm,
    StudentEditForm,
    StudentEnrollmentForm,
    StudentStatusUpdateForm,
    IDCardFilterForm,
    IDCardRevokeForm,
    CertificateRequestForm,
    CertificateFilterForm,
    CertificateApprovalForm,
    CertificateRevokeForm,
)
from students.services import StudentService, StudentIDCardService, CertificateService


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


# ---------------------------------------------------------------------------
# 7. STEP 22: STUDENT ID CARD MANAGEMENT & QR CODE VERIFICATION
# ---------------------------------------------------------------------------

def _get_user_role(user):
    if user.is_superuser:
        return 'ADMIN'
    if user.role:
        return user.role.code
    return None


@any_authenticated_role_required
def id_card_hub_view(request):
    """
    Step 22: Central Student ID Card Management Hub.
    Provides directory search, academic filtering, status badges,
    single/batch generation, printable PDF triggers, and card lifecycle management.
    """
    user_role = _get_user_role(request.user)
    teacher_profile = getattr(request.user, 'teacher_profile', None) if user_role == 'TEACHER' else None

    form = IDCardFilterForm(request.GET or None, teacher=teacher_profile)

    scoped_students = StudentService.get_scoped_queryset(request.user)
    current_year = AcademicYear.objects.filter(is_current=True).first()

    # Active filters
    students_qs = scoped_students
    selected_year = current_year

    if form.is_valid():
        search_q = form.cleaned_data.get('q')
        if search_q:
            students_qs = students_qs.filter(
                Q(admission_number__icontains=search_q) |
                Q(first_name__icontains=search_q) |
                Q(father_name__icontains=search_q) |
                Q(grandfather_name__icontains=search_q)
            )

        ay = form.cleaned_data.get('academic_year')
        if ay:
            selected_year = ay
            students_qs = students_qs.filter(enrollments__academic_year=ay)

        grade = form.cleaned_data.get('grade')
        if grade:
            students_qs = students_qs.filter(enrollments__class_offering__grade=grade)

        co = form.cleaned_data.get('class_offering')
        if co:
            students_qs = students_qs.filter(enrollments__class_offering=co)

        card_status = form.cleaned_data.get('status')
        if card_status == 'ACTIVE':
            students_qs = students_qs.filter(id_cards__status='ACTIVE')
        elif card_status == 'REVOKED':
            students_qs = students_qs.filter(id_cards__status='REVOKED')
        elif card_status == 'EXPIRED':
            students_qs = students_qs.filter(id_cards__status='EXPIRED')
        elif card_status == 'NOT_ISSUED':
            students_qs = students_qs.exclude(id_cards__status='ACTIVE')

    students_qs = students_qs.distinct().prefetch_related(
        'enrollments__class_offering__grade',
        'enrollments__class_offering__section',
        'enrollments__class_offering__stream',
        'enrollments__academic_year',
        'id_cards'
    ).order_by('first_name', 'father_name')

    # Metrics calculation
    active_cards_count = StudentIDCard.objects.filter(
        student__in=scoped_students,
        status='ACTIVE'
    ).count()

    year_cards_count = StudentIDCard.objects.filter(
        student__in=scoped_students,
        academic_year=selected_year,
        status='ACTIVE'
    ).count() if selected_year else active_cards_count

    revoked_cards_count = StudentIDCard.objects.filter(
        student__in=scoped_students,
        status='REVOKED'
    ).count()

    # Pagination (20 per page)
    paginator = Paginator(students_qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Attach active ID card and enrollment context to current page items
    student_rows = []
    for st in page_obj:
        active_card = st.id_cards.filter(status='ACTIVE').first()
        latest_card = st.id_cards.order_by('-created_at').first()
        enrollment = st.enrollments.filter(academic_year=selected_year, status='ACTIVE').first() or st.enrollments.filter(status='ACTIVE').first()

        student_rows.append({
            'student': st,
            'active_card': active_card,
            'latest_card': latest_card,
            'enrollment': enrollment,
            'class_offering': enrollment.class_offering if enrollment else None,
        })

    revoke_form = IDCardRevokeForm()

    context = {
        'active_menu': 'id_cards',
        'page_title': 'Student ID Card Management',
        'form': form,
        'revoke_form': revoke_form,
        'page_obj': page_obj,
        'student_rows': student_rows,
        'active_cards_count': active_cards_count,
        'year_cards_count': year_cards_count,
        'revoked_cards_count': revoked_cards_count,
        'total_students_count': students_qs.count(),
        'selected_year': selected_year,
        'user_role': user_role,
        'is_management': user_role in ('ADMIN', 'PRINCIPAL', 'REGISTRAR'),
    }
    return render(request, 'students/id_card_hub.html', context)


@any_authenticated_role_required
def id_card_preview_view(request, student_id):
    """
    Step 22: Displays high-fidelity interactive preview of a student's ID card (Front & Back)
    including live vector QR code and institutional branding.
    """
    student = get_object_or_404(Student, pk=student_id)

    # RBAC check
    scoped_students = StudentService.get_scoped_queryset(request.user)
    if not scoped_students.filter(pk=student.pk).exists():
        raise PermissionDenied("You do not have permission to view ID cards for this student.")

    # Get active card or latest card or draft one
    id_card = student.id_cards.filter(status='ACTIVE').first() or student.id_cards.order_by('-created_at').first()

    if not id_card:
        # Create card on the fly if user is authorized
        current_year = AcademicYear.objects.filter(is_current=True).first()
        id_card, _ = StudentIDCardService.get_or_create_id_card(
            student=student,
            academic_year=current_year,
            issued_by=request.user,
            request=request
        )

    card_data = StudentIDCardService.get_card_context(id_card, request=request)

    context = {
        'active_menu': 'id_cards',
        'page_title': f"ID Card: {student.full_name}",
        'data': card_data,
        'student': student,
        'card': id_card,
        'user_role': _get_user_role(request.user),
    }
    return render(request, 'students/id_card_preview.html', context)


@any_authenticated_role_required
@require_POST
def id_card_generate_view(request, student_id):
    """
    Step 22: Issues or re-issues an ID card for an individual student.
    """
    student = get_object_or_404(Student, pk=student_id)

    scoped_students = StudentService.get_scoped_queryset(request.user)
    if not scoped_students.filter(pk=student.pk).exists():
        raise PermissionDenied("You do not have permission to issue ID cards for this student.")

    reissue = request.POST.get('reissue') == '1'
    current_year = AcademicYear.objects.filter(is_current=True).first()

    try:
        card, created = StudentIDCardService.get_or_create_id_card(
            student=student,
            academic_year=current_year,
            issued_by=request.user,
            force_new=reissue,
            request=request
        )
        if created and reissue:
            messages.success(request, f"New ID Card '{card.card_number}' successfully issued for {student.full_name}.")
        elif created:
            messages.success(request, f"ID Card '{card.card_number}' generated for {student.full_name}.")
        else:
            messages.info(request, f"Student already has an active ID Card ({card.card_number}).")
    except ValidationError as e:
        messages.error(request, str(e))

    next_url = request.POST.get('next')
    if next_url:
        return redirect(next_url)
    return redirect('id_card_preview', student_id=student.id)


@any_authenticated_role_required
@require_POST
def id_card_batch_generate_view(request):
    """
    Step 22: Batch generation of ID cards for an entire grade or section.
    """
    user_role = _get_user_role(request.user)
    if user_role not in ('ADMIN', 'PRINCIPAL', 'REGISTRAR'):
        raise PermissionDenied("Only administrative staff may trigger batch ID card generation.")

    class_offering_id = request.POST.get('class_offering')
    grade_id = request.POST.get('grade')
    academic_year_id = request.POST.get('academic_year')
    force_new = request.POST.get('force_new') == '1'

    class_offering = ClassOffering.objects.filter(pk=class_offering_id).first() if class_offering_id else None
    grade = Grade.objects.filter(pk=grade_id).first() if grade_id else None
    academic_year = AcademicYear.objects.filter(pk=academic_year_id).first() if academic_year_id else AcademicYear.objects.filter(is_current=True).first()

    result = StudentIDCardService.batch_generate_id_cards(
        class_offering=class_offering,
        grade=grade,
        academic_year=academic_year,
        issued_by=request.user,
        force_new=force_new,
        request=request
    )

    if result['errors']:
        messages.warning(
            request,
            f"Batch generation completed with warnings: {result['created']} created, {result['reused']} existing active. {len(result['errors'])} errors occurred."
        )
    else:
        messages.success(
            request,
            f"Batch ID card generation complete: {result['created']} cards issued, {result['reused']} existing active cards retained."
        )

    return redirect('id_card_hub')


@any_authenticated_role_required
def id_card_pdf_view(request, card_id):
    """
    Step 22: Exports standalone 2-page CR80 vector PDF (Front & Back) for an ID card.
    """
    id_card = get_object_or_404(StudentIDCard.objects.select_related('student', 'academic_year'), pk=card_id)

    scoped_students = StudentService.get_scoped_queryset(request.user)
    if not scoped_students.filter(pk=id_card.student.pk).exists():
        raise PermissionDenied("You do not have permission to export this ID card.")

    return StudentIDCardService.export_single_card_pdf(id_card, request=request)


@any_authenticated_role_required
def id_card_batch_pdf_view(request):
    """
    Step 22: Exports multi-card printable PDF sheet (4 cards per page grid with cut marks).
    """
    scoped_students = StudentService.get_scoped_queryset(request.user)
    cards_qs = StudentIDCard.objects.filter(
        student__in=scoped_students,
        status='ACTIVE'
    ).select_related('student', 'enrollment__class_offering__grade', 'enrollment__class_offering__section', 'academic_year')

    # Apply filters
    class_offering_id = request.GET.get('class_offering')
    if class_offering_id:
        cards_qs = cards_qs.filter(enrollment__class_offering_id=class_offering_id)

    grade_id = request.GET.get('grade')
    if grade_id:
        cards_qs = cards_qs.filter(enrollment__class_offering__grade_id=grade_id)

    ay_id = request.GET.get('academic_year')
    if ay_id:
        cards_qs = cards_qs.filter(academic_year_id=ay_id)

    cards_qs = cards_qs.order_by('enrollment__class_offering__grade__level', 'enrollment__class_offering__section__name', 'student__first_name')

    if not cards_qs.exists():
        messages.warning(request, "No active ID cards found matching the selected export criteria.")
        return redirect('id_card_hub')

    filename = f"StudentID_Batch_Sheet_{timezone.now():%Y%m%d_%H%M%S}.pdf"
    return StudentIDCardService.export_batch_cards_pdf(cards_qs, filename=filename, request=request)


@any_authenticated_role_required
@require_POST
def id_card_revoke_view(request, card_id):
    """
    Step 22: Revokes an active ID card with mandatory logged justification.
    """
    user_role = _get_user_role(request.user)
    if user_role not in ('ADMIN', 'PRINCIPAL', 'REGISTRAR'):
        raise PermissionDenied("Only administrative staff may revoke student ID cards.")

    id_card = get_object_or_404(StudentIDCard.objects.select_related('student'), pk=card_id)
    form = IDCardRevokeForm(request.POST)
    if form.is_valid():
        reason = form.cleaned_data['reason']
        StudentIDCardService.revoke_card(id_card, reason=reason, user=request.user, request=request)
        messages.success(request, f"ID Card '{id_card.card_number}' for {id_card.student.full_name} has been revoked.")
    else:
        messages.error(request, "Please provide a valid revocation reason.")

    return redirect('id_card_hub')


@any_authenticated_role_required
@require_POST
def id_card_reprint_view(request, card_id):
    """
    Step 22: Logs a reprint event and redirects to the PDF export.
    """
    id_card = get_object_or_404(StudentIDCard.objects.select_related('student'), pk=card_id)
    StudentIDCardService.reprint_card(id_card, user=request.user, request=request)
    return redirect('id_card_pdf', card_id=id_card.id)


def id_card_verify_view(request, card_uuid):
    """
    Step 22: QR Code Scanning Destination on Local School LAN.
    Publicly accessible across LAN to verify ID card authenticity.
    CRITICAL SECURITY: Does NOT expose confidential student PII (no address, phone, or guardian contacts).
    """
    id_card = StudentIDCard.objects.filter(
        card_uuid=card_uuid
    ).select_related(
        'student',
        'enrollment__class_offering__grade',
        'enrollment__class_offering__section',
        'enrollment__class_offering__stream',
        'academic_year'
    ).first()

    # Log verification scan to audit log
    if id_card:
        StudentService.log_audit(
            request,
            'VERIFY_QR_SCAN',
            id_card.student,
            {
                'card_number': id_card.card_number,
                'status': id_card.verification_status,
                'card_uuid': str(card_uuid)
            }
        )

    context = {
        'page_title': 'Student ID Card Verification',
        'id_card': id_card,
        'verification_status': id_card.verification_status if id_card else 'INVALID',
        'is_staff_user': request.user.is_authenticated,
    }
    return render(request, 'students/id_card_verify.html', context)


# ---------------------------------------------------------------------------
# 11. STEP 23: STUDENT TRANSFER & LEAVING CERTIFICATE MANAGEMENT
# ---------------------------------------------------------------------------

@principal_or_registrar_required
def certificate_hub_view(request):
    """
    Central management hub for Student Transfer and Leaving Certificates.
    Displays summary KPI metrics, multi-parameter search/filters, and certificate roster.
    """
    queryset = StudentCertificate.objects.select_related(
        'student',
        'academic_year',
        'last_grade',
        'requested_by',
        'approved_by',
        'issued_by'
    ).order_by('-created_at')

    # Metrics
    total_count = queryset.count()
    draft_count = queryset.filter(status='DRAFT').count()
    submitted_count = queryset.filter(status='SUBMITTED').count()
    approved_count = queryset.filter(status='APPROVED').count()
    issued_count = queryset.filter(status='ISSUED').count()
    transfer_count = queryset.filter(certificate_type='TRANSFER', status='ISSUED').count()
    leaving_count = queryset.filter(certificate_type='LEAVING', status='ISSUED').count()
    revoked_count = queryset.filter(status='REVOKED').count()

    filter_form = CertificateFilterForm(request.GET)
    if filter_form.is_valid():
        search_query = filter_form.cleaned_data.get('search')
        if search_query:
            queryset = queryset.filter(
                Q(student__first_name__icontains=search_query) |
                Q(student__father_name__icontains=search_query) |
                Q(student__grandfather_name__icontains=search_query) |
                Q(student__admission_number__icontains=search_query) |
                Q(certificate_number__icontains=search_query) |
                Q(destination_school__icontains=search_query)
            )

        cert_type = filter_form.cleaned_data.get('certificate_type')
        if cert_type and cert_type != 'ALL':
            queryset = queryset.filter(certificate_type=cert_type)

        academic_year = filter_form.cleaned_data.get('academic_year')
        if academic_year:
            queryset = queryset.filter(academic_year=academic_year)

        grade = filter_form.cleaned_data.get('grade')
        if grade:
            queryset = queryset.filter(last_grade=grade)

        status_val = filter_form.cleaned_data.get('status')
        if status_val and status_val != 'ALL':
            queryset = queryset.filter(status=status_val)

    paginator = Paginator(queryset, 15)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    # Clean query string for pagination links
    query_params = request.GET.copy()
    if 'page' in query_params:
        query_params.pop('page')
    query_string = query_params.urlencode()

    is_approver = request.user.is_superuser or (
        request.user.role and request.user.role.code in ['PRINCIPAL', 'ADMIN']
    )

    context = {
        'page_title': 'Transfer & Leaving Certificates',
        'active_menu': 'certificates',
        'certificates': page_obj,
        'page_obj': page_obj,
        'filter_form': filter_form,
        'query_string': query_string,
        'total_count': total_count,
        'draft_count': draft_count,
        'submitted_count': submitted_count,
        'approved_count': approved_count,
        'issued_count': issued_count,
        'transfer_count': transfer_count,
        'leaving_count': leaving_count,
        'revoked_count': revoked_count,
        'is_approver': is_approver,
    }
    return render(request, 'students/certificate_hub.html', context)


@principal_or_registrar_required
def certificate_create_view(request, student_id=None):
    """
    Creates a new Transfer or Leaving Certificate request for a student.
    Auto-populates fields from active or historical student enrollments.
    """
    student = None
    if student_id:
        student = get_object_or_404(Student, pk=student_id)

    # Initial data defaults from student's active or latest enrollment
    initial_data = {}
    if student:
        active_enr = student.enrollments.select_related('academic_year', 'class_offering__grade', 'class_offering__section', 'class_offering__stream').order_by('-academic_year__start_date').first()
        if active_enr:
            initial_data['academic_year'] = active_enr.academic_year
            if active_enr.class_offering:
                initial_data['last_grade'] = active_enr.class_offering.grade
                if active_enr.class_offering.section:
                    initial_data['section_name'] = f"Section {active_enr.class_offering.section.name}"
                if active_enr.class_offering.stream:
                    initial_data['stream_name'] = active_enr.class_offering.stream.name

        latest_prom = student.promotion_records.order_by('-created_at').first()
        if latest_prom:
            initial_data['academic_standing'] = f"{latest_prom.get_decision_display()} to {latest_prom.to_grade.name if latest_prom.to_grade else 'Next Level'}"
        else:
            initial_data['academic_standing'] = "In Good Standing"

        initial_data['effective_date'] = timezone.now().date()
        initial_data['conduct'] = 'Good'

    if request.method == 'POST':
        if not student:
            selected_student_id = request.POST.get('student_id')
            student = get_object_or_404(Student, pk=selected_student_id)

        form = CertificateRequestForm(request.POST)
        if form.is_valid():
            try:
                cert = CertificateService.create_certificate_request(
                    student=student,
                    certificate_type=form.cleaned_data['certificate_type'],
                    academic_year=form.cleaned_data['academic_year'],
                    last_grade=form.cleaned_data['last_grade'],
                    section_name=form.cleaned_data.get('section_name', ''),
                    stream_name=form.cleaned_data.get('stream_name', ''),
                    effective_date=form.cleaned_data.get('effective_date'),
                    destination_school=form.cleaned_data.get('destination_school', ''),
                    reason=form.cleaned_data.get('reason', ''),
                    academic_standing=form.cleaned_data.get('academic_standing', ''),
                    conduct=form.cleaned_data.get('conduct', 'Good'),
                    remarks=form.cleaned_data.get('remarks', ''),
                    requested_by=request.user,
                    request=request
                )

                # Submit immediately if button clicked
                if 'submit_now' in request.POST:
                    CertificateService.submit_certificate(cert, user=request.user, request=request)
                    messages.success(request, f"{cert.get_certificate_type_display()} request submitted for administrative review.")
                else:
                    messages.success(request, f"{cert.get_certificate_type_display()} draft created successfully.")

                return redirect('certificate_preview', certificate_id=cert.pk)
            except Exception as e:
                messages.error(request, f"Error creating certificate request: {str(e)}")
        else:
            messages.error(request, "Please correct the errors in the certificate form.")
    else:
        form = CertificateRequestForm(initial=initial_data)

    context = {
        'page_title': f"Request Certificate — {student.full_name}" if student else "Create Certificate Request",
        'active_menu': 'certificates',
        'student': student,
        'form': form,
    }
    return render(request, 'students/certificate_form.html', context)


@principal_or_registrar_required
def certificate_preview_view(request, certificate_id):
    """
    High-fidelity official certificate preview with print stylesheet and action workflow controls.
    """
    certificate = get_object_or_404(
        StudentCertificate.objects.select_related(
            'student',
            'academic_year',
            'last_grade',
            'requested_by',
            'approved_by',
            'issued_by',
            'revoked_by'
        ),
        pk=certificate_id
    )

    is_approver = request.user.is_superuser or (
        request.user.role and request.user.role.code in ['PRINCIPAL', 'ADMIN']
    )

    dual_issue_date = CertificateService.format_dual_date(certificate.issue_date or timezone.now().date())
    dual_admission_date = CertificateService.format_dual_date(certificate.admission_date) if certificate.admission_date else "Not Recorded"
    dual_effective_date = CertificateService.format_dual_date(certificate.effective_date) if certificate.effective_date else "Not Recorded"
    dual_dob = CertificateService.format_dual_date(certificate.student.date_of_birth) if certificate.student.date_of_birth else "Not Recorded"

    revoke_form = CertificateRevokeForm()
    approval_form = CertificateApprovalForm(initial={'decision': 'APPROVE'})

    context = {
        'page_title': f"Certificate Preview — {certificate.student.full_name}",
        'active_menu': 'certificates',
        'certificate': certificate,
        'is_approver': is_approver,
        'dual_issue_date': dual_issue_date,
        'dual_admission_date': dual_admission_date,
        'dual_effective_date': dual_effective_date,
        'dual_dob': dual_dob,
        'revoke_form': revoke_form,
        'approval_form': approval_form,
    }
    return render(request, 'students/certificate_preview.html', context)


@require_POST
@principal_or_registrar_required
def certificate_submit_view(request, certificate_id):
    """Submits a draft certificate request for administrative and principal review."""
    certificate = get_object_or_404(StudentCertificate, pk=certificate_id)
    try:
        CertificateService.submit_certificate(certificate, user=request.user, request=request)
        messages.success(request, f"{certificate.get_certificate_type_display()} successfully submitted for principal review.")
    except Exception as e:
        messages.error(request, f"Submission error: {str(e)}")
    return redirect('certificate_preview', certificate_id=certificate.pk)


@require_POST
def certificate_approve_view(request, certificate_id):
    """
    Principal approval view. Enforces RBAC: Only Principal or Admin may approve.
    """
    certificate = get_object_or_404(StudentCertificate, pk=certificate_id)

    # RBAC check
    is_approver = request.user.is_superuser or (
        request.user.is_authenticated and request.user.role and request.user.role.code in ['PRINCIPAL', 'ADMIN']
    )
    if not is_approver:
        raise PermissionDenied("Only the School Principal or Administrator may approve certificates.")

    remarks = request.POST.get('approval_remarks', '').strip()
    try:
        CertificateService.approve_certificate(certificate, user=request.user, remarks=remarks, request=request)
        messages.success(request, f"Certificate successfully APPROVED. It can now be officially issued.")
    except Exception as e:
        messages.error(request, f"Approval error: {str(e)}")

    return redirect('certificate_preview', certificate_id=certificate.pk)


@require_POST
def certificate_reject_view(request, certificate_id):
    """
    Principal rejection view. Enforces RBAC: Only Principal or Admin may reject.
    """
    certificate = get_object_or_404(StudentCertificate, pk=certificate_id)

    # RBAC check
    is_approver = request.user.is_superuser or (
        request.user.is_authenticated and request.user.role and request.user.role.code in ['PRINCIPAL', 'ADMIN']
    )
    if not is_approver:
        raise PermissionDenied("Only the School Principal or Administrator may reject certificates.")

    reason = request.POST.get('rejection_reason', '').strip()
    if not reason:
        messages.error(request, "A clear justification is required to reject a certificate request.")
        return redirect('certificate_preview', certificate_id=certificate.pk)

    try:
        CertificateService.reject_certificate(certificate, user=request.user, reason=reason, request=request)
        messages.warning(request, f"Certificate request was REJECTED.")
    except Exception as e:
        messages.error(request, f"Rejection error: {str(e)}")

    return redirect('certificate_preview', certificate_id=certificate.pk)


@require_POST
@principal_or_registrar_required
def certificate_issue_view(request, certificate_id):
    """
    Officially issues an approved certificate. Assigns reference number, issue date,
    and updates student status while preserving all academic history.
    """
    certificate = get_object_or_404(StudentCertificate, pk=certificate_id)
    try:
        CertificateService.issue_certificate(certificate, user=request.user, update_student_status=True, request=request)
        messages.success(request, f"Certificate officially ISSUED with Reference Number: {certificate.certificate_number}.")
    except Exception as e:
        messages.error(request, f"Issuance error: {str(e)}")

    return redirect('certificate_preview', certificate_id=certificate.pk)


@require_POST
@principal_or_registrar_required
def certificate_revoke_view(request, certificate_id):
    """
    Revokes an issued or approved certificate with mandatory justification.
    """
    certificate = get_object_or_404(StudentCertificate, pk=certificate_id)
    reason = request.POST.get('reason', '').strip()
    if not reason:
        messages.error(request, "A mandatory reason is required to revoke an official certificate.")
        return redirect('certificate_preview', certificate_id=certificate.pk)

    try:
        CertificateService.revoke_certificate(certificate, user=request.user, reason=reason, request=request)
        messages.warning(request, f"Certificate {certificate.certificate_number or certificate.pk} was officially REVOKED.")
    except Exception as e:
        messages.error(request, f"Revocation error: {str(e)}")

    return redirect('certificate_preview', certificate_id=certificate.pk)


@any_authenticated_role_required
def certificate_pdf_view(request, certificate_id):
    """
    Generates and downloads the official English-only A4 PDF certificate.
    """
    certificate = get_object_or_404(StudentCertificate, pk=certificate_id)
    return CertificateService.export_certificate_pdf(certificate, request=request)


@any_authenticated_role_required
def certificate_verify_view(request):
    """
    Internal Certificate Verification Search Portal for authorized staff.
    Searches by institutional reference number (MSS-TC-... or MSS-LC-...) or UUID.
    Does not expose sensitive PII over unauthenticated public endpoints.
    """
    query = (request.GET.get('query') or request.GET.get('q') or '').strip()
    certificate = None
    searched = bool(query)

    if query:
        # Search by certificate number or UUID
        certificate = StudentCertificate.objects.filter(
            Q(certificate_number__iexact=query) |
            Q(certificate_uuid__iexact=query)
        ).select_related('student', 'academic_year', 'last_grade', 'approved_by', 'issued_by').first()

    dual_issue_date = None
    dual_effective_date = None
    if certificate:
        dual_issue_date = CertificateService.format_dual_date(certificate.issue_date) if certificate.issue_date else "Not Issued"
        dual_effective_date = CertificateService.format_dual_date(certificate.effective_date) if certificate.effective_date else "Not Recorded"

    context = {
        'page_title': 'Certificate Verification Portal',
        'active_menu': 'certificates',
        'query': query,
        'certificate': certificate,
        'searched': searched,
        'search_performed': searched,
        'dual_issue_date': dual_issue_date,
        'dual_effective_date': dual_effective_date,
    }
    return render(request, 'students/certificate_verify.html', context)

