"""
Service layer for Timetable and Class Scheduling Management System.
Implements:
- Comprehensive multi-dimension conflict detection (Teacher, Class, Classroom, Break periods).
- Automated alternative period suggestions.
- Draft creation, cloning, and incremental versioning.
- Multi-tier committee approval and publication workflow.
- PDF (ReportLab) and Excel (OpenPyXL) timetable matrix export.
- LAN-audit logging via core AuditLog.
"""

from decimal import Decimal
import io
import json
from datetime import datetime, date, time
from django.db import transaction, models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.http import HttpResponse

from academics.models import AcademicYear, Grade, Section, Stream, Subject, ClassOffering
from teachers.models import Teacher, TeacherAssignment
from core.models import AuditLog

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


class TimetableAuditHelper:
    """Helper to record timetable events in the core AuditLog."""
    @staticmethod
    def log(request, action, resource_type, resource_id, details=None):
        user = getattr(request, 'user', None) if request else None
        ip_addr = request.META.get('REMOTE_ADDR') if request else None
        AuditLog.objects.create(
            actor=user if user and user.is_authenticated else None,
            action=action,
            entity_name=resource_type,
            record_id=str(resource_id),
            changes_json=details or {},
            ip_address=ip_addr
        )


class TimetableConfigService:
    """Configures and provisions school working days and period schedules."""

    @classmethod
    def get_active_working_days(cls, academic_year=None):
        """Returns ordered active school days for given academic year or global default."""
        days = SchoolDay.objects.filter(is_active=True)
        if academic_year:
            year_days = days.filter(academic_year=academic_year)
            if year_days.exists():
                return year_days.order_by('order', 'day_of_week')
        global_days = days.filter(academic_year__isnull=True).order_by('order', 'day_of_week')
        if not global_days.exists():
            cls.initialize_default_working_days()
            global_days = SchoolDay.objects.filter(academic_year__isnull=True, is_active=True).order_by('order', 'day_of_week')
        return global_days

    @classmethod
    def get_active_periods(cls, academic_year=None):
        """Returns ordered active periods for given academic year or global default."""
        periods = Period.objects.filter(is_active=True)
        if academic_year:
            year_periods = periods.filter(academic_year=academic_year)
            if year_periods.exists():
                return year_periods.order_by('period_number', 'start_time')
        global_periods = periods.filter(academic_year__isnull=True).order_by('period_number', 'start_time')
        if not global_periods.exists():
            cls.initialize_default_periods()
            global_periods = Period.objects.filter(academic_year__isnull=True, is_active=True).order_by('period_number', 'start_time')
        return global_periods

    @classmethod
    def initialize_default_working_days(cls, academic_year=None):
        """Seeds default Monday through Friday working days if none exist."""
        defaults = [
            (1, 'Monday', 'Mon', 1),
            (2, 'Tuesday', 'Tue', 2),
            (3, 'Wednesday', 'Wed', 3),
            (4, 'Thursday', 'Thu', 4),
            (5, 'Friday', 'Fri', 5),
        ]
        created_days = []
        for dow, name, short, order in defaults:
            day, _ = SchoolDay.objects.get_or_create(
                academic_year=academic_year,
                day_of_week=dow,
                defaults={
                    'name': name,
                    'short_name': short,
                    'order': order,
                    'is_active': True
                }
            )
            created_days.append(day)
        return created_days

    @classmethod
    def initialize_default_periods(cls, academic_year=None):
        """Seeds standard secondary school timetable period structure (6 lessons + 2 breaks)."""
        defaults = [
            (1, 'Period 1', time(8, 30), time(9, 15), False, 'NONE'),
            (2, 'Period 2', time(9, 15), time(10, 0), False, 'NONE'),
            (3, 'Morning Recess', time(10, 0), time(10, 20), True, 'SHORT_BREAK'),
            (4, 'Period 3', time(10, 20), time(11, 5), False, 'NONE'),
            (5, 'Period 4', time(11, 5), time(11, 50), False, 'NONE'),
            (6, 'Lunch Break', time(11, 50), time(13, 30), True, 'LUNCH'),
            (7, 'Period 5', time(13, 30), time(14, 15), False, 'NONE'),
            (8, 'Period 6', time(14, 15), time(15, 0), False, 'NONE'),
        ]
        created_periods = []
        for num, name, st, et, is_b, b_type in defaults:
            p, _ = Period.objects.get_or_create(
                academic_year=academic_year,
                period_number=num,
                defaults={
                    'name': name,
                    'start_time': st,
                    'end_time': et,
                    'is_break': is_b,
                    'break_type': b_type,
                    'is_active': True
                }
            )
            created_periods.append(p)
        return created_periods


