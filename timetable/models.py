"""
Models for Timetable and Class Scheduling Management System.
Supports configurable periods, working days, classrooms, conflict-checked weekly schedules,
and multi-tier publication workflows with immutable version archiving.
"""

from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone

from academics.models import AcademicYear, Grade, Section, Stream, Subject, ClassOffering
from teachers.models import Teacher, TeacherAssignment


DAY_OF_WEEK_CHOICES = [
    (1, 'Monday'),
    (2, 'Tuesday'),
    (3, 'Wednesday'),
    (4, 'Thursday'),
    (5, 'Friday'),
    (6, 'Saturday'),
    (7, 'Sunday'),
]

DAY_NAME_MAP = dict(DAY_OF_WEEK_CHOICES)


class Classroom(models.Model):
    """
    Physical or specialized learning space (regular classrooms, science labs, library).
    Supports optional capacity tracking and active/inactive status.
    """
    ROOM_TYPE_CHOICES = [
        ('REGULAR', 'Regular Classroom'),
        ('LAB_SCIENCE', 'Science Laboratory'),
        ('LAB_COMPUTER', 'Computer Laboratory'),
        ('LIBRARY', 'Library / Resource Center'),
        ('HALL', 'Multi-purpose Hall / Auditorium'),
        ('WORKSHOP', 'Technical / Vocational Workshop'),
    ]

    name = models.CharField(max_length=60, unique=True, help_text="e.g. Block A - Room 101, Chemistry Lab")
    code = models.CharField(max_length=25, unique=True, help_text="Short room code, e.g. R-101, LAB-CHEM")
    building = models.CharField(max_length=100, blank=True, help_text="Building or campus section, e.g. Block A")
    room_type = models.CharField(max_length=30, choices=ROOM_TYPE_CHOICES, default='REGULAR')
    capacity = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Maximum student seating capacity")
    is_active = models.BooleanField(default=True, help_text="Deactivated rooms cannot be assigned to lessons.")
    description = models.TextField(blank=True, help_text="Facilities, equipment, or access notes")

    class Meta:
        verbose_name = 'Classroom'
        verbose_name_plural = 'Classrooms'
        ordering = ['building', 'name']

    def __str__(self):
        cap_str = f" ({self.capacity} seats)" if self.capacity else ""
        return f"{self.name} [{self.code}]{cap_str}"


class SchoolDay(models.Model):
    """
    Configurable school working day. Allows administrators to configure working days
    (e.g., Monday through Friday or Saturday) per academic year or as global defaults.
    """
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='school_working_days',
        help_text="Optional academic year binding; leave empty for global default."
    )
    day_of_week = models.PositiveSmallIntegerField(choices=DAY_OF_WEEK_CHOICES)
    name = models.CharField(max_length=30, help_text="e.g. Monday")
    short_name = models.CharField(max_length=10, help_text="e.g. Mon")
    is_active = models.BooleanField(default=True, help_text="Designates whether lessons are conducted on this day.")
    order = models.PositiveSmallIntegerField(default=1, help_text="Ordering in timetable grid (1=first day)")

    class Meta:
        verbose_name = 'School Working Day'
        verbose_name_plural = 'School Working Days'
        ordering = ['order', 'day_of_week']
        constraints = [
            models.UniqueConstraint(
                fields=['academic_year', 'day_of_week'],
                name='unique_working_day_per_academic_year'
            )
        ]

    def __str__(self):
        ay_str = f" ({self.academic_year.code})" if self.academic_year else ""
        return f"{self.name}{ay_str}"


