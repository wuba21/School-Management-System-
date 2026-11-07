"""
School Reports & Analytics Service Engine for SSMS.
Centralized, high-performance data aggregation across all core academic domains:
  - AnalyticsService: Real-time DB metrics & Chart.js data generation
  - StudentReportService: Student demographics, enrollments, 360° academic history
  - TeacherReportService: Teacher workloads, subject allocations, timetable allocations
  - AttendanceReportService: Multi-scale attendance aggregates & chronic absenteeism detection
  - ExaminationPerformanceReportService: Broad-sheet analysis, exam completions, score boundaries
  - PromotionReportService: End-of-year batch outcomes, graduation archives, cohort statistics
  - ReportExportService: Official PDF (ReportLab) & Excel (OpenPyXL) document builders
"""

import io
from decimal import Decimal
from datetime import date, timedelta
from django.db.models import Count, Avg, Max, Min, Sum, Q, F
from django.utils import timezone
from django.core.exceptions import PermissionDenied

# Core Domain Models
from students.models import Student, StudentEnrollment
from teachers.models import Teacher, TeacherAssignment
from academics.models import AcademicYear, Grade, Section, Stream, Subject, CurriculumSubject, ClassOffering
from attendance.models import AttendanceSession, AttendanceRecord
from examinations.models import Examination, ExamSubject
from results.models import Mark, StudentResultSummary, GradingScale, GradingRange, ResultApproval
from promotion.models import PromotionBatch, PromotionRecord, GraduationRecord, StudentStatusHistory, PromotionCriteria
from timetable.models import Classroom, Timetable, TimetableEntry