class ConflictDetectionService:
    """
    Multi-dimensional timetable conflict engine.
    Detects:
    1. Teacher double-booking (same teacher, same day and period in two different classes).
    2. Class double-booking (same class, same day and period in two different subjects).
    3. Classroom double-booking (same physical room, same day and period for two classes).
    4. Invalid schedule conflicts (break periods, inactive teachers/classrooms, assignment mismatch).
    5. Suggests alternative free periods where practical.
    """

    @classmethod
    def check_entry_conflicts(cls, timetable, day_of_week, period, teacher, class_offering, classroom=None, subject=None, exclude_entry_id=None, include_suggestions=True):
        """
        Validates a proposed lesson assignment.
        Returns a dictionary:
        {
            'has_conflict': bool,
            'conflicts': list of conflict dicts,
            'suggestions': list of alternative period dicts
        }
        """
        conflicts = []
        academic_year = timetable.academic_year

        # 1. Break Period Check
        if period.is_break:
            conflicts.append({
                'type': 'BREAK_PERIOD',
                'severity': 'ERROR',
                'title': 'Scheduled During Break Slot',
                'message': f"Period '{period.name}' ({period.start_time.strftime('%H:%M')}-{period.end_time.strftime('%H:%M')}) is marked as a {period.get_break_type_display()}. Instructional lessons cannot be placed during breaks."
            })

        # 2. Inactive Teacher Check
        if teacher and not teacher.is_active:
            conflicts.append({
                'type': 'INACTIVE_TEACHER',
                'severity': 'ERROR',
                'title': 'Teacher Inactive / On Leave',
                'message': f"Teacher '{teacher.full_name}' ({teacher.employee_id}) has employment status '{teacher.get_employment_status_display()}' and cannot be scheduled."
            })

        # 3. Inactive Classroom Check
        if classroom and not classroom.is_active:
            conflicts.append({
                'type': 'INACTIVE_CLASSROOM',
                'severity': 'ERROR',
                'title': 'Classroom Deactivated',
                'message': f"Classroom '{classroom.name}' [{classroom.code}] is currently inactive."
            })

        # 4. Teacher-Subject-Class Assignment Validation (Warning if unassigned)
        if subject and teacher and class_offering:
            is_assigned = TeacherAssignment.objects.filter(
                teacher=teacher,
                subject=subject,
                class_offering=class_offering
            ).exists()
            if not is_assigned:
                conflicts.append({
                    'type': 'TEACHER_ASSIGNMENT_MISMATCH',
                    'severity': 'WARNING',
                    'title': 'Unassigned Subject Instructor',
                    'message': f"Teacher '{teacher.full_name}' does not have an active official TeacherAssignment for '{subject.name}' in {class_offering.display_name}."
                })

        # Base query for conflicting entries in the same academic year
        # Excludes archived timetables to detect clashes across all active and draft schedules
        relevant_entries = TimetableEntry.objects.filter(
            timetable__academic_year=academic_year,
            day_of_week=day_of_week,
            period=period
        ).exclude(timetable__status='ARCHIVED')

        if exclude_entry_id:
            relevant_entries = relevant_entries.exclude(pk=exclude_entry_id)

        # 5. Teacher Double-Booking Check
        teacher_clashes = relevant_entries.filter(teacher=teacher).select_related('class_offering', 'subject', 'timetable')
        for clash in teacher_clashes:
            conflicts.append({
                'type': 'TEACHER_CONFLICT',
                'severity': 'ERROR',
                'title': 'Teacher Double-Booking Conflict',
                'message': (
                    f"Teacher '{teacher.full_name}' is already assigned to {clash.class_offering.display_name} "
                    f"for '{clash.subject.name}' on {DAY_NAME_MAP.get(day_of_week)} during {period.name} "
                    f"in timetable '{clash.timetable.name}'."
                ),
                'conflicting_class': clash.class_offering.display_name,
                'conflicting_subject': clash.subject.name,
                'conflicting_timetable': clash.timetable.name,
            })

        # 6. Class Double-Booking Check
        class_clashes = relevant_entries.filter(class_offering=class_offering).select_related('subject', 'teacher', 'timetable')
        for clash in class_clashes:
            conflicts.append({
                'type': 'CLASS_CONFLICT',
                'severity': 'ERROR',
                'title': 'Class Double-Booking Conflict',
                'message': (
                    f"Class '{class_offering.display_name}' is already scheduled for '{clash.subject.name}' "
                    f"with {clash.teacher.full_name} on {DAY_NAME_MAP.get(day_of_week)} during {period.name}."
                ),
                'conflicting_subject': clash.subject.name,
                'conflicting_teacher': clash.teacher.full_name,
            })

        # 7. Classroom Double-Booking Check
        if classroom:
            room_clashes = relevant_entries.filter(classroom=classroom).select_related('class_offering', 'subject', 'teacher', 'timetable')
            for clash in room_clashes:
                conflicts.append({
                    'type': 'CLASSROOM_CONFLICT',
                    'severity': 'ERROR',
                    'title': 'Classroom Double-Booking Conflict',
                    'message': (
                        f"Classroom '{classroom.name}' [{classroom.code}] is already allocated to "
                        f"{clash.class_offering.display_name} ({clash.subject.name}) on {DAY_NAME_MAP.get(day_of_week)} during {period.name}."
                    ),
                    'conflicting_class': clash.class_offering.display_name,
                    'conflicting_subject': clash.subject.name,
                })

        # Suggestions: Find alternative available non-break periods on this day
        suggestions = []
        has_blocking_conflict = any(c['severity'] == 'ERROR' for c in conflicts)
        if has_blocking_conflict and include_suggestions:
            suggestions = cls.suggest_alternative_periods(
                timetable=timetable,
                day_of_week=day_of_week,
                teacher=teacher,
                class_offering=class_offering,
                classroom=classroom,
                exclude_entry_id=exclude_entry_id
            )

        return {
            'has_conflict': len(conflicts) > 0,
            'has_blocking_conflict': has_blocking_conflict,
            'conflicts': conflicts,
            'suggestions': suggestions
        }

    @classmethod
    def suggest_alternative_periods(cls, timetable, day_of_week, teacher, class_offering, classroom=None, exclude_entry_id=None):
        """
        Scans all periods on the given day and identifies non-break periods
        where teacher, class, and classroom are completely unbooked.
        """
        all_periods = TimetableConfigService.get_active_periods(timetable.academic_year)
        free_periods = []

        for p in all_periods:
            if p.is_break or not p.is_active:
                continue

            test_result = cls.check_entry_conflicts(
                timetable=timetable,
                day_of_week=day_of_week,
                period=p,
                teacher=teacher,
                class_offering=class_offering,
                classroom=classroom,
                exclude_entry_id=exclude_entry_id,
                include_suggestions=False
            )
            if not test_result['has_blocking_conflict']:
                free_periods.append({
                    'period_id': p.id,
                    'period_number': p.period_number,
                    'period_name': p.name,
                    'start_time': p.start_time.strftime('%H:%M'),
                    'end_time': p.end_time.strftime('%H:%M'),
                    'day_of_week': day_of_week,
                    'day_name': DAY_NAME_MAP.get(day_of_week),
                })
        return free_periods

    @classmethod
    def validate_entire_timetable(cls, timetable):
        """
        Runs comprehensive conflict detection over all entries in a timetable.
        Returns a list of conflict summaries.
        """
        all_conflicts = []
        entries = timetable.entries.select_related('period', 'subject', 'teacher', 'classroom', 'class_offering')

        for entry in entries:
            result = cls.check_entry_conflicts(
                timetable=timetable,
                day_of_week=entry.day_of_week,
                period=entry.period,
                teacher=entry.teacher,
                class_offering=entry.class_offering,
                classroom=entry.classroom,
                subject=entry.subject,
                exclude_entry_id=entry.id
            )
            if result['has_conflict']:
                for c in result['conflicts']:
                    c['entry_id'] = entry.id
                    c['day_of_week'] = entry.day_of_week
                    c['day_name'] = entry.day_name
                    c['period_name'] = entry.period.name
                    c['subject_name'] = entry.subject.name
                    c['teacher_name'] = entry.teacher.full_name
                    c['classroom_name'] = entry.classroom.name if entry.classroom else 'None'
                    all_conflicts.append(c)

        return all_conflicts