class Period(models.Model):
    """
    Configurable period slot within the daily school schedule.
    Supports lessons, morning assembly, short recess, and lunch breaks.
    """
    BREAK_TYPE_CHOICES = [
        ('NONE', 'Instructional Lesson Period'),
        ('SHORT_BREAK', 'Short Break / Recess'),
        ('LUNCH', 'Lunch Break'),
        ('ASSEMBLY', 'Morning Assembly'),
    ]

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='schedule_periods',
        help_text="Optional academic year binding; leave empty for global default."
    )
    period_number = models.PositiveSmallIntegerField(help_text="Sequence index, e.g. 1, 2, 3...")
    name = models.CharField(max_length=50, help_text="e.g. Period 1, Morning Break, Period 4, Lunch")
    start_time = models.TimeField(help_text="Period start time (HH:MM)")
    end_time = models.TimeField(help_text="Period end time (HH:MM)")
    is_break = models.BooleanField(default=False, help_text="True if this slot is a break/recess or assembly.")
    break_type = models.CharField(max_length=30, choices=BREAK_TYPE_CHOICES, default='NONE')
    is_active = models.BooleanField(default=True, help_text="Inactive periods cannot receive lesson assignments.")

    class Meta:
        verbose_name = 'Schedule Period'
        verbose_name_plural = 'Schedule Periods'
        ordering = ['period_number', 'start_time']
        constraints = [
            models.UniqueConstraint(
                fields=['academic_year', 'period_number'],
                name='unique_period_number_per_academic_year'
            )
        ]

    def __str__(self):
        break_tag = f" [{self.get_break_type_display()}]" if self.is_break else ""
        time_str = f"{self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"
        return f"{self.name} ({time_str}){break_tag}"

    @property
    def duration_minutes(self):
        """Calculates period duration in minutes."""
        from datetime import datetime, date
        dt_start = datetime.combine(date.today(), self.start_time)
        dt_end = datetime.combine(date.today(), self.end_time)
        delta = dt_end - dt_start
        return int(delta.total_seconds() / 60)

    def clean(self):
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({'end_time': "Period end time must be strictly after start time."})
        if self.is_break and self.break_type == 'NONE':
            self.break_type = 'SHORT_BREAK'
        elif not self.is_break and self.break_type != 'NONE':
            self.is_break = True