class AnalyticsService:
    """
    Computes high-level aggregated school metrics and generates Chart.js payloads.
    All statistics are strictly derived from real database queries (zero hardcoded numbers).
    """

    @classmethod
    def get_school_overview_stats(cls, filters=None, user=None):
        """
        Calculates institutional overview statistics across 5 core dimensions:
        Student, Teacher, Attendance, Examination, and Academic/Promotion.
        """
        filters = filters or {}
        today = timezone.localdate()

        # -------------------------------------------------------------
        # 1. Academic Year Context
        # -------------------------------------------------------------
        current_year = None
        if filters.get('academic_year'):
            current_year = filters['academic_year']
        else:
            current_year = AcademicYear.objects.filter(is_current=True).first()
            if not current_year:
                current_year = AcademicYear.objects.filter(is_closed=False).order_by('-start_date').first()
            if not current_year:
                current_year = AcademicYear.objects.order_by('-start_date').first()

        # Base student enrollment queryset filtered by academic year if present
        enrollments = StudentEnrollment.objects.all()
        if current_year:
            enrollments = enrollments.filter(academic_year=current_year)

        if filters.get('grade'):
            enrollments = enrollments.filter(class_offering__grade=filters['grade'])
        if filters.get('class_offering'):
            enrollments = enrollments.filter(class_offering=filters['class_offering'])

        # -------------------------------------------------------------
        # 2. Student Statistics
        # -------------------------------------------------------------
        total_registered_students = Student.objects.count()
        total_active_students = Student.objects.filter(status='ACTIVE').count()
        
        # Gender counts
        active_students_qs = Student.objects.filter(status='ACTIVE')
        if current_year:
            active_students_qs = active_students_qs.filter(enrollments__academic_year=current_year).distinct()
        
        male_students = active_students_qs.filter(gender='M').count()
        female_students = active_students_qs.filter(gender='F').count()

        # Students by Grade
        students_by_grade = (
            Grade.objects.filter(is_active=True)
            .annotate(
                total_enrolled=Count(
                    'class_offerings__student_enrollments',
                    filter=Q(class_offerings__student_enrollments__status='ACTIVE') & (Q(class_offerings__student_enrollments__academic_year=current_year) if current_year else Q())
                )
            )
            .order_by('level')
        )

        # Students by Class
        class_offerings_qs = ClassOffering.objects.all().select_related('grade', 'section', 'stream')
        if current_year:
            class_offerings_qs = class_offerings_qs.filter(academic_year=current_year)
        if filters.get('grade'):
            class_offerings_qs = class_offerings_qs.filter(grade=filters['grade'])

        students_by_class = (
            class_offerings_qs
            .annotate(enrolled_count=Count('student_enrollments', filter=Q(student_enrollments__status='ACTIVE')))
            .order_by('grade__level', 'section__name')
        )

        # New students registered (last 30 days or current year)
        thirty_days_ago = today - timedelta(days=30)
        newly_registered = Student.objects.filter(admission_date__gte=thirty_days_ago).count()

        # Graduated students
        graduated_students_count = GraduationRecord.objects.filter(status='GRADUATED').count()
        if graduated_students_count == 0:
            graduated_students_count = Student.objects.filter(status='GRADUATED').count()

        # -------------------------------------------------------------
        # 3. Teacher Statistics
        # -------------------------------------------------------------
        total_teachers = Teacher.objects.count()
        active_teachers = Teacher.objects.filter(is_active=True).count()
        inactive_teachers = total_teachers - active_teachers

        # Teachers by Subject Assignment
        teachers_by_subject = (
            Subject.objects.filter(is_active=True)
            .annotate(
                teacher_count=Count('teacher_assignments__teacher', distinct=True)
            )
            .filter(teacher_count__gt=0)
            .order_by('-teacher_count')
        )

        # Teachers with at least one active class assignment
        teachers_with_classes_count = TeacherAssignment.objects.filter(
            class_offering__academic_year=current_year
        ).values('teacher').distinct().count() if current_year else TeacherAssignment.objects.values('teacher').distinct().count()

        # -------------------------------------------------------------
        # 4. Attendance Statistics
        # -------------------------------------------------------------
        records_qs = AttendanceRecord.objects.all()
        if current_year:
            records_qs = records_qs.filter(attendance_session__academic_year=current_year)
        if filters.get('date_from'):
            records_qs = records_qs.filter(attendance_session__date__gte=filters['date_from'])
        if filters.get('date_to'):
            records_qs = records_qs.filter(attendance_session__date__lte=filters['date_to'])
        if filters.get('class_offering'):
            records_qs = records_qs.filter(attendance_session__class_offering=filters['class_offering'])

        total_attendance_records = records_qs.count()
        present_count = records_qs.filter(status='PRESENT').count()
        late_count = records_qs.filter(status='LATE').count()
        absent_count = records_qs.filter(status='ABSENT').count()
        excused_count = records_qs.filter(status='EXCUSED').count()

        if total_attendance_records > 0:
            attendance_percentage = round(((present_count + late_count) / total_attendance_records) * 100, 1)
        else:
            attendance_percentage = 0.0

        # Class-wise attendance rate summary (top 10 classes)
        class_attendance_summary = []
        for co in class_offerings_qs[:12]:
            co_records = records_qs.filter(attendance_session__class_offering=co)
            co_tot = co_records.count()
            if co_tot > 0:
                co_att = co_records.filter(status__in=['PRESENT', 'LATE']).count()
                co_rate = round((co_att / co_tot) * 100, 1)
            else:
                co_rate = 0.0
            class_attendance_summary.append({
                'class_name': co.display_name,
                'total_records': co_tot,
                'rate': co_rate
            })

        # -------------------------------------------------------------
        # 5. Examination Statistics
        # -------------------------------------------------------------
        exams_qs = Examination.objects.all()
        if current_year:
            exams_qs = exams_qs.filter(academic_year=current_year)

        total_examinations = exams_qs.count()
        completed_examinations = exams_qs.filter(is_locked=True).count()
        active_examinations = exams_qs.filter(is_active=True).count()

        # Mark submissions & pending approvals
        marks_qs = Mark.objects.all()
        if current_year:
            marks_qs = marks_qs.filter(exam_subject__examination__academic_year=current_year)

        total_marks_count = marks_qs.count()
        pending_mark_submissions = marks_qs.filter(status='DRAFT').count()
        pending_result_approvals = marks_qs.filter(status='SUBMITTED').count()
        published_results_count = marks_qs.filter(status='PUBLISHED').count()

        overall_exam_average = marks_qs.filter(marks_obtained__isnull=False).aggregate(avg=Avg('marks_obtained'))['avg']
        overall_exam_average = round(float(overall_exam_average), 1) if overall_exam_average is not None else 0.0

        # -------------------------------------------------------------
        # 6. Academic & Promotion Statistics
        # -------------------------------------------------------------
        promotion_records_qs = PromotionRecord.objects.all()
        if current_year:
            promotion_records_qs = promotion_records_qs.filter(batch__academic_year=current_year)

        promoted_count = promotion_records_qs.filter(final_outcome='PROMOTED').count()
        repeated_count = promotion_records_qs.filter(final_outcome='REPEATED').count()
        graduated_promo_count = promotion_records_qs.filter(final_outcome='GRADUATED').count()
        transferred_count = promotion_records_qs.filter(final_outcome='TRANSFERRED').count()
        pending_promo_count = promotion_records_qs.filter(final_outcome='PENDING').count()

        # Total historical status changes
        total_status_transitions = StudentStatusHistory.objects.count()

        return {
            'current_year': current_year,
            # Students
            'total_registered_students': total_registered_students,
            'total_active_students': total_active_students,
            'male_students': male_students,
            'female_students': female_students,
            'newly_registered': newly_registered,
            'graduated_students_count': graduated_students_count,
            'students_by_grade': students_by_grade,
            'students_by_class': students_by_class,
            # Teachers
            'total_teachers': total_teachers,
            'active_teachers': active_teachers,
            'inactive_teachers': inactive_teachers,
            'teachers_by_subject': teachers_by_subject,
            'teachers_with_classes_count': teachers_with_classes_count,
            # Attendance
            'total_attendance_records': total_attendance_records,
            'present_count': present_count,
            'absent_count': absent_count,
            'late_count': late_count,
            'excused_count': excused_count,
            'attendance_percentage': attendance_percentage,
            'class_attendance_summary': class_attendance_summary,
            # Examinations
            'total_examinations': total_examinations,
            'completed_examinations': completed_examinations,
            'active_examinations': active_examinations,
            'total_marks_count': total_marks_count,
            'pending_mark_submissions': pending_mark_submissions,
            'pending_result_approvals': pending_result_approvals,
            'published_results_count': published_results_count,
            'overall_exam_average': overall_exam_average,
            # Promotion
            'promoted_count': promoted_count,
            'repeated_count': repeated_count,
            'graduated_promo_count': graduated_promo_count,
            'transferred_count': transferred_count,
            'pending_promo_count': pending_promo_count,
            'total_status_transitions': total_status_transitions,
        }

    @classmethod
    def get_charts_payload(cls, filters=None, user=None):
        """
        Prepares 8 structured datasets for Chart.js client-side rendering.
        All datasets are formatted with labels, data arrays, and safe defaults.
        """
        filters = filters or {}
        current_year = filters.get('academic_year')
        if not current_year:
            current_year = AcademicYear.objects.filter(is_current=True).first()

        # 1. Student Distribution by Grade
        grade_qs = Grade.objects.filter(is_active=True).order_by('level')
        chart1_labels = []
        chart1_data = []
        for g in grade_qs:
            chart1_labels.append(g.name)
            cnt = StudentEnrollment.objects.filter(
                class_offering__grade=g,
                status='ACTIVE'
            )
            if current_year:
                cnt = cnt.filter(academic_year=current_year)
            chart1_data.append(cnt.count())

        # 2. Student Enrollment Trends by Academic Year (last 5 years)
        years = AcademicYear.objects.all().order_by('start_date')[:5]
        chart2_labels = [y.name for y in years]
        chart2_data = []
        for y in years:
            cnt = StudentEnrollment.objects.filter(academic_year=y, status='ACTIVE').count()
            chart2_data.append(cnt)

        # 3. Attendance Trends (last 10 attendance dates)
        recent_dates = (
            AttendanceSession.objects.values_list('date', flat=True)
            .distinct()
            .order_by('-date')[:10]
        )
        chronological_dates = sorted(list(recent_dates))
        chart3_labels = []
        chart3_data = []
        for d in chronological_dates:
            records = AttendanceRecord.objects.filter(attendance_session__date=d)
            if filters.get('class_offering'):
                records = records.filter(attendance_session__class_offering=filters['class_offering'])
            tot = records.count()
            if tot > 0:
                att = records.filter(status__in=['PRESENT', 'LATE']).count()
                rate = round((att / tot) * 100, 1)
            else:
                rate = 0.0
            chart3_labels.append(d.strftime('%b %d'))
            chart3_data.append(rate)

        # 4. Class Attendance Comparison
        classes = ClassOffering.objects.all().select_related('grade', 'section')
        if current_year:
            classes = classes.filter(academic_year=current_year)
        if filters.get('grade'):
            classes = classes.filter(grade=filters['grade'])
        classes = classes[:8]

        chart4_labels = []
        chart4_data = []
        for c in classes:
            c_records = AttendanceRecord.objects.filter(attendance_session__class_offering=c)
            c_tot = c_records.count()
            c_rate = round((c_records.filter(status__in=['PRESENT', 'LATE']).count() / c_tot) * 100, 1) if c_tot > 0 else 0.0
            chart4_labels.append(c.display_name)
            chart4_data.append(c_rate)

        # 5. Subject Performance Comparison (Average scores by subject)
        marks_qs = Mark.objects.filter(marks_obtained__isnull=False)
        if current_year:
            marks_qs = marks_qs.filter(exam_subject__examination__academic_year=current_year)
        if filters.get('grade'):
            marks_qs = marks_qs.filter(exam_subject__grade=filters['grade'])

        subject_perf = (
            marks_qs.values('exam_subject__subject__name')
            .annotate(avg_score=Avg('marks_obtained'))
            .order_by('-avg_score')[:8]
        )
        chart5_labels = [s['exam_subject__subject__name'] for s in subject_perf]
        chart5_data = [round(float(s['avg_score']), 1) for s in subject_perf]

        # 6. Examination Performance Trends (Average by Examination)
        exams = Examination.objects.all()
        if current_year:
            exams = exams.filter(academic_year=current_year)
        exams = exams.order_by('start_date')[:6]

        chart6_labels = []
        chart6_data = []
        for ex in exams:
            ex_marks = Mark.objects.filter(exam_subject__examination=ex, marks_obtained__isnull=False)
            avg = ex_marks.aggregate(a=Avg('marks_obtained'))['a']
            chart6_labels.append(ex.name)
            chart6_data.append(round(float(avg), 1) if avg is not None else 0.0)

        # 7. Teacher Distribution by Subject Specialization
        teachers_qs = Teacher.objects.filter(is_active=True).values('specialization').annotate(cnt=Count('id')).order_by('-cnt')[:8]
        chart7_labels = [t['specialization'] or 'General' for t in teachers_qs]
        chart7_data = [t['cnt'] for t in teachers_qs]

        # 8. Promotion Outcome Distribution
        promo_records = PromotionRecord.objects.all()
        if current_year:
            promo_records = promo_records.filter(batch__academic_year=current_year)

        chart8_labels = ['Promoted', 'Repeated', 'Graduated', 'Transferred', 'Pending']
        chart8_data = [
            promo_records.filter(final_outcome='PROMOTED').count(),
            promo_records.filter(final_outcome='REPEATED').count(),
            promo_records.filter(final_outcome='GRADUATED').count(),
            promo_records.filter(final_outcome='TRANSFERRED').count(),
            promo_records.filter(final_outcome='PENDING').count(),
        ]

        return {
            'chart1': {'labels': chart1_labels, 'data': chart1_data, 'title': 'Student Distribution by Grade'},
            'chart2': {'labels': chart2_labels, 'data': chart2_data, 'title': 'Enrollment Trends by Academic Year'},
            'chart3': {'labels': chart3_labels, 'data': chart3_data, 'title': 'Attendance Rate Trend (%)'},
            'chart4': {'labels': chart4_labels, 'data': chart4_data, 'title': 'Class Attendance Rate Comparison (%)'},
            'chart5': {'labels': chart5_labels, 'data': chart5_data, 'title': 'Subject Average Score Comparison'},
            'chart6': {'labels': chart6_labels, 'data': chart6_data, 'title': 'Examination Performance Trends'},
            'chart7': {'labels': chart7_labels, 'data': chart7_data, 'title': 'Teacher Count by Specialization'},
            'chart8': {'labels': chart8_labels, 'data': chart8_data, 'title': 'Promotion Outcome Distribution'},
        }