class TimetableService:
    """Manages timetable drafting, entry manipulation, and timetable cloning."""

    @classmethod
    def create_timetable(cls, academic_year, class_offering, name=None, valid_from=None, valid_until=None, user=None, request=None):
        """Creates a new draft timetable for a class offering."""
        if class_offering.academic_year_id != academic_year.id:
            raise ValidationError("Class offering must belong to the selected academic year.")

        # Determine next version
        latest_version = Timetable.objects.filter(
            class_offering=class_offering
        ).aggregate(max_v=models.Max('version'))['max_v'] or 0
        new_version = latest_version + 1

        if not name:
            name = f"{class_offering.display_name} Timetable (v{new_version})"

        with transaction.atomic():
            timetable = Timetable.objects.create(
                name=name,
                academic_year=academic_year,
                class_offering=class_offering,
                version=new_version,
                status='DRAFT',
                valid_from=valid_from,
                valid_until=valid_until,
                created_by=user
            )

            TimetableAuditHelper.log(
                request,
                'CREATE',
                'Timetable',
                timetable.id,
                {
                    'name': timetable.name,
                    'class': class_offering.display_name,
                    'academic_year': academic_year.code,
                    'version': new_version
                }
            )

        return timetable

    @classmethod
    def add_lesson_entry(cls, timetable, day_of_week, period, subject, teacher, classroom=None, notes='', enforce_no_conflicts=True, user=None, request=None):
        """
        Adds a single lesson entry to a timetable after running conflict validation.
        """
        if not timetable.is_editable:
            raise ValidationError(f"Cannot modify timetable in '{timetable.get_status_display()}' status.")

        # Conflict check
        conflict_res = ConflictDetectionService.check_entry_conflicts(
            timetable=timetable,
            day_of_week=day_of_week,
            period=period,
            teacher=teacher,
            class_offering=timetable.class_offering,
            classroom=classroom,
            subject=subject
        )

        if enforce_no_conflicts and conflict_res['has_blocking_conflict']:
            error_msgs = "; ".join([f"{c['title']}: {c['message']}" for c in conflict_res['conflicts'] if c['severity'] == 'ERROR'])
            raise ValidationError(f"Scheduling Conflict Detected: {error_msgs}")

        # Link teacher assignment if available
        assignment = TeacherAssignment.objects.filter(
            teacher=teacher,
            subject=subject,
            class_offering=timetable.class_offering
        ).first()

        # Link school day if configured
        school_day = SchoolDay.objects.filter(
            models.Q(academic_year=timetable.academic_year) | models.Q(academic_year__isnull=True),
            day_of_week=day_of_week,
            is_active=True
        ).first()

        entry, created = TimetableEntry.objects.update_or_create(
            timetable=timetable,
            day_of_week=day_of_week,
            period=period,
            defaults={
                'class_offering': timetable.class_offering,
                'subject': subject,
                'teacher': teacher,
                'teacher_assignment': assignment,
                'school_day': school_day,
                'classroom': classroom,
                'notes': notes,
            }
        )

        TimetableAuditHelper.log(
            request,
            'CREATE' if created else 'UPDATE',
            'TimetableEntry',
            entry.id,
            {
                'timetable': timetable.name,
                'day': entry.day_name,
                'period': period.name,
                'subject': subject.code,
                'teacher': teacher.full_name,
                'classroom': classroom.code if classroom else None
            }
        )
        return entry

    @classmethod
    def delete_lesson_entry(cls, entry_id, user=None, request=None):
        """Removes a lesson entry from an editable timetable."""
        entry = TimetableEntry.objects.select_related('timetable', 'subject', 'teacher', 'period').get(pk=entry_id)
        if not entry.timetable.is_editable:
            raise ValidationError(f"Cannot delete entries from timetable in '{entry.timetable.get_status_display()}' status.")

        log_details = {
            'timetable': entry.timetable.name,
            'day': entry.day_name,
            'period': entry.period.name,
            'subject': entry.subject.code,
            'teacher': entry.teacher.full_name,
        }
        entry_pk = entry.id
        entry.delete()

        TimetableAuditHelper.log(request, 'DELETE', 'TimetableEntry', entry_pk, log_details)
        return True

    @classmethod
    def copy_timetable(cls, source_timetable, target_class_offering, user=None, request=None):
        """
        Clones an existing timetable's layout and periods to another class offering.
        Validates teacher assignments and flags any unassigned subjects.
        """
        target_timetable = cls.create_timetable(
            academic_year=source_timetable.academic_year,
            class_offering=target_class_offering,
            name=f"{target_class_offering.display_name} Timetable (Cloned from {source_timetable.class_offering.display_name})",
            valid_from=source_timetable.valid_from,
            valid_until=source_timetable.valid_until,
            user=user,
            request=request
        )

        copied_count = 0
        conflicts_count = 0

        with transaction.atomic():
            for src_entry in source_timetable.entries.select_related('period', 'subject', 'teacher', 'classroom'):
                # Try to find a matching teacher assignment for the target class
                target_teacher = src_entry.teacher
                assignment = TeacherAssignment.objects.filter(
                    class_offering=target_class_offering,
                    subject=src_entry.subject
                ).first()
                if assignment:
                    target_teacher = assignment.teacher

                # Test for conflicts before creating
                conflict_check = ConflictDetectionService.check_entry_conflicts(
                    timetable=target_timetable,
                    day_of_week=src_entry.day_of_week,
                    period=src_entry.period,
                    teacher=target_teacher,
                    class_offering=target_class_offering,
                    classroom=src_entry.classroom,
                    subject=src_entry.subject
                )

                if not conflict_check['has_blocking_conflict']:
                    TimetableEntry.objects.create(
                        timetable=target_timetable,
                        class_offering=target_class_offering,
                        subject=src_entry.subject,
                        teacher=target_teacher,
                        teacher_assignment=assignment,
                        day_of_week=src_entry.day_of_week,
                        school_day=src_entry.school_day,
                        period=src_entry.period,
                        classroom=src_entry.classroom,
                        notes=src_entry.notes
                    )
                    copied_count += 1
                else:
                    conflicts_count += 1

        TimetableAuditHelper.log(
            request,
            'CLONE',
            'Timetable',
            target_timetable.id,
            {
                'source_timetable': source_timetable.name,
                'copied_entries': copied_count,
                'skipped_conflicts': conflicts_count
            }
        )

        return target_timetable, copied_count, conflicts_count