class Timetable(models.Model):
    """
    Weekly master schedule container for a specific ClassOffering and AcademicYear.
    Enforces revision versioning and publication workflow states:
    DRAFT -> SUBMITTED -> APPROVED -> PUBLISHED -> ARCHIVED.
    """
    STATUS_CHOICES = [
        ('DRAFT', 'Draft / In Preparation'),
        ('SUBMITTED', 'Submitted for Review'),
        ('APPROVED', 'Approved by Committee'),
        ('PUBLISHED', 'Published / Active'),
        ('ARCHIVED', 'Archived / Superseded'),
    ]

    name = models.CharField(max_length=150, help_text="e.g. Grade 10-A Weekly Timetable (2026/2027)")
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name='timetables'
    )
    class_offering = models.ForeignKey(
        ClassOffering,
        on_delete=models.CASCADE,
        related_name='timetables'
    )
    version = models.PositiveIntegerField(default=1, help_text="Revision version number (1, 2, 3...)")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    valid_from = models.DateField(null=True, blank=True, help_text="Effective start date of this timetable")
    valid_until = models.DateField(null=True, blank=True, help_text="Effective end date of this timetable")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_timetables'
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='approved_timetables'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    approval_remarks = models.TextField(blank=True, help_text="Feedback or approval notes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Timetable'
        verbose_name_plural = 'Timetables'
        ordering = ['-academic_year__start_date', 'class_offering__grade__level', 'class_offering__section__name', '-version']
        constraints = [
            models.UniqueConstraint(
                fields=['class_offering', 'version'],
                name='unique_timetable_version_per_class'
            )
        ]

    def __str__(self):
        return f"{self.class_offering.display_name} - v{self.version} ({self.get_status_display()})"

    @property
    def is_published(self):
        return self.status == 'PUBLISHED'

    @property
    def is_editable(self):
        return self.status in ['DRAFT', 'SUBMITTED']

    @property
    def total_scheduled_lessons(self):
        return self.entries.count()

    def clean(self):
        if self.class_offering_id and self.academic_year_id:
            if self.class_offering.academic_year_id != self.academic_year_id:
                raise ValidationError("Timetable academic year must match the class offering's academic year.")
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValidationError({'valid_until': "Valid until date must be after valid from date."})


class TimetableEntry(models.Model):
    """
    Scheduled lesson slot mapping a ClassOffering, Subject, Teacher, Day, and Period,
    with an optional Classroom assignment.
    """
    timetable = models.ForeignKey(
        Timetable,
        on_delete=models.CASCADE,
        related_name='entries'
    )
    class_offering = models.ForeignKey(
        ClassOffering,
        on_delete=models.CASCADE,
        related_name='timetable_entries'
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name='timetable_entries'
    )
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.CASCADE,
        related_name='timetable_entries'
    )
    teacher_assignment = models.ForeignKey(
        TeacherAssignment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='timetable_entries',
        help_text="Verified teacher-subject-class qualification link."
    )
    day_of_week = models.PositiveSmallIntegerField(
        choices=DAY_OF_WEEK_CHOICES,
        help_text="1=Monday ... 7=Sunday"
    )
    school_day = models.ForeignKey(
        SchoolDay,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='entries'
    )
    period = models.ForeignKey(
        Period,
        on_delete=models.CASCADE,
        related_name='entries'
    )
    classroom = models.ForeignKey(
        Classroom,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='timetable_entries',
        help_text="Optional physical room or laboratory allocation."
    )
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = 'Timetable Lesson Entry'
        verbose_name_plural = 'Timetable Lesson Entries'
        ordering = ['day_of_week', 'period__period_number']
        constraints = [
            models.UniqueConstraint(
                fields=['timetable', 'day_of_week', 'period'],
                name='unique_lesson_per_timetable_slot'
            )
        ]

    def __str__(self):
        day_name = DAY_NAME_MAP.get(self.day_of_week, f"Day {self.day_of_week}")
        room_str = f" @ {self.classroom.code}" if self.classroom else ""
        return f"{day_name} P{self.period.period_number}: {self.subject.code} ({self.teacher.first_name}){room_str}"

    @property
    def day_name(self):
        return DAY_NAME_MAP.get(self.day_of_week, f"Day {self.day_of_week}")

    def clean(self):
        # 1. Validate period is not a break
        if self.period and self.period.is_break:
            raise ValidationError({'period': f"Cannot schedule instructional lesson during break: '{self.period.name}'."})

        # 2. Synchronize class offering from timetable
        if self.timetable and not self.class_offering_id:
            self.class_offering = self.timetable.class_offering
        elif self.timetable and self.class_offering_id != self.timetable.class_offering_id:
            raise ValidationError("Timetable entry class offering must match the parent timetable.")

        # 3. Validate teacher is active
        if self.teacher and not self.teacher.is_active:
            raise ValidationError({'teacher': f"Teacher '{self.teacher.full_name}' is inactive and cannot be scheduled."})

        # 4. Validate classroom is active
        if self.classroom and not self.classroom.is_active:
            raise ValidationError({'classroom': f"Classroom '{self.classroom.name}' is inactive and cannot be allocated."})

    def save(self, *args, **kwargs):
        if self.timetable and not self.class_offering_id:
            self.class_offering = self.timetable.class_offering
        self.clean()
        super().save(*args, **kwargs)


class TimetableVersion(models.Model):
    """
    Immutable audit snapshot of a timetable when submitted, approved, published, or revised.
    Preserves exact historical lesson configurations.
    """
    timetable = models.ForeignKey(
        Timetable,
        on_delete=models.CASCADE,
        related_name='versions'
    )
    version_number = models.PositiveIntegerField()
    status = models.CharField(max_length=20)
    snapshot_data = models.JSONField(default=dict, help_text="Full JSON state of entries and metadata")
    change_summary = models.TextField(blank=True, help_text="Description of changes made in this revision")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Timetable Version Snapshot'
        verbose_name_plural = 'Timetable Version Snapshots'
        ordering = ['-version_number', '-created_at']

    def __str__(self):
        return f"{self.timetable.name} - Version {self.version_number} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"