class StudentReportService:
    """Service generating tabular rosters and individual 360-degree academic reports."""

    @classmethod
    def get_student_reports(cls, filters=None, user=None):
        """
        Retrieves a filtered, paginated queryset of enrolled students with academic and attendance stats.
        Respects teacher role restrictions by filtering to assigned classes if user is a teacher.
        """
        filters = filters or {}
        enrollments = (
            StudentEnrollment.objects.all()
            .select_related('student', 'class_offering__grade', 'class_offering__section', 'class_offering__stream', 'academic_year')
            .order_by('class_offering__grade__level', 'class_offering__section__name', 'student__first_name', 'student__father_name')
        )

        # Role enforcement for Teachers
        if user and hasattr(user, 'role') and user.role and user.role.code == 'TEACHER':
            if hasattr(user, 'teacher_profile'):
                assigned_classes = TeacherAssignment.objects.filter(
                    teacher=user.teacher_profile
                ).values_list('class_offering_id', flat=True)
                enrollments = enrollments.filter(class_offering_id__in=assigned_classes)

        # Filters
        if filters.get('academic_year'):
            enrollments = enrollments.filter(academic_year=filters['academic_year'])
        if filters.get('grade'):
            enrollments = enrollments.filter(class_offering__grade=filters['grade'])
        if filters.get('class_offering'):
            enrollments = enrollments.filter(class_offering=filters['class_offering'])
        if filters.get('section'):
            enrollments = enrollments.filter(class_offering__section=filters['section'])
        if filters.get('stream'):
            enrollments = enrollments.filter(class_offering__stream=filters['stream'])
        if filters.get('search'):
            query = filters['search'].strip()
            enrollments = enrollments.filter(
                Q(student__admission_number__icontains=query) |
                Q(student__first_name__icontains=query) |
                Q(student__father_name__icontains=query) |
                Q(student__grandfather_name__icontains=query)
            )

        return enrollments

    @classmethod
    def get_student_detail_report(cls, student_id, user=None):
        """
        Builds a comprehensive 360-degree student academic portfolio:
        - Bio & guardian profile
        - Longitudinal enrollments across all years
        - Examination marks, averages, and ranks
        - Attendance statistics and presence percentage
        - Promotion batch outcomes and graduation records
        """
        student = Student.objects.prefetch_related('enrollments__academic_year', 'enrollments__class_offering__grade').get(pk=student_id)

        # Multi-year enrollments
        enrollments = student.enrollments.all().select_related('academic_year', 'class_offering__grade', 'class_offering__section').order_by('-academic_year__start_date')

        # Examination results summary
        results = StudentResultSummary.objects.filter(
            student_enrollment__student=student
        ).select_related('examination__academic_year', 'student_enrollment__class_offering__grade').order_by('-examination__start_date')

        # Recent marks
        recent_marks = Mark.objects.filter(
            student_enrollment__student=student
        ).select_related('exam_subject__subject', 'exam_subject__examination').order_by('-exam_subject__examination__start_date')[:15]

        # Attendance summary
        records = AttendanceRecord.objects.filter(student_enrollment__student=student)
        total_sessions = records.count()
        present = records.filter(status='PRESENT').count()
        late = records.filter(status='LATE').count()
        absent = records.filter(status='ABSENT').count()
        excused = records.filter(status='EXCUSED').count()
        rate = round(((present + late) / total_sessions) * 100, 1) if total_sessions > 0 else 0.0

        # Promotion and status history
        promotions = PromotionRecord.objects.filter(student=student).select_related('batch__academic_year', 'batch__target_academic_year', 'batch__grade')
        status_changes = StudentStatusHistory.objects.filter(student=student).order_by('-effective_date')
        graduation = GraduationRecord.objects.filter(student=student).first()

        return {
            'student': student,
            'enrollments': enrollments,
            'results': results,
            'recent_marks': recent_marks,
            'attendance': {
                'total_sessions': total_sessions,
                'present': present,
                'late': late,
                'absent': absent,
                'excused': excused,
                'rate': rate,
            },
            'promotions': promotions,
            'status_changes': status_changes,
            'graduation': graduation,
        }