class TimetablePublicationService:
    """Manages multi-tier review, approval, publication, and immutable snapshotting."""

    @classmethod
    def submit_for_review(cls, timetable, user=None, request=None):
        """Submits draft timetable to Principal / Committee."""
        if timetable.status not in ['DRAFT', 'REJECTED']:
            raise ValidationError(f"Cannot submit timetable from status '{timetable.get_status_display()}'.")

        if timetable.entries.count() == 0:
            raise ValidationError("Cannot submit an empty timetable with zero scheduled lessons.")

        # Check for blocking conflicts
        conflicts = ConflictDetectionService.validate_entire_timetable(timetable)
        blocking = [c for c in conflicts if c['severity'] == 'ERROR']
        if blocking:
            raise ValidationError(f"Cannot submit timetable with {len(blocking)} active scheduling conflict(s). Please resolve them first.")

        timetable.status = 'SUBMITTED'
        timetable.save(update_fields=['status', 'updated_at'])

        TimetableAuditHelper.log(request, 'SUBMIT', 'Timetable', timetable.id, {'status': 'SUBMITTED'})
        return timetable

    @classmethod
    def review_timetable(cls, timetable, decision, reviewer_user, comments='', request=None):
        """Committee review decision: APPROVED or REJECTED."""
        if timetable.status != 'SUBMITTED':
            raise ValidationError("Only submitted timetables can be reviewed.")

        if decision not in ['APPROVED', 'REJECTED']:
            raise ValidationError("Invalid review decision.")

        with transaction.atomic():
            if decision == 'APPROVED':
                timetable.status = 'APPROVED'
                timetable.approved_by = reviewer_user
                timetable.approved_at = timezone.now()
            else:
                timetable.status = 'DRAFT'  # returned to draft for edits

            timetable.approval_remarks = comments
            timetable.save(update_fields=['status', 'approved_by', 'approved_at', 'approval_remarks', 'updated_at'])

            TimetableAuditHelper.log(
                request,
                'REVIEW',
                'Timetable',
                timetable.id,
                {'decision': decision, 'comments': comments}
            )
        return timetable

    @classmethod
    def publish_timetable(cls, timetable, user=None, request=None):
        """
        Publishes approved timetable, archives previous versions for the class,
        and saves an immutable JSON snapshot.
        """
        if timetable.status != 'APPROVED':
            raise ValidationError("Only approved timetables can be published.")

        # Final whole-school conflict verification
        conflicts = ConflictDetectionService.validate_entire_timetable(timetable)
        blocking = [c for c in conflicts if c['severity'] == 'ERROR']
        if blocking:
            raise ValidationError(f"Cannot publish: {len(blocking)} conflict(s) detected during pre-publication check.")

        with transaction.atomic():
            # Archive previous published timetables for this class
            Timetable.objects.filter(
                class_offering=timetable.class_offering,
                status='PUBLISHED'
            ).exclude(pk=timetable.pk).update(status='ARCHIVED')

            timetable.status = 'PUBLISHED'
            timetable.published_at = timezone.now()
            timetable.save(update_fields=['status', 'published_at', 'updated_at'])

            # Create immutable version snapshot
            snapshot_data = {
                'timetable_id': timetable.id,
                'class_offering': timetable.class_offering.display_name,
                'academic_year': timetable.academic_year.name,
                'version': timetable.version,
                'published_at': timetable.published_at.isoformat(),
                'entries': [
                    {
                        'day_of_week': e.day_of_week,
                        'day_name': e.day_name,
                        'period_number': e.period.period_number,
                        'period_name': e.period.name,
                        'start_time': e.period.start_time.strftime('%H:%M'),
                        'end_time': e.period.end_time.strftime('%H:%M'),
                        'subject_code': e.subject.code,
                        'subject_name': e.subject.name,
                        'teacher_id': e.teacher.employee_id,
                        'teacher_name': e.teacher.full_name,
                        'classroom_code': e.classroom.code if e.classroom else None,
                        'classroom_name': e.classroom.name if e.classroom else None,
                    }
                    for e in timetable.entries.select_related('period', 'subject', 'teacher', 'classroom')
                ]
            }

            TimetableVersion.objects.create(
                timetable=timetable,
                version_number=timetable.version,
                status='PUBLISHED',
                snapshot_data=snapshot_data,
                change_summary=f"Published Version {timetable.version}",
                created_by=user or timetable.approved_by
            )

            TimetableAuditHelper.log(
                request,
                'PUBLISH',
                'Timetable',
                timetable.id,
                {'version': timetable.version, 'total_lessons': timetable.entries.count()}
            )

        return timetable

    @classmethod
    def create_revised_version(cls, published_timetable, user=None, request=None):
        """
        Clones a published timetable into a new DRAFT revision (vN+1)
        without disrupting the live published timetable until newly approved.
        """
        if published_timetable.status != 'PUBLISHED':
            raise ValidationError("Revisions can only be initiated from a currently published timetable.")

        new_version_num = published_timetable.version + 1
        with transaction.atomic():
            new_timetable = Timetable.objects.create(
                name=f"{published_timetable.class_offering.display_name} Timetable (v{new_version_num})",
                academic_year=published_timetable.academic_year,
                class_offering=published_timetable.class_offering,
                version=new_version_num,
                status='DRAFT',
                valid_from=published_timetable.valid_from,
                valid_until=published_timetable.valid_until,
                created_by=user
            )

            for e in published_timetable.entries.all():
                TimetableEntry.objects.create(
                    timetable=new_timetable,
                    class_offering=e.class_offering,
                    subject=e.subject,
                    teacher=e.teacher,
                    teacher_assignment=e.teacher_assignment,
                    day_of_week=e.day_of_week,
                    school_day=e.school_day,
                    period=e.period,
                    classroom=e.classroom,
                    notes=e.notes
                )

            TimetableAuditHelper.log(
                request,
                'REVISE',
                'Timetable',
                new_timetable.id,
                {'from_version': published_timetable.version, 'new_version': new_version_num}
            )

        return new_timetable


