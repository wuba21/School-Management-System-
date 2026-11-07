"""
Dashboard Analytics Service Engine for SSMS.

Computes real-time, aggregated statistics from the relational database:
  - KPI overview metrics (Students, Teachers, Academic Years, Classes, Attendance, Pending Results)
  - Student demographic distributions (Grade, Section, Gender, Stream)
  - Attendance metrics (Present, Absent, Late, Attendance Rate, Trend)
  - Academic metrics (Examinations, Subject Averages, Class Averages)
  - Role-filtered data (Teacher, Registrar, Admin, Principal)
  - Recent operational activities
"""

from decimal import Decimal
from django.db.models import Count, Avg, Q
from django.utils import timezone
from datetime import timedelta

from students.models import Student, StudentEnrollment
from teachers.models import Teacher, TeacherAssignment
from academics.models import AcademicYear, Grade, Section, ClassOffering, Subject
from attendance.models import AttendanceSession, AttendanceRecord
from examinations.models import Examination, ExamSubject
from results.models import Mark
from accounts.models import User
from core.models import AuditLog


class DashboardService:
    """
    Encapsulates all database aggregation and query logic for the school dashboard.
    Designed for high performance using Django ORM aggregation (preventing N+1 queries).
    """

    @staticmethod
    def get_overview_kpis(user):
        """
        Calculates top-level KPI metrics across the institution.
        Safely handles empty database states by defaulting to zero.
        """
        today = timezone.localdate()

        # 1. Total Active Students
        total_students = Student.objects.filter(status='ACTIVE').count()

        # 2. Total Active Teachers
        total_teachers = Teacher.objects.filter(is_active=True).count()

        # 3. Active Academic Year
        current_year = AcademicYear.objects.filter(is_current=True).first()
        if not current_year:
            current_year = AcademicYear.objects.filter(is_closed=False).order_by('-start_date').first()
        if not current_year:
            current_year = AcademicYear.objects.order_by('-start_date').first()

        total_active_years = AcademicYear.objects.filter(is_closed=False).count()

        # 4. Total Active Classes
        if current_year:
            total_active_classes = ClassOffering.objects.filter(academic_year=current_year).count()
        else:
            total_active_classes = ClassOffering.objects.count()

        # 5. Today's Attendance Overview
        today_sessions = AttendanceSession.objects.filter(date=today)
        today_records = AttendanceRecord.objects.filter(attendance_session__in=today_sessions)
        
        today_total = today_records.count()
        today_present = today_records.filter(status='PRESENT').count()
        today_late = today_records.filter(status='LATE').count()
        today_absent = today_records.filter(status='ABSENT').count()

        if today_total > 0:
            attendance_rate = round(((today_present + today_late) / today_total) * 100, 1)
            attendance_status_label = f"{today_present + today_late} of {today_total} students"
        else:
            # Check last 7 days average if no session recorded today
            recent_records = AttendanceRecord.objects.filter(
                attendance_session__date__gte=today - timedelta(days=7)
            )
            recent_total = recent_records.count()
            if recent_total > 0:
                recent_attended = recent_records.filter(status__in=['PRESENT', 'LATE']).count()
                attendance_rate = round((recent_attended / recent_total) * 100, 1)
                attendance_status_label = "7-day average (no session today)"
            else:
                attendance_rate = 0.0
                attendance_status_label = "No attendance recorded today"

        # 6. Pending Examination Results
        active_exams = Examination.objects.filter(is_active=True, is_locked=False)
        pending_exams_count = active_exams.count()

        # Total marks recorded so far across all examination cycles
        total_marks_entered = Mark.objects.count()

        return {
            'total_students': total_students,
            'total_teachers': total_teachers,
            'current_year': current_year,
            'total_active_years': total_active_years,
            'total_active_classes': total_active_classes,
            'attendance_rate': attendance_rate,
            'today_total': today_total,
            'today_present': today_present,
            'today_late': today_late,
            'today_absent': today_absent,
            'attendance_status_label': attendance_status_label,
            'pending_exams_count': pending_exams_count,
            'total_marks_entered': total_marks_entered,
        }

    @staticmethod
    def get_student_analytics():
        """
        Computes student demographic distributions for Chart.js:
          - By Grade level
          - By Section
          - By Gender
          - By Stream
        """
        # 1. Students by Grade Level via current active student_enrollments
        grade_data = (
            Grade.objects.all()
            .annotate(
                student_count=Count('class_offerings__student_enrollments', filter=Q(class_offerings__student_enrollments__status='ACTIVE'))
            )
            .order_by('level')
        )
        grade_labels = [g.name for g in grade_data]
        grade_counts = [g.student_count for g in grade_data]

        # 2. Gender distribution
        gender_data = (
            Student.objects.filter(status='ACTIVE')
            .values('gender')
            .annotate(count=Count('id'))
            .order_by('gender')
        )
        gender_map = {'M': 0, 'F': 0}
        for item in gender_data:
            gender_map[item['gender']] = item['count']

        # 3. Students by Stream (Natural Science vs Social Science vs General)
        stream_data = (
            ClassOffering.objects.values('stream__name')
            .annotate(count=Count('student_enrollments', filter=Q(student_enrollments__status='ACTIVE')))
            .order_by('-count')
        )
        stream_labels = [s['stream__name'] or 'General Secondary' for s in stream_data if s['stream__name']]
        stream_counts = [s['count'] for s in stream_data if s['stream__name']]

        return {
            'grade_labels': grade_labels,
            'grade_counts': grade_counts,
            'gender_male': gender_map.get('M', 0),
            'gender_female': gender_map.get('F', 0),
            'stream_labels': stream_labels,
            'stream_counts': stream_counts,
            'has_student_data': sum(grade_counts) > 0 or (gender_map.get('M', 0) + gender_map.get('F', 0)) > 0,
        }

    @staticmethod
    def get_attendance_analytics():
        """
        Computes detailed attendance trends across the last 7 recorded dates.
        """
        recent_dates = (
            AttendanceSession.objects.values_list('date', flat=True)
            .distinct()
            .order_by('-date')[:7]
        )
        chronological_dates = sorted(list(recent_dates))

        trend_labels = []
        trend_rates = []

        for d in chronological_dates:
            records = AttendanceRecord.objects.filter(attendance_session__date=d)
            tot = records.count()
            if tot > 0:
                att = records.filter(status__in=['PRESENT', 'LATE']).count()
                rate = round((att / tot) * 100, 1)
            else:
                rate = 0.0
            trend_labels.append(d.strftime('%a (%d %b)'))
            trend_rates.append(rate)

        all_records = AttendanceRecord.objects.all()
        total_all = all_records.count()
        total_present = all_records.filter(status='PRESENT').count()
        total_absent = all_records.filter(status='ABSENT').count()
        total_late = all_records.filter(status='LATE').count()
        total_excused = all_records.filter(status='EXCUSED').count()

        overall_percentage = (
            round(((total_present + total_late) / total_all) * 100, 1)
            if total_all > 0 else 0.0
        )

        return {
            'trend_labels': trend_labels,
            'trend_rates': trend_rates,
            'total_present': total_present,
            'total_absent': total_absent,
            'total_late': total_late,
            'total_excused': total_excused,
            'overall_percentage': overall_percentage,
            'has_attendance_data': total_all > 0,
        }

    @staticmethod
    def get_academic_analytics():
        """
        Computes exam summaries and average mark performance by subject.
        """
        examinations = Examination.objects.select_related('academic_year').order_by('-start_date')[:5]

        subject_performance = (
            Mark.objects.values('exam_subject__subject__name')
            .annotate(
                avg_score=Avg('marks_obtained'),
                marks_count=Count('id')
            )
            .order_by('-avg_score')[:8]
        )

        subject_names = [s['exam_subject__subject__name'] for s in subject_performance]
        subject_averages = [round(float(s['avg_score']), 1) for s in subject_performance]

        class_offerings = (
            ClassOffering.objects.select_related('grade', 'section', 'stream')
            .annotate(enrolled_count=Count('student_enrollments'))
            .order_by('grade__level', 'section__name')
        )

        return {
            'examinations': examinations,
            'subject_names': subject_names,
            'subject_averages': subject_averages,
            'class_offerings': class_offerings[:10],
            'has_academic_data': len(examinations) > 0 or len(subject_names) > 0,
        }

    @staticmethod
    def get_role_specific_context(user):
        """
        Tailors context data according to the logged-in user's role:
          - Teacher: Assigned classes, subjects, teacher's student count
          - Registrar: Unassigned students, pending enrollments
          - Administrator: User stats by role, audit log counts
          - Principal: School-wide executive metrics
        """
        role_code = user.role.code if user.role else ('ADMIN' if user.is_superuser else None)

        context = {
            'role_code': role_code,
            'is_principal': role_code == 'PRINCIPAL',
            'is_registrar': role_code == 'REGISTRAR',
            'is_teacher': role_code == 'TEACHER',
            'is_admin': role_code == 'ADMIN' or user.is_superuser,
        }

        if role_code == 'TEACHER':
            teacher_obj = Teacher.objects.filter(user=user).first()
            if teacher_obj:
                assignments = TeacherAssignment.objects.filter(teacher=teacher_obj).select_related(
                    'class_offering__grade', 'class_offering__section', 'subject'
                )
                assigned_classes = assignments.values('class_offering').distinct()
                assigned_students_count = StudentEnrollment.objects.filter(
                    class_offering__in=assigned_classes, status='ACTIVE'
                ).count()
                recent_teacher_sessions = AttendanceSession.objects.filter(
                    recorded_by=teacher_obj
                ).select_related('class_offering__grade', 'class_offering__section').order_by('-date')[:5]

                context['teacher_profile'] = teacher_obj
                context['teacher_assignments'] = assignments
                context['teacher_classes_count'] = assigned_classes.count()
                context['teacher_subjects_count'] = assignments.values('subject').distinct().count()
                context['teacher_students_count'] = assigned_students_count
                context['recent_teacher_sessions'] = recent_teacher_sessions
            else:
                context['teacher_profile'] = None
                context['teacher_assignments'] = []
                context['teacher_classes_count'] = 0
                context['teacher_subjects_count'] = 0
                context['teacher_students_count'] = 0
                context['recent_teacher_sessions'] = []

        elif role_code == 'REGISTRAR':
            # Unassigned students (students without active enrollment in any class)
            enrolled_student_ids = StudentEnrollment.objects.filter(
                status='ACTIVE'
            ).values_list('student_id', flat=True)
            unassigned_students_count = Student.objects.filter(
                status='ACTIVE'
            ).exclude(id__in=enrolled_student_ids).count()

            context['unassigned_students_count'] = unassigned_students_count
            context['recent_enrollments'] = StudentEnrollment.objects.select_related(
                'student', 'class_offering__grade', 'class_offering__section'
            ).order_by('-enrollment_date')[:5]

        elif role_code in ('ADMIN', None) and (user.is_superuser or role_code == 'ADMIN'):
            user_counts_by_role = User.objects.values('role__name').annotate(count=Count('id'))
            active_users_count = User.objects.filter(is_active=True).count()
            inactive_users_count = User.objects.filter(is_active=False).count()
            audit_logs_count = AuditLog.objects.count()

            context['user_counts_by_role'] = user_counts_by_role
            context['active_users_count'] = active_users_count
            context['inactive_users_count'] = inactive_users_count
            context['audit_logs_count'] = audit_logs_count

        return context

    @staticmethod
    def get_recent_activities(user):
        """
        Returns recent system activity logs filtered appropriately for the user role.
        """
        role_code = user.role.code if user.role else ('ADMIN' if user.is_superuser else None)

        if role_code in ('ADMIN', 'PRINCIPAL') or user.is_superuser:
            return AuditLog.objects.select_related('actor').order_by('-timestamp')[:8]
        elif role_code == 'REGISTRAR':
            return AuditLog.objects.filter(
                entity_name__in=['Student', 'StudentEnrollment', 'Examination', 'Mark']
            ).select_related('actor').order_by('-timestamp')[:8]
        elif role_code == 'TEACHER':
            return AuditLog.objects.filter(
                actor=user
            ).order_by('-timestamp')[:6]
        else:
            return AuditLog.objects.none()