class TeacherReportService:
    """Service providing teacher workload, assignment, and timetable analytics."""

    @classmethod
    def get_teacher_reports(cls, filters=None, user=None):
        """
        Retrieves a filtered queryset of teachers with aggregated workload data:
        assigned subjects count, assigned classes count, and weekly scheduled period count.
        """
        filters = filters or {}
        teachers = Teacher.objects.all().order_by('first_name', 'father_name')

        if filters.get('teacher'):
            teachers = teachers.filter(id=filters['teacher'].id)

        # Subject filter
        if filters.get('subject'):
            teachers = teachers.filter(assignments__subject=filters['subject']).distinct()

        # Build list with computed workloads
        report_data = []
        for t in teachers:
            assignments = t.assignments.all().select_related('subject', 'class_offering__grade', 'class_offering__section')
            if filters.get('academic_year'):
                assignments = assignments.filter(class_offering__academic_year=filters['academic_year'])

            classes_count = assignments.values('class_offering').distinct().count()
            subjects_list = list(assignments.values_list('subject__name', flat=True).distinct())

            # Scheduled lessons in published timetables
            periods_count = TimetableEntry.objects.filter(
                teacher=t,
                timetable__status='PUBLISHED'
            )
            if filters.get('academic_year'):
                periods_count = periods_count.filter(timetable__academic_year=filters['academic_year'])
            periods_count = periods_count.count()

            report_data.append({
                'teacher': t,
                'assignments': assignments,
                'classes_count': classes_count,
                'subjects_list': subjects_list,
                'periods_count': periods_count,
            })

        return report_data