class TimetableMatrixService:
    """Assembles weekly 2D timetable matrices for Class offerings and Teachers."""

    @classmethod
    def get_class_matrix(cls, timetable):
        """
        Returns structured grid matrix for class timetable:
        - working_days: list of active SchoolDay or synthetic day objects
        - periods: list of active Period objects
        - matrix: dict mapping (day_of_week, period_id) -> TimetableEntry
        """
        ay = timetable.academic_year
        working_days = TimetableConfigService.get_active_working_days(ay)
        periods = TimetableConfigService.get_active_periods(ay)

        entries = timetable.entries.select_related('subject', 'teacher', 'classroom', 'period').all()
        entry_map = {(e.day_of_week, e.period_id): e for e in entries}

        grid = []
        for p in periods:
            row = {'period': p, 'days': []}
            for d in working_days:
                e = entry_map.get((d.day_of_week, p.id))
                row['days'].append({
                    'day': d,
                    'entry': e
                })
            grid.append(row)

        return {
            'timetable': timetable,
            'working_days': working_days,
            'periods': periods,
            'grid': grid
        }

    @classmethod
    def get_teacher_matrix(cls, teacher, academic_year=None):
        """
        Returns structured weekly grid for a specific teacher across all their assigned classes.
        """
        if not academic_year:
            academic_year = AcademicYear.objects.filter(is_current=True).first()

        working_days = TimetableConfigService.get_active_working_days(academic_year)
        periods = TimetableConfigService.get_active_periods(academic_year)

        # Get entries from published timetables for this teacher
        entries = TimetableEntry.objects.filter(
            teacher=teacher,
            timetable__academic_year=academic_year,
            timetable__status='PUBLISHED'
        ).select_related('subject', 'class_offering__grade', 'class_offering__section', 'classroom', 'period')

        entry_map = {(e.day_of_week, e.period_id): e for e in entries}

        grid = []
        for p in periods:
            row = {'period': p, 'days': []}
            for d in working_days:
                e = entry_map.get((d.day_of_week, p.id))
                row['days'].append({
                    'day': d,
                    'entry': e
                })
            grid.append(row)

        return {
            'teacher': teacher,
            'academic_year': academic_year,
            'working_days': working_days,
            'periods': periods,
            'grid': grid,
            'total_lessons': entries.count()
        }