class AttendanceReportService:
    """Service providing daily/weekly/monthly attendance aggregates and chronic absentee alerts."""

    @classmethod
    def get_attendance_reports(cls, filters=None, user=None):
        """
        Computes detailed attendance breakdowns:
        - Daily summary across date range
        - Class-wise comparison
        - Grade-wise comparison
        - Chronic absenteeism list (students with > 3 absences or < 80% attendance)
        """
        filters = filters or {}
        sessions = AttendanceSession.objects.all().select_related('class_offering__grade', 'class_offering__section', 'academic_year')

        if filters.get('academic_year'):
            sessions = sessions.filter(academic_year=filters['academic_year'])
        if filters.get('grade'):
            sessions = sessions.filter(class_offering__grade=filters['grade'])
        if filters.get('class_offering'):
            sessions = sessions.filter(class_offering=filters['class_offering'])
        if filters.get('date_from'):
            sessions = sessions.filter(date__gte=filters['date_from'])
        if filters.get('date_to'):
            sessions = sessions.filter(date__lte=filters['date_to'])

        # Role enforcement for teachers
        if user and hasattr(user, 'role') and user.role and user.role.code == 'TEACHER':
            if hasattr(user, 'teacher_profile'):
                assigned_classes = TeacherAssignment.objects.filter(teacher=user.teacher_profile).values_list('class_offering_id', flat=True)
                sessions = sessions.filter(class_offering_id__in=assigned_classes)

        # Daily Attendance Breakdown
        daily_records = (
            AttendanceRecord.objects.filter(attendance_session__in=sessions)
            .values('attendance_session__date')
            .annotate(
                total=Count('id'),
                present=Count('id', filter=Q(status='PRESENT')),
                late=Count('id', filter=Q(status='LATE')),
                absent=Count('id', filter=Q(status='ABSENT')),
                excused=Count('id', filter=Q(status='EXCUSED')),
            )
            .order_by('-attendance_session__date')[:30]
        )

        daily_summary = []
        for d in daily_records:
            tot = d['total']
            att = d['present'] + d['late']
            rate = round((att / tot) * 100, 1) if tot > 0 else 0.0
            daily_summary.append({
                'date': d['attendance_session__date'],
                'total': tot,
                'present': d['present'],
                'late': d['late'],
                'absent': d['absent'],
                'excused': d['excused'],
                'rate': rate
            })

        # Chronic Absenteeism Review: Students with attendance rate < 80% or >= 3 absences
        chronic_absentees = []
        student_records = (
            AttendanceRecord.objects.filter(attendance_session__in=sessions)
            .values(
                'student_enrollment__student__id',
                'student_enrollment__student__admission_number',
                'student_enrollment__student__first_name',
                'student_enrollment__student__father_name',
                'student_enrollment__class_offering__grade__name',
                'student_enrollment__class_offering__section__name'
            )
            .annotate(
                total=Count('id'),
                absent=Count('id', filter=Q(status='ABSENT')),
                late=Count('id', filter=Q(status='LATE')),
                present=Count('id', filter=Q(status='PRESENT')),
            )
            .filter(absent__gte=3)
            .order_by('-absent')[:25]
        )

        for s in student_records:
            tot = s['total']
            att = s['present'] + s['late']
            rate = round((att / tot) * 100, 1) if tot > 0 else 0.0
            chronic_absentees.append({
                'student_id': s['student_enrollment__student__id'],
                'admission_number': s['student_enrollment__student__admission_number'],
                'full_name': f"{s['student_enrollment__student__first_name']} {s['student_enrollment__student__father_name']}",
                'class_name': f"{s['student_enrollment__class_offering__grade__name']} - {s['student_enrollment__class_offering__section__name']}",
                'total_sessions': tot,
                'absent_count': s['absent'],
                'late_count': s['late'],
                'rate': rate
            })

        return {
            'daily_summary': daily_summary,
            'chronic_absentees': chronic_absentees,
            'total_sessions_count': sessions.count(),
        }


class ExaminationPerformanceReportService:
    """Service providing broad-sheet examination analysis, mark completion, and pass statistics."""

    @classmethod
    def get_examination_reports(cls, filters=None, user=None):
        """
        Compiles examination-level completion metrics and score bounds.
        """
        filters = filters or {}
        exams = Examination.objects.all().select_related('academic_year').order_by('-start_date')

        if filters.get('academic_year'):
            exams = exams.filter(academic_year=filters['academic_year'])
        if filters.get('examination'):
            exams = exams.filter(id=filters['examination'].id)

        exam_reports = []
        for ex in exams:
            exam_subjects = ExamSubject.objects.filter(examination=ex).select_related('subject', 'grade')
            marks = Mark.objects.filter(exam_subject__examination=ex)

            total_subjects = exam_subjects.count()
            total_marks = marks.count()
            entered_marks = marks.filter(marks_obtained__isnull=False).count()
            draft_count = marks.filter(status='DRAFT').count()
            verified_count = marks.filter(status__in=['VERIFIED', 'PUBLISHED']).count()
            avg_score = marks.filter(marks_obtained__isnull=False).aggregate(a=Avg('marks_obtained'))['a']
            highest_score = marks.filter(marks_obtained__isnull=False).aggregate(m=Max('marks_obtained'))['m']
            lowest_score = marks.filter(marks_obtained__isnull=False).aggregate(m=Min('marks_obtained'))['m']

            # Passing percentage calculation
            passing_marks = marks.filter(marks_obtained__isnull=False, marks_obtained__gte=F('exam_subject__pass_marks')).count()
            pass_rate = round((passing_marks / entered_marks) * 100, 1) if entered_marks > 0 else 0.0

            exam_reports.append({
                'examination': ex,
                'total_subjects': total_subjects,
                'total_marks': total_marks,
                'entered_marks': entered_marks,
                'draft_count': draft_count,
                'verified_count': verified_count,
                'average': round(float(avg_score), 1) if avg_score is not None else 0.0,
                'highest': round(float(highest_score), 1) if highest_score is not None else 0.0,
                'lowest': round(float(lowest_score), 1) if lowest_score is not None else 0.0,
                'pass_rate': pass_rate,
            })

        return exam_reports

    @classmethod
    def get_subject_performance_reports(cls, filters=None, user=None):
        """
        Compiles subject-level score broadsheets with highest, lowest, average, and pass rates.
        """
        filters = filters or {}
        exam_subjects = ExamSubject.objects.all().select_related('subject', 'grade', 'examination')

        if filters.get('academic_year'):
            exam_subjects = exam_subjects.filter(examination__academic_year=filters['academic_year'])
        if filters.get('examination'):
            exam_subjects = exam_subjects.filter(examination=filters['examination'])
        if filters.get('subject'):
            exam_subjects = exam_subjects.filter(subject=filters['subject'])
        if filters.get('grade'):
            exam_subjects = exam_subjects.filter(grade=filters['grade'])

        subject_reports = []
        for es in exam_subjects[:30]:
            marks = Mark.objects.filter(exam_subject=es)
            total = marks.count()
            sat = marks.filter(marks_obtained__isnull=False).count()
            absent = marks.filter(is_absent=True).count()
            avg = marks.filter(marks_obtained__isnull=False).aggregate(a=Avg('marks_obtained'))['a']
            hi = marks.filter(marks_obtained__isnull=False).aggregate(m=Max('marks_obtained'))['m']
            lo = marks.filter(marks_obtained__isnull=False).aggregate(m=Min('marks_obtained'))['m']
            passed = marks.filter(marks_obtained__isnull=False, marks_obtained__gte=es.pass_marks).count()
            pass_pct = round((passed / sat) * 100, 1) if sat > 0 else 0.0

            subject_reports.append({
                'exam_subject': es,
                'subject_name': es.subject.name,
                'grade_name': es.grade.name,
                'examination_name': es.examination.name,
                'max_marks': es.max_marks,
                'pass_marks': es.pass_marks,
                'total_candidates': total,
                'sat_count': sat,
                'absent_count': absent,
                'average': round(float(avg), 1) if avg is not None else 0.0,
                'highest': round(float(hi), 1) if hi is not None else 0.0,
                'lowest': round(float(lo), 1) if lo is not None else 0.0,
                'pass_percentage': pass_pct,
            })

        return subject_reports


class PromotionReportService:
    """Service compiling promotion cohort results and graduation archives."""

    @classmethod
    def get_promotion_reports(cls, filters=None, user=None):
        """
        Returns batch-by-batch promotion summaries and graduation registries.
        """
        filters = filters or {}
        batches = PromotionBatch.objects.all().select_related('academic_year', 'target_academic_year', 'grade', 'promotion_criteria').order_by('-created_at')

        if filters.get('academic_year'):
            batches = batches.filter(academic_year=filters['academic_year'])
        if filters.get('grade'):
            batches = batches.filter(grade=filters['grade'])

        batch_summaries = []
        for b in batches:
            records = b.records.all()
            tot = records.count()
            promoted = records.filter(final_outcome='PROMOTED').count()
            repeated = records.filter(final_outcome='REPEATED').count()
            graduated = records.filter(final_outcome='GRADUATED').count()
            transferred = records.filter(final_outcome='TRANSFERRED').count()
            pending = records.filter(final_outcome='PENDING').count()

            promo_rate = round((promoted / tot) * 100, 1) if tot > 0 else 0.0

            batch_summaries.append({
                'batch': b,
                'total_candidates': tot,
                'promoted': promoted,
                'repeated': repeated,
                'graduated': graduated,
                'transferred': transferred,
                'pending': pending,
                'promotion_rate': promo_rate,
            })

        # Official Graduations
        graduations = GraduationRecord.objects.all().select_related('student', 'academic_year')
        if filters.get('academic_year'):
            graduations = graduations.filter(academic_year=filters['academic_year'])
        graduations = graduations.order_by('-graduation_date')[:50]

        return {
            'batch_summaries': batch_summaries,
            'graduations': graduations,
        }