class TimetableReportService:
    """Generates official ReportLab PDFs and OpenPyXL Excel spreadsheets for timetables."""

    @classmethod
    def export_class_timetable_pdf(cls, timetable, filename="class_timetable.pdf"):
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=13,
            leading=16,
            alignment=1,
            textColor=colors.HexColor('#1E3A8A')
        )
        sub_style = ParagraphStyle(
            'SubStyle',
            parent=styles['Normal'],
            fontSize=8.5,
            leading=11,
            alignment=1,
            textColor=colors.HexColor('#475569')
        )
        cell_style = ParagraphStyle(
            'CellStyle',
            parent=styles['Normal'],
            fontSize=7,
            leading=9,
            alignment=1
        )

        elements.append(Paragraph("MAJANG SECONDARY SCHOOL - GAMBELLA REGION, ETHIOPIA", title_style))
        elements.append(Paragraph(f"Official Class Weekly Schedule: {timetable.class_offering.display_name}", title_style))
        elements.append(Paragraph(
            f"Academic Year: {timetable.academic_year.name} &bull; Version: v{timetable.version} &bull; Status: {timetable.get_status_display()}",
            sub_style
        ))
        elements.append(Spacer(1, 10))

        matrix = TimetableMatrixService.get_class_matrix(timetable)
        working_days = matrix['working_days']
        periods = matrix['periods']

        # Build table
        headers = ["Period / Time"] + [d.name for d in working_days]
        table_data = [headers]

        for row in matrix['grid']:
            p = row['period']
            time_str = f"{p.name}\n({p.start_time.strftime('%H:%M')}-{p.end_time.strftime('%H:%M')})"
            if p.is_break:
                time_str = f"{p.name} [{p.get_break_type_display()}]\n({p.start_time.strftime('%H:%M')}-{p.end_time.strftime('%H:%M')})"

            row_data = [time_str]
            for col in row['days']:
                e = col['entry']
                if p.is_break:
                    row_data.append(f"— {p.get_break_type_display()} —")
                elif e:
                    room = f" @ {e.classroom.code}" if e.classroom else ""
                    row_data.append(f"{e.subject.code}\n{e.teacher.first_name} {e.teacher.father_name[0]}.{room}")
                else:
                    row_data.append("—")
            table_data.append(row_data)

        num_cols = len(headers)
        col_width = (doc.width - 90) / (num_cols - 1) if num_cols > 1 else 100
        col_widths = [90] + [col_width] * (num_cols - 1)

        t = Table(table_data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ]))
        elements.append(t)

        doc.build(elements)
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @classmethod
    def export_class_timetable_excel(cls, timetable, filename="class_timetable.xlsx"):
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Class Timetable"
        ws.views.sheetView[0].showGridLines = True

        matrix = TimetableMatrixService.get_class_matrix(timetable)
        working_days = matrix['working_days']

        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(working_days) + 1)
        ws["A1"] = f"MAJANG SECONDARY SCHOOL - {timetable.class_offering.display_name.upper()} TIMETABLE"
        ws["A1"].font = Font(name="Calibri", size=13, bold=True, color="1E3A8A")
        ws["A1"].alignment = Alignment(horizontal="center")

        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(working_days) + 1)
        ws["A2"] = f"Academic Year: {timetable.academic_year.name} | Version: v{timetable.version} | Status: {timetable.get_status_display()}"
        ws["A2"].font = Font(name="Calibri", size=10, italic=True)
        ws["A2"].alignment = Alignment(horizontal="center")

        headers = ["Period / Time"] + [d.name for d in working_days]
        ws.append([])
        ws.append(headers)

        header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        thin_border = Border(
            left=Side(style='thin', color='CBD5E1'),
            right=Side(style='thin', color='CBD5E1'),
            top=Side(style='thin', color='CBD5E1'),
            bottom=Side(style='thin', color='CBD5E1')
        )

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=4, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")

        for row in matrix['grid']:
            p = row['period']
            time_str = f"{p.name} ({p.start_time.strftime('%H:%M')}-{p.end_time.strftime('%H:%M')})"
            row_vals = [time_str]
            for col in row['days']:
                e = col['entry']
                if p.is_break:
                    row_vals.append(f"[{p.get_break_type_display()}]")
                elif e:
                    room = f" @ {e.classroom.code}" if e.classroom else ""
                    row_vals.append(f"{e.subject.code} - {e.teacher.first_name}{room}")
                else:
                    row_vals.append("—")
            ws.append(row_vals)
            curr_row = ws.max_row
            for col_idx in range(1, len(headers) + 1):
                c = ws.cell(row=curr_row, column=col_idx)
                c.border = thin_border
                c.alignment = Alignment(horizontal="center", vertical="center")
                if p.is_break:
                    c.fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @classmethod
    def export_teacher_timetable_pdf(cls, teacher, academic_year=None, filename="teacher_timetable.pdf"):
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
        elements = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'TitleStyle', parent=styles['Heading1'],
            fontSize=13, leading=16, alignment=1, textColor=colors.HexColor('#1E3A8A')
        )
        sub_style = ParagraphStyle(
            'SubStyle', parent=styles['Normal'],
            fontSize=8.5, leading=11, alignment=1, textColor=colors.HexColor('#475569')
        )

        elements.append(Paragraph("MAJANG SECONDARY SCHOOL - GAMBELLA REGION, ETHIOPIA", title_style))
        elements.append(Paragraph(f"Official Teacher Weekly Schedule: {teacher.full_name} ({teacher.employee_id})", title_style))
        elements.append(Paragraph(
            f"Specialization: {teacher.specialization} &bull; Academic Year: {academic_year.name if academic_year else 'Current'}",
            sub_style
        ))
        elements.append(Spacer(1, 10))

        matrix = TimetableMatrixService.get_teacher_matrix(teacher, academic_year)
        working_days = matrix['working_days']
        periods = matrix['periods']

        headers = ["Period / Time"] + [d.name for d in working_days]
        table_data = [headers]

        for row in matrix['grid']:
            p = row['period']
            time_str = f"{p.name}\n({p.start_time.strftime('%H:%M')}-{p.end_time.strftime('%H:%M')})"
            row_data = [time_str]
            for col in row['days']:
                e = col['entry']
                if p.is_break:
                    row_data.append(f"— {p.get_break_type_display()} —")
                elif e:
                    room = f" @ {e.classroom.code}" if e.classroom else ""
                    row_data.append(f"{e.class_offering.grade.name}-{e.class_offering.section.name}\n{e.subject.code}{room}")
                else:
                    row_data.append("—")
            table_data.append(row_data)

        num_cols = len(headers)
        col_width = (doc.width - 90) / (num_cols - 1) if num_cols > 1 else 100
        col_widths = [90] + [col_width] * (num_cols - 1)

        t = Table(table_data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('FONTSIZE', (0, 1), (-1, -1), 7),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ]))
        elements.append(t)

        doc.build(elements)
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @classmethod
    def export_teacher_timetable_excel(cls, teacher, academic_year=None, filename="teacher_timetable.xlsx"):
        import openpyxl
        from openpyxl.styles import Font, Alignment, PatternFill, Border, Side

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Teacher Timetable"
        ws.views.sheetView[0].showGridLines = True

        matrix = TimetableMatrixService.get_teacher_matrix(teacher, academic_year)
        working_days = matrix['working_days']

        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(working_days) + 1)
        ws["A1"] = f"MAJANG SECONDARY SCHOOL - TEACHER SCHEDULE: {teacher.full_name.upper()}"
        ws["A1"].font = Font(name="Calibri", size=13, bold=True, color="1E3A8A")
        ws["A1"].alignment = Alignment(horizontal="center")

        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(working_days) + 1)
        ws["A2"] = f"Employee ID: {teacher.employee_id} | Specialization: {teacher.specialization} | Academic Year: {academic_year.name if academic_year else 'Current'}"
        ws["A2"].font = Font(name="Calibri", size=10, italic=True)
        ws["A2"].alignment = Alignment(horizontal="center")

        headers = ["Period / Time"] + [d.name for d in working_days]
        ws.append([])
        ws.append(headers)

        header_font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        thin_border = Border(
            left=Side(style='thin', color='CBD5E1'),
            right=Side(style='thin', color='CBD5E1'),
            top=Side(style='thin', color='CBD5E1'),
            bottom=Side(style='thin', color='CBD5E1')
        )

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=4, column=col_idx)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")

        for row in matrix['grid']:
            p = row['period']
            time_str = f"{p.name} ({p.start_time.strftime('%H:%M')}-{p.end_time.strftime('%H:%M')})"
            row_vals = [time_str]
            for col in row['days']:
                e = col['entry']
                if p.is_break:
                    row_vals.append(f"[{p.get_break_type_display()}]")
                elif e:
                    room = f" @ {e.classroom.code}" if e.classroom else ""
                    row_vals.append(f"{e.class_offering.grade.name}-{e.class_offering.section.name} ({e.subject.code}){room}")
                else:
                    row_vals.append("—")
            ws.append(row_vals)
            curr_row = ws.max_row
            for col_idx in range(1, len(headers) + 1):
                c = ws.cell(row=curr_row, column=col_idx)
                c.border = thin_border
                c.alignment = Alignment(horizontal="center", vertical="center")
                if p.is_break:
                    c.fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")

        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = openpyxl.utils.get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 14)

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        response = HttpResponse(buffer.getvalue(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