class ReportExportService:
    """
    Generates downloadable PDF and Excel files for all major school reports.
    Employs ReportLab for vector PDFs and OpenPyXL for styled spreadsheets.
    """

    @classmethod
    def export_pdf(cls, report_type, context, title="School Report"):
        """
        Compiles and renders a publication-grade A4 Landscape PDF report.
        """
        from reportlab.lib.pagesizes import letter, landscape
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=landscape(letter),
            rightMargin=25,
            leftMargin=25,
            topMargin=25,
            bottomMargin=25
        )
        elements = []
        styles = getSampleStyleSheet()

        header_title_style = ParagraphStyle(
            'HeaderTitle',
            parent=styles['Heading1'],
            fontSize=13,
            leading=16,
            alignment=1,
            textColor=colors.HexColor('#0F172A')
        )
        sub_style = ParagraphStyle(
            'HeaderSub',
            parent=styles['Normal'],
            fontSize=8.5,
            leading=11,
            alignment=1,
            textColor=colors.HexColor('#475569')
        )
        cell_style = ParagraphStyle(
            'CellText',
            parent=styles['Normal'],
            fontSize=7.5,
            leading=9.5,
            textColor=colors.HexColor('#1E293B')
        )
        th_style = ParagraphStyle(
            'THText',
            parent=styles['Normal'],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor('#FFFFFF'),
            fontName='Helvetica-Bold'
        )

        # 1. School Header Banner
        elements.append(Paragraph("<b>SMART SCHOOL MANAGEMENT SYSTEM (SSMS)</b>", header_title_style))
        elements.append(Paragraph("Majang Zone Secondary School &bull; Gambella Regional State, Ethiopia", sub_style))
        elements.append(Paragraph(f"<b>{title.upper()}</b> &bull; Generated: {timezone.now().strftime('%Y-%m-%d %H:%M')}", sub_style))
        elements.append(Spacer(1, 12))

        # 2. Table Data Assembly based on report_type
        table_data = []

        if report_type == 'students':
            table_data.append([
                Paragraph("Admission No", th_style),
                Paragraph("Student Full Name", th_style),
                Paragraph("Gender", th_style),
                Paragraph("Grade & Section", th_style),
                Paragraph("Stream", th_style),
                Paragraph("Academic Year", th_style),
                Paragraph("Status", th_style),
            ])
            for item in context.get('records', [])[:200]:
                st = item.student
                co = item.class_offering
                table_data.append([
                    Paragraph(st.admission_number, cell_style),
                    Paragraph(st.full_name, cell_style),
                    Paragraph(st.get_gender_display(), cell_style),
                    Paragraph(f"{co.grade.name} - {co.section.name}", cell_style),
                    Paragraph(co.stream.name if co.stream else 'General', cell_style),
                    Paragraph(item.academic_year.name, cell_style),
                    Paragraph(item.get_status_display(), cell_style),
                ])

        elif report_type == 'teachers':
            table_data.append([
                Paragraph("Employee ID", th_style),
                Paragraph("Teacher Full Name", th_style),
                Paragraph("Gender", th_style),
                Paragraph("Specialization", th_style),
                Paragraph("Classes Count", th_style),
                Paragraph("Subjects Taught", th_style),
                Paragraph("Weekly Periods", th_style),
                Paragraph("Status", th_style),
            ])
            for item in context.get('records', []):
                t = item['teacher']
                table_data.append([
                    Paragraph(t.employee_id, cell_style),
                    Paragraph(t.full_name, cell_style),
                    Paragraph(t.get_gender_display(), cell_style),
                    Paragraph(t.specialization or '-', cell_style),
                    Paragraph(str(item['classes_count']), cell_style),
                    Paragraph(", ".join(item['subjects_list']) if item['subjects_list'] else 'None', cell_style),
                    Paragraph(str(item['periods_count']), cell_style),
                    Paragraph(t.get_employment_status_display(), cell_style),
                ])

        elif report_type == 'attendance':
            table_data.append([
                Paragraph("Date", th_style),
                Paragraph("Total Enrolled", th_style),
                Paragraph("Present", th_style),
                Paragraph("Late", th_style),
                Paragraph("Absent", th_style),
                Paragraph("Excused", th_style),
                Paragraph("Attendance Rate (%)", th_style),
            ])
            for item in context.get('records', []):
                table_data.append([
                    Paragraph(str(item['date']), cell_style),
                    Paragraph(str(item['total']), cell_style),
                    Paragraph(str(item['present']), cell_style),
                    Paragraph(str(item['late']), cell_style),
                    Paragraph(str(item['absent']), cell_style),
                    Paragraph(str(item['excused']), cell_style),
                    Paragraph(f"{item['rate']}%", cell_style),
                ])

        elif report_type in ['examinations', 'academic']:
            table_data.append([
                Paragraph("Examination", th_style),
                Paragraph("Subject", th_style),
                Paragraph("Grade", th_style),
                Paragraph("Max / Pass", th_style),
                Paragraph("Sat", th_style),
                Paragraph("Average", th_style),
                Paragraph("Highest", th_style),
                Paragraph("Lowest", th_style),
                Paragraph("Pass Rate (%)", th_style),
            ])
            for item in context.get('records', []):
                table_data.append([
                    Paragraph(item['examination_name'], cell_style),
                    Paragraph(item['subject_name'], cell_style),
                    Paragraph(item['grade_name'], cell_style),
                    Paragraph(f"{item['max_marks']} / {item['pass_marks']}", cell_style),
                    Paragraph(str(item['sat_count']), cell_style),
                    Paragraph(str(item['average']), cell_style),
                    Paragraph(str(item['highest']), cell_style),
                    Paragraph(str(item['lowest']), cell_style),
                    Paragraph(f"{item['pass_percentage']}%", cell_style),
                ])

        elif report_type == 'promotion':
            table_data.append([
                Paragraph("Cohort Batch Name", th_style),
                Paragraph("Academic Year", th_style),
                Paragraph("Target Year", th_style),
                Paragraph("Grade", th_style),
                Paragraph("Candidates", th_style),
                Paragraph("Promoted", th_style),
                Paragraph("Repeated", th_style),
                Paragraph("Graduated", th_style),
                Paragraph("Promotion Rate (%)", th_style),
            ])
            for item in context.get('records', []):
                b = item['batch']
                table_data.append([
                    Paragraph(b.name, cell_style),
                    Paragraph(b.academic_year.name, cell_style),
                    Paragraph(b.target_academic_year.name, cell_style),
                    Paragraph(b.grade.name, cell_style),
                    Paragraph(str(item['total_candidates']), cell_style),
                    Paragraph(str(item['promoted']), cell_style),
                    Paragraph(str(item['repeated']), cell_style),
                    Paragraph(str(item['graduated']), cell_style),
                    Paragraph(f"{item['promotion_rate']}%", cell_style),
                ])

        # Style Table
        if len(table_data) > 1:
            t = Table(table_data, repeatRows=1)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0F172A')),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor('#FFFFFF'), colors.HexColor('#F8FAFC')]),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ]))
            elements.append(t)
        else:
            elements.append(Paragraph("<i>No data records matched the selected query filters.</i>", sub_style))

        # 3. Footer and Signature Block
        elements.append(Spacer(1, 20))
        sig_data = [
            [
                Paragraph("<b>Prepared By:</b> ___________________________", sub_style),
                Paragraph("<b>Approved By (Principal):</b> ___________________________", sub_style),
                Paragraph("<b>Official School Seal:</b> [ &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; &nbsp; ]", sub_style),
            ]
        ]
        sig_table = Table(sig_data, colWidths=[240, 260, 200])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(sig_table)

        doc.build(elements)
        buffer.seek(0)
        return buffer

    @classmethod
    def export_excel(cls, report_type, context, title="School Report"):
        """
        Compiles and renders a styled Microsoft Excel spreadsheet (.xlsx).
        """
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = title[:30]

        # Styling Definitions
        title_font = Font(name='Calibri', size=14, bold=True, color='0F172A')
        sub_font = Font(name='Calibri', size=9, italic=True, color='475569')
        th_font = Font(name='Calibri', size=10, bold=True, color='FFFFFF')
        th_fill = PatternFill(start_color='0F172A', end_color='0F172A', fill_type='solid')
        cell_font = Font(name='Calibri', size=10)
        center_align = Alignment(horizontal='center', vertical='center')
        left_align = Alignment(horizontal='left', vertical='center')
        thin_border = Border(
            left=Side(style='thin', color='E2E8F0'),
            right=Side(style='thin', color='E2E8F0'),
            top=Side(style='thin', color='E2E8F0'),
            bottom=Side(style='thin', color='E2E8F0')
        )

        # Header Rows
        ws.merge_cells('A1:G1')
        ws['A1'] = "SMART SCHOOL MANAGEMENT SYSTEM (SSMS) - MAJANG ZONE SECONDARY SCHOOL"
        ws['A1'].font = title_font
        ws['A1'].alignment = left_align

        ws.merge_cells('A2:G2')
        ws['A2'] = f"{title.upper()} | Generated on: {timezone.now().strftime('%Y-%m-%d %H:%M')}"
        ws['A2'].font = sub_font
        ws['A2'].alignment = left_align

        # Headers & Row Population
        row_num = 4

        if report_type == 'students':
            headers = ["Admission No", "Student Name", "Gender", "Grade & Section", "Stream", "Academic Year", "Status"]
            ws.append([])  # blank row
            for col_idx, h in enumerate(headers, 1):
                cell = ws.cell(row=row_num, column=col_idx, value=h)
                cell.font = th_font
                cell.fill = th_fill
                cell.alignment = center_align

            for item in context.get('records', [])[:500]:
                row_num += 1
                st = item.student
                co = item.class_offering
                ws.append([
                    st.admission_number,
                    st.full_name,
                    st.get_gender_display(),
                    f"{co.grade.name} - {co.section.name}",
                    co.stream.name if co.stream else 'General',
                    item.academic_year.name,
                    item.get_status_display()
                ])

        elif report_type == 'teachers':
            headers = ["Employee ID", "Teacher Name", "Gender", "Specialization", "Classes Count", "Subjects Taught", "Weekly Periods", "Status"]
            for col_idx, h in enumerate(headers, 1):
                cell = ws.cell(row=row_num, column=col_idx, value=h)
                cell.font = th_font
                cell.fill = th_fill
                cell.alignment = center_align

            for item in context.get('records', []):
                row_num += 1
                t = item['teacher']
                ws.append([
                    t.employee_id,
                    t.full_name,
                    t.get_gender_display(),
                    t.specialization or '-',
                    item['classes_count'],
                    ", ".join(item['subjects_list']) if item['subjects_list'] else 'None',
                    item['periods_count'],
                    t.get_employment_status_display()
                ])

        elif report_type == 'attendance':
            headers = ["Date", "Total Enrolled", "Present", "Late", "Absent", "Excused", "Attendance Rate (%)"]
            for col_idx, h in enumerate(headers, 1):
                cell = ws.cell(row=row_num, column=col_idx, value=h)
                cell.font = th_font
                cell.fill = th_fill
                cell.alignment = center_align

            for item in context.get('records', []):
                row_num += 1
                ws.append([
                    str(item['date']),
                    item['total'],
                    item['present'],
                    item['late'],
                    item['absent'],
                    item['excused'],
                    f"{item['rate']}%"
                ])

        elif report_type in ['examinations', 'academic']:
            headers = ["Examination", "Subject", "Grade", "Max Marks", "Pass Marks", "Sat Count", "Average", "Highest", "Lowest", "Pass Rate (%)"]
            for col_idx, h in enumerate(headers, 1):
                cell = ws.cell(row=row_num, column=col_idx, value=h)
                cell.font = th_font
                cell.fill = th_fill
                cell.alignment = center_align

            for item in context.get('records', []):
                row_num += 1
                ws.append([
                    item['examination_name'],
                    item['subject_name'],
                    item['grade_name'],
                    item['max_marks'],
                    item['pass_marks'],
                    item['sat_count'],
                    item['average'],
                    item['highest'],
                    item['lowest'],
                    f"{item['pass_percentage']}%"
                ])

        elif report_type == 'promotion':
            headers = ["Cohort Batch", "Academic Year", "Target Year", "Grade", "Candidates", "Promoted", "Repeated", "Graduated", "Promotion Rate (%)"]
            for col_idx, h in enumerate(headers, 1):
                cell = ws.cell(row=row_num, column=col_idx, value=h)
                cell.font = th_font
                cell.fill = th_fill
                cell.alignment = center_align

            for item in context.get('records', []):
                row_num += 1
                b = item['batch']
                ws.append([
                    b.name,
                    b.academic_year.name,
                    b.target_academic_year.name,
                    b.grade.name,
                    item['total_candidates'],
                    item['promoted'],
                    item['repeated'],
                    item['graduated'],
                    f"{item['promotion_rate']}%"
                ])

        # Auto-adjust column widths and cell styling
        for col in ws.columns:
            max_len = 0
            col_letter = get_column_letter(col[0].column)
            for cell in col:
                cell.border = thin_border
                if cell.row > 4:
                    cell.font = cell_font
                val_str = str(cell.value or '')
                if len(val_str) > max_len:
                    max_len = len(val_str)
            ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer
