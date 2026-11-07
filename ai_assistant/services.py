"""
Core Intelligence and Analytics Services for AI-Powered School Assistant.
Operates 100% offline with zero cloud API dependencies.
"""

import math
import statistics
import re
from datetime import date, timedelta
from decimal import Decimal
import io

from django.db.models import Avg, Count, Max, Min, Q, StdDev
from django.utils import timezone
from django.core.exceptions import PermissionDenied

from academics.models import AcademicYear, Grade, Section, Stream, Subject, ClassOffering
from students.models import Student, StudentEnrollment
from teachers.models import Teacher, TeacherAssignment
from attendance.models import AttendanceSession, AttendanceRecord
from examinations.models import Examination, ExamSubject
from results.models import Mark, StudentResultSummary
from promotion.models import PromotionBatch, PromotionRecord, PromotionCriteria
from timetable.models import Timetable, TimetableEntry, Period, SchoolDay
from core.models import AuditLog


class AcademicAnalysisService:
    """
    Advanced offline statistical analysis of verified student examination records.
    Provides subject averages, variance, attention indices, and class benchmarks.
    """

    @classmethod
    def get_subject_averages(cls, academic_year=None, grade=None, class_offering=None, user=None):
        """
        Calculates comprehensive subject performance statistics across verified results.
        """
        # Teacher scoping
        allowed_subject_ids = None
        if user and getattr(user, 'role', None) and user.role.code == 'TEACHER':
            if hasattr(user, 'teacher_profile'):
                teacher = user.teacher_profile
                allowed_subject_ids = list(TeacherAssignment.objects.filter(
                    teacher=teacher
                ).values_list('subject_id', flat=True).distinct())

        exam_subjects = ExamSubject.objects.all().select_related('subject', 'grade', 'examination')
        if academic_year:
            exam_subjects = exam_subjects.filter(examination__academic_year=academic_year)
        if grade:
            exam_subjects = exam_subjects.filter(grade=grade)
        if allowed_subject_ids is not None:
            exam_subjects = exam_subjects.filter(subject_id__in=allowed_subject_ids)

        results_list = []
        for es in exam_subjects[:40]:
            marks_qs = Mark.objects.filter(exam_subject=es)
            if class_offering:
                marks_qs = marks_qs.filter(student_enrollment__class_offering=class_offering)

            total_entries = marks_qs.count()
            sat_marks_qs = marks_qs.filter(marks_obtained__isnull=False, is_absent=False)
            sat_count = sat_marks_qs.count()

            if sat_count > 0:
                scores = list(sat_marks_qs.values_list('marks_obtained', flat=True))
                float_scores = [float(s) for s in scores]
                avg_score = round(statistics.mean(float_scores), 2)
                median_score = round(statistics.median(float_scores), 2)
                max_score = round(max(float_scores), 2)
                min_score = round(min(float_scores), 2)
                std_dev = round(statistics.stdev(float_scores), 2) if len(float_scores) > 1 else 0.0

                pass_threshold = float(es.pass_marks)
                passed_count = sum(1 for s in float_scores if s >= pass_threshold)
                pass_rate = round((passed_count / sat_count) * 100, 1)

                # Attention required indicator
                needs_attention = (pass_rate < 60.0) or (avg_score < float(es.pass_marks))
                attention_reason = []
                if pass_rate < 50.0:
                    attention_reason.append(f"Critical fail rate ({100 - pass_rate:.1f}%)")
                elif pass_rate < 60.0:
                    attention_reason.append(f"Sub-optimal pass rate ({pass_rate}%)")
                if avg_score < float(es.pass_marks):
                    attention_reason.append(f"Mean ({avg_score}) below pass mark ({es.pass_marks})")
                if std_dev > 25.0:
                    attention_reason.append(f"High score dispersion (SD: {std_dev})")
            else:
                avg_score = 0.0
                median_score = 0.0
                max_score = 0.0
                min_score = 0.0
                std_dev = 0.0
                pass_rate = 0.0
                needs_attention = False
                attention_reason = ["No sat exam records"]

            results_list.append({
                'exam_subject_id': es.id,
                'subject_id': es.subject.id,
                'subject_name': es.subject.name,
                'subject_code': es.subject.code,
                'grade_id': es.grade.id,
                'grade_name': es.grade.name,
                'examination_name': es.examination.name,
                'max_marks': float(es.max_marks),
                'pass_marks': float(es.pass_marks),
                'total_enrolled': total_entries,
                'sat_count': sat_count,
                'average_score': avg_score,
                'median_score': median_score,
                'max_score': max_score,
                'min_score': min_score,
                'std_dev': std_dev,
                'pass_rate': pass_rate,
                'needs_attention': needs_attention,
                'attention_reason': ", ".join(attention_reason) if needs_attention else "Normal performance",
            })

        return results_list

    @classmethod
    def get_subjects_requiring_attention(cls, academic_year=None, grade=None, user=None):
        """
        Filters and ranks subjects that exhibit high difficulty or low pass rates,
        formulating pedagogical recommendations for academic intervention.
        """
        all_subjects = cls.get_subject_averages(academic_year=academic_year, grade=grade, user=user)
        attention_list = [s for s in all_subjects if s['needs_attention'] and s['sat_count'] > 0]

        # Sort by pass rate ascending (most critical first)
        attention_list.sort(key=lambda x: (x['pass_rate'], x['average_score']))

        for item in attention_list:
            recs = []
            if item['pass_rate'] < 50.0:
                recs.append("Organize structured after-school remedial tutorial cohorts for struggling students.")
                recs.append("Review syllabus pacing and ensure foundational prerequisite concepts are thoroughly consolidated.")
            elif item['pass_rate'] < 60.0:
                recs.append("Conduct teacher peer-observations and collaborate on targeted formative quiz assessments.")
            if item['std_dev'] > 20.0:
                recs.append("Differentiated instructional tasks recommended to support both lower-tier and high-achieving pupils.")
            item['recommendations'] = recs

        return attention_list

    @classmethod
    def get_class_comparison_matrix(cls, academic_year=None, grade=None, user=None):
        """
        Compares academic achievement across class sections within the same grade level.
        """
        class_offerings = ClassOffering.objects.all().select_related('academic_year', 'grade', 'section', 'stream')
        if academic_year:
            class_offerings = class_offerings.filter(academic_year=academic_year)
        if grade:
            class_offerings = class_offerings.filter(grade=grade)

        # Teacher scoping
        if user and getattr(user, 'role', None) and user.role.code == 'TEACHER':
            if hasattr(user, 'teacher_profile'):
                teacher = user.teacher_profile
                allowed_co_ids = list(TeacherAssignment.objects.filter(
                    teacher=teacher
                ).values_list('class_offering_id', flat=True).distinct())
                class_offerings = class_offerings.filter(id__in=allowed_co_ids)

        matrix = []
        for co in class_offerings:
            enrollments = co.student_enrollments.filter(status='ACTIVE')
            student_count = enrollments.count()

            marks = Mark.objects.filter(
                student_enrollment__class_offering=co,
                marks_obtained__isnull=False,
                is_absent=False
            )
            scores = list(marks.values_list('marks_obtained', flat=True))
            float_scores = [float(s) for s in scores]

            if float_scores:
                class_avg = round(statistics.mean(float_scores), 2)
                class_max = round(max(float_scores), 2)
                class_min = round(min(float_scores), 2)
                # Count scores >= 50%
                passing = sum(1 for s in float_scores if s >= 50.0)
                class_pass_rate = round((passing / len(float_scores)) * 100, 1)
            else:
                class_avg = 0.0
                class_max = 0.0
                class_min = 0.0
                class_pass_rate = 0.0

            matrix.append({
                'class_offering_id': co.id,
                'class_name': co.display_name,
                'grade_name': co.grade.name,
                'section_name': co.section.name,
                'stream_name': co.stream.name if co.stream else 'General',
                'enrolled_students': student_count,
                'total_graded_marks': len(float_scores),
                'class_average': class_avg,
                'highest_score': class_max,
                'lowest_score': class_min,
                'pass_rate': class_pass_rate,
            })

        # Rank classes by class average descending
        matrix.sort(key=lambda x: x['class_average'], reverse=True)
        for idx, row in enumerate(matrix, 1):
            row['rank'] = idx

        return matrix

    @classmethod
    def get_academic_performance_trends(cls, academic_year=None, user=None):
        """
        Chronological trajectory of exam performance across milestones (e.g. Midterm -> Final).
        """
        exams = Examination.objects.all().order_by('start_date')
        if academic_year:
            exams = exams.filter(academic_year=academic_year)

        trend_data = []
        for ex in exams:
            marks = Mark.objects.filter(exam_subject__examination=ex, marks_obtained__isnull=False, is_absent=False)
            scores = [float(s) for s in marks.values_list('marks_obtained', flat=True)]
            if scores:
                avg_val = round(statistics.mean(scores), 2)
                pass_count = sum(1 for s in scores if s >= 50.0)
                pass_pct = round((pass_count / len(scores)) * 100, 1)
            else:
                avg_val = 0.0
                pass_pct = 0.0

            trend_data.append({
                'examination_id': ex.id,
                'examination_name': ex.name,
                'semester': ex.get_semester_display(),
                'start_date': ex.start_date.strftime('%Y-%m-%d'),
                'average_score': avg_val,
                'pass_rate': pass_pct,
                'total_scores_recorded': len(scores),
            })
        return trend_data

    @classmethod
    def get_student_academic_summary(cls, student_id, user=None):
        """
        Holistic diagnostic summary for an individual student across all courses and marks.
        """
        student = Student.objects.get(pk=student_id)

        # Scoping check if teacher
        if user and getattr(user, 'role', None) and user.role.code == 'TEACHER':
            if hasattr(user, 'teacher_profile'):
                teacher = user.teacher_profile
                has_access = student.enrollments.filter(
                    class_offering__teacher_assignments__teacher=teacher
                ).exists()
                if not has_access:
                    raise PermissionDenied("You may only access academic summaries for students in your assigned classes.")

        marks = Mark.objects.filter(
            student_enrollment__student=student,
            marks_obtained__isnull=False
        ).select_related('exam_subject__subject', 'exam_subject__examination').order_by('-exam_subject__examination__start_date')

        scores = [float(m.marks_obtained) for m in marks if not m.is_absent]
        overall_avg = round(statistics.mean(scores), 2) if scores else 0.0

        # Strengths (scores >= 75%) and Areas for Support (scores < 50%)
        strengths = []
        support_needed = []
        for m in marks:
            score = float(m.marks_obtained) if not m.is_absent else 0.0
            sub_info = {
                'subject': m.exam_subject.subject.name,
                'score': score,
                'max_marks': float(m.exam_subject.max_marks),
                'exam': m.exam_subject.examination.name,
                'is_absent': m.is_absent,
            }
            if score >= 75.0 and not m.is_absent:
                strengths.append(sub_info)
            elif (score < float(m.exam_subject.pass_marks) or m.is_absent):
                support_needed.append(sub_info)

        # Attendance correlation
        att_records = AttendanceRecord.objects.filter(student_enrollment__student=student)
        total_att = att_records.count()
        attended = att_records.filter(status__in=['PRESENT', 'LATE']).count()
        att_rate = round((attended / total_att) * 100, 1) if total_att > 0 else 0.0

        # Constructive advisory narrative
        narrative = []
        if overall_avg >= 80.0:
            narrative.append("Student demonstrates exemplary academic consistency across assessments.")
        elif overall_avg >= 60.0:
            narrative.append("Student exhibits solid foundational progress with potential for higher mastery.")
        elif overall_avg >= 50.0:
            narrative.append("Student is meeting minimum passing benchmarks; targeted revision advised in weaker subjects.")
        else:
            narrative.append("Academic progress is currently below standard benchmarks; pastoral and tutorial support is recommended.")

        if att_rate < 80.0 and total_att > 0:
            narrative.append(f"Noticeable attendance gap ({att_rate}% presence) may be impacting academic outcomes.")

        return {
            'student': student,
            'overall_average': overall_avg,
            'attendance_rate': att_rate,
            'total_assessments': len(marks),
            'strengths': strengths,
            'support_needed': support_needed,
            'narrative': " ".join(narrative),
        }


class AttendanceAnalysisService:
    """
    Offline analytical evaluation of student attendance data.
    Identifies weekday patterns, monthly trends, and non-punitive chronic absence trajectories.
    """

    WEEKDAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

    @classmethod
    def get_attendance_overview(cls, academic_year=None, grade=None, class_offering=None, user=None):
        """
        Computes institutional attendance health metrics across the specified scope.
        """
        records = AttendanceRecord.objects.all().select_related(
            'attendance_session__class_offering__grade', 'student_enrollment__student'
        )
        if academic_year:
            records = records.filter(attendance_session__academic_year=academic_year)
        if grade:
            records = records.filter(attendance_session__class_offering__grade=grade)
        if class_offering:
            records = records.filter(attendance_session__class_offering=class_offering)

        # Teacher scoping
        if user and getattr(user, 'role', None) and user.role.code == 'TEACHER':
            if hasattr(user, 'teacher_profile'):
                teacher = user.teacher_profile
                records = records.filter(
                    attendance_session__class_offering__teacher_assignments__teacher=teacher
                )

        total_records = records.count()
        present_count = records.filter(status='PRESENT').count()
        late_count = records.filter(status='LATE').count()
        absent_count = records.filter(status='ABSENT').count()
        excused_count = records.filter(status='EXCUSED').count()

        if total_records > 0:
            presence_rate = round(((present_count + late_count) / total_records) * 100, 1)
            absence_rate = round((absent_count / total_records) * 100, 1)
            excused_rate = round((excused_count / total_records) * 100, 1)
        else:
            presence_rate = 0.0
            absence_rate = 0.0
            excused_rate = 0.0

        return {
            'total_records': total_records,
            'present_count': present_count,
            'late_count': late_count,
            'absent_count': absent_count,
            'excused_count': excused_count,
            'presence_rate': presence_rate,
            'absence_rate': absence_rate,
            'excused_rate': excused_rate,
        }

    @classmethod
    def get_repeated_absenteeism_patterns(cls, academic_year=None, grade=None, class_offering=None, user=None):
        """
        Analyzes day-of-week correlations and flags recurrent patterns (e.g., market day spikes).
        Flags are strictly advisory to guide supportive counseling rather than punishment.
        """
        records = AttendanceRecord.objects.all().select_related(
            'attendance_session', 'student_enrollment__student'
        )
        if academic_year:
            records = records.filter(attendance_session__academic_year=academic_year)
        if grade:
            records = records.filter(attendance_session__class_offering__grade=grade)
        if class_offering:
            records = records.filter(attendance_session__class_offering=class_offering)

        # Teacher scoping
        if user and getattr(user, 'role', None) and user.role.code == 'TEACHER':
            if hasattr(user, 'teacher_profile'):
                teacher = user.teacher_profile
                records = records.filter(
                    attendance_session__class_offering__teacher_assignments__teacher=teacher
                )

        # 1. Day of Week Absence Frequency
        day_absence_counts = {i: 0 for i in range(5)}  # Mon-Fri
        day_total_counts = {i: 0 for i in range(5)}

        for r in records[:5000]:
            session_date = r.attendance_session.date
            weekday = session_date.weekday()
            if weekday < 5:
                day_total_counts[weekday] += 1
                if r.status == 'ABSENT':
                    day_absence_counts[weekday] += 1

        day_patterns = []
        for i in range(5):
            tot = day_total_counts[i]
            abs_cnt = day_absence_counts[i]
            rate = round((abs_cnt / tot) * 100, 1) if tot > 0 else 0.0
            day_patterns.append({
                'day_name': cls.WEEKDAY_NAMES[i],
                'day_index': i,
                'total_records': tot,
                'absent_count': abs_cnt,
                'absence_rate': rate,
            })

        # 2. Students with frequent unexcused absences (>= 3 absences)
        absentee_query = records.filter(status='ABSENT').values(
            'student_enrollment__student_id',
            'student_enrollment__student__first_name',
            'student_enrollment__student__father_name',
            'student_enrollment__student__admission_number',
            'student_enrollment__class_offering__grade__name',
            'student_enrollment__class_offering__section__name',
        ).annotate(unexcused_count=Count('id')).filter(unexcused_count__gte=3).order_by('-unexcused_count')[:30]

        frequent_absentees = []
        for s in absentee_query:
            frequent_absentees.append({
                'student_id': s['student_enrollment__student_id'],
                'student_name': f"{s['student_enrollment__student__first_name']} {s['student_enrollment__student__father_name']}",
                'admission_number': s['student_enrollment__student__admission_number'],
                'grade_section': f"{s['student_enrollment__class_offering__grade__name']} {s['student_enrollment__class_offering__section__name']}",
                'unexcused_absences': s['unexcused_count'],
                'advisory_recommendation': "Schedule friendly home check-in or pastoral counseling to understand root causes."
            })

        return {
            'day_patterns': day_patterns,
            'frequent_absentees': frequent_absentees,
            'total_flagged_students': len(frequent_absentees),
        }

    @classmethod
    def get_class_attendance_comparison(cls, academic_year=None, grade=None, user=None):
        """
        Ranks class offerings by attendance presence percentage.
        """
        class_offerings = ClassOffering.objects.all().select_related('grade', 'section', 'academic_year')
        if academic_year:
            class_offerings = class_offerings.filter(academic_year=academic_year)
        if grade:
            class_offerings = class_offerings.filter(grade=grade)

        # Teacher scoping
        if user and getattr(user, 'role', None) and user.role.code == 'TEACHER':
            if hasattr(user, 'teacher_profile'):
                teacher = user.teacher_profile
                allowed_co_ids = list(TeacherAssignment.objects.filter(
                    teacher=teacher
                ).values_list('class_offering_id', flat=True).distinct())
                class_offerings = class_offerings.filter(id__in=allowed_co_ids)

        benchmarks = []
        for co in class_offerings:
            records = AttendanceRecord.objects.filter(attendance_session__class_offering=co)
            tot = records.count()
            if tot > 0:
                attended = records.filter(status__in=['PRESENT', 'LATE']).count()
                rate = round((attended / tot) * 100, 1)
            else:
                rate = 0.0

            benchmarks.append({
                'class_offering_id': co.id,
                'class_name': co.display_name,
                'total_records': tot,
                'presence_rate': rate,
            })

        benchmarks.sort(key=lambda x: x['presence_rate'], reverse=True)
        return benchmarks


class ConversationalAssistantService:
    """
    100% Offline Conversational AI Assistant.
    Parses natural language requests deterministically, executes authorized Django queries,
    and returns friendly, structured, markdown responses with strict RBAC enforcement.
    """

    INTENT_PATTERNS = [
        # 1. Student Count / Roster
        ('STUDENT_COUNT', [
            r'how many students', r'total students', r'registered students',
            r'number of students', r'student count', r'student population',
            r'how many active students', r'boys and girls', r'gender breakdown'
        ]),
        # 2. Teacher Count / Info
        ('TEACHER_COUNT', [
            r'how many teachers', r'total teachers', r'number of teachers',
            r'teacher count', r'registered staff', r'teaching staff'
        ]),
        # 3. Lowest Scoring Subjects / Subjects Needing Attention
        ('LOW_SCORING_SUBJECTS', [
            r'lowest average', r'lowest score', r'lowest performing',
            r'subjects? (need|requir|requiring) attention', r'weakest subjects?',
            r'struggling subjects?', r'which subjects.*fail', r'worst subjects?'
        ]),
        # 4. Grade / Class Attendance
        ('GRADE_ATTENDANCE', [
            r'attendance percentage', r'attendance of grade', r'attendance rate',
            r'how is attendance', r'what is the attendance', r'absenteeism rate'
        ]),
        # 5. Grade Academic Summary
        ('GRADE_ACADEMIC_SUMMARY', [
            r'summarize grade', r'summary of grade', r'performance of grade',
            r'how is grade.*performing', r'grade.*results', r'academic summary'
        ]),
        # 6. Chronic Absentees
        ('CHRONIC_ABSENTEES', [
            r'chronic absent', r'frequent absent', r'who is absent',
            r'missing classes', r'repeated absence', r'absentee list'
        ]),
        # 7. Timetable / Schedule
        ('TIMETABLE_INFO', [
            r'period', r'timetable', r'schedule', r'when does.*start',
            r'working days', r'school hours', r'bell schedule'
        ]),
        # 8. Promotion Criteria
        ('PROMOTION_CRITERIA', [
            r'promotion criteri', r'how.*promoted', r'pass mark',
            r'requirements for promotion', r'criteria for grade'
        ]),
        # 9. System Capabilities / Help
        ('HELP', [
            r'what can you do', r'help', r'who are you', r'capabilities',
            r'commands', r'supported questions'
        ]),
    ]

    @classmethod
    def match_intent(cls, text):
        """Identifies the primary query intent using regex pattern analysis."""
        clean_text = text.lower().strip()
        for intent, patterns in cls.INTENT_PATTERNS:
            for pattern in patterns:
                if re.search(pattern, clean_text):
                    return intent
        return 'UNKNOWN'

    @classmethod
    def extract_entities(cls, text):
        """Extracts key academic entities (grade level, section, subject name)."""
        clean_text = text.lower()
        entities = {}

        # Grade extraction (e.g. Grade 9, Grade 10, G11, 12th grade)
        grade_match = re.search(r'(?:grade|g)\s*(\d{1,2})', clean_text)
        if not grade_match:
            grade_match = re.search(r'\b(9|10|11|12)(?:th)?\s*grade\b', clean_text)
        if grade_match:
            entities['grade_level'] = int(grade_match.group(1))

        # Section extraction (e.g. Section A, Sec B)
        sec_match = re.search(r'(?:section|sec)\s*([a-z])', clean_text)
        if sec_match:
            entities['section_name'] = sec_match.group(1).upper()

        # Subject extraction
        known_subjects = Subject.objects.all().values_list('name', 'code')
        for s_name, s_code in known_subjects:
            if s_name.lower() in clean_text or s_code.lower() in clean_text:
                entities['subject_name'] = s_name
                entities['subject_code'] = s_code
                break

        return entities

    @classmethod
    def handle_query(cls, query_text, user):
        """
        Central processing dispatch: matches intent, verifies role-based permissions,
        retrieves actual database facts, and structures a markdown response.
        """
        intent = cls.match_intent(query_text)
        entities = cls.extract_entities(query_text)
        user_role = getattr(user.role, 'code', 'STAFF') if getattr(user, 'role', None) else 'STAFF'

        # Audit logging of AI query
        try:
            AuditLog.objects.create(
                actor=user,
                action='OVERRIDE',
                entity_name='AI Assistant Engine',
                record_id=intent,
                changes_json={'query': query_text[:200], 'intent': intent, 'entities': entities}
            )
        except Exception:
            pass

        # ---------------------------------------------------------------------
        # 1. STUDENT COUNT & DEMOGRAPHICS
        # ---------------------------------------------------------------------
        if intent == 'STUDENT_COUNT':
            total_students = Student.objects.count()
            active_students = Student.objects.filter(status='ACTIVE').count()
            male_count = Student.objects.filter(gender='MALE', status='ACTIVE').count()
            female_count = Student.objects.filter(gender='FEMALE', status='ACTIVE').count()

            # Breakdown by grade
            grade_breakdown = []
            for g in Grade.objects.filter(is_active=True).order_by('level'):
                cnt = StudentEnrollment.objects.filter(class_offering__grade=g, status='ACTIVE').count()
                grade_breakdown.append(f"• **{g.name}:** {cnt} students")

            response_md = (
                f"### 📊 Student Population Statistics\n\n"
                f"• **Total Registered Students:** {total_students}\n"
                f"• **Currently Active Students:** {active_students}\n"
                f"• **Male Students:** {male_count}\n"
                f"• **Female Students:** {female_count}\n\n"
                f"**Active Enrollment by Grade Level:**\n"
                + "\n".join(grade_breakdown) + "\n\n"
                f"*Data sourced directly from live student enrollment records.*"
            )
            return {
                'intent': intent,
                'content': response_md,
                'entities': entities,
                'payload': {'total': total_students, 'active': active_students}
            }

        # ---------------------------------------------------------------------
        # 2. TEACHER COUNT & STAFFING
        # ---------------------------------------------------------------------
        elif intent == 'TEACHER_COUNT':
            total_teachers = Teacher.objects.count()
            active_teachers = Teacher.objects.filter(is_active=True).count()
            teachers_with_classes = TeacherAssignment.objects.values('teacher').distinct().count()

            response_md = (
                f"### 👨‍🏫 Teaching Faculty Statistics\n\n"
                f"• **Total Registered Teachers:** {total_teachers}\n"
                f"• **Active Instructors:** {active_teachers}\n"
                f"• **Teachers with Active Class Allocations:** {teachers_with_classes}\n\n"
                f"Faculty members are allocated to instruction across Grades 9–12 subjects in alignment with "
                f"Majang Zone secondary staffing guidelines."
            )
            return {
                'intent': intent,
                'content': response_md,
                'entities': entities,
                'payload': {'total_teachers': total_teachers, 'active': active_teachers}
            }

        # ---------------------------------------------------------------------
        # 3. LOWEST SCORING SUBJECTS / ATTENTION REQUIRED
        # ---------------------------------------------------------------------
        elif intent == 'LOW_SCORING_SUBJECTS':
            grade_obj = None
            if 'grade_level' in entities:
                grade_obj = Grade.objects.filter(level=entities['grade_level']).first()

            attention_items = AcademicAnalysisService.get_subjects_requiring_attention(grade=grade_obj, user=user)

            if not attention_items:
                response_md = (
                    "### ✅ Academic Performance Diagnostics\n\n"
                    "All evaluated subjects currently meet standard passing thresholds (overall pass rate ≥ 60% "
                    "and average scores at or above passing mark). No critical subjects requiring urgent intervention were detected."
                )
            else:
                rows = []
                for idx, item in enumerate(attention_items[:5], 1):
                    rows.append(
                        f"| {idx} | **{item['subject_name']}** ({item['grade_name']}) | "
                        f"{item['average_score']} / {item['max_marks']} | {item['pass_rate']}% | {item['attention_reason']} |"
                    )

                response_md = (
                    f"### ⚠️ Subjects Requiring Academic Attention\n\n"
                    f"The following {len(attention_items)} subject(s) exhibit sub-optimal pass rates or averages below passing marks:\n\n"
                    f"| # | Subject (Grade) | Average Score | Pass Rate | Diagnostic Reason |\n"
                    f"|---|-----------------|---------------|-----------|-------------------|\n"
                    + "\n".join(rows) + "\n\n"
                    f"**Advisory Recommendations:**\n"
                    f"1. Schedule targeted peer-mentoring and tutorial sessions for foundational topics.\n"
                    f"2. Department heads should conduct syllabus coverage reviews with assigned teachers."
                )
            return {
                'intent': intent,
                'content': response_md,
                'entities': entities,
                'payload': {'flagged_subjects': attention_items}
            }

        # ---------------------------------------------------------------------
        # 4. GRADE / CLASS ATTENDANCE
        # ---------------------------------------------------------------------
        elif intent == 'GRADE_ATTENDANCE':
            grade_obj = None
            if 'grade_level' in entities:
                grade_obj = Grade.objects.filter(level=entities['grade_level']).first()

            # Teacher permission check
            if user_role == 'TEACHER' and grade_obj:
                teacher = getattr(user, 'teacher_profile', None)
                if teacher:
                    teaches_grade = TeacherAssignment.objects.filter(teacher=teacher, class_offering__grade=grade_obj).exists()
                    if not teaches_grade:
                        return {
                            'intent': intent,
                            'content': f"🔒 **Permission Notice:** You are assigned to specific classes. Grade {entities['grade_level']} attendance summary is restricted to authorized administrative staff or assigned instructors.",
                            'entities': entities,
                            'payload': {}
                        }

            overview = AttendanceAnalysisService.get_attendance_overview(grade=grade_obj, user=user)
            title_suffix = f"for {grade_obj.name}" if grade_obj else "Across the School"

            response_md = (
                f"### 📋 Attendance Intelligence {title_suffix}\n\n"
                f"• **Overall Presence Rate:** **{overview['presence_rate']}%**\n"
                f"• **Total Recorded Sessions:** {overview['total_records']}\n"
                f"• **Present:** {overview['present_count']} | **Late:** {overview['late_count']}\n"
                f"• **Confirmed Unexcused Absences:** {overview['absent_count']} ({overview['absence_rate']}%)\n"
                f"• **Excused Absences:** {overview['excused_count']} ({overview['excused_rate']}%)\n\n"
                f"*(Note: In accordance with school policy, Late arrivals count as present for instructional attendance percentage).* "
            )
            return {
                'intent': intent,
                'content': response_md,
                'entities': entities,
                'payload': overview
            }

        # ---------------------------------------------------------------------
        # 5. GRADE ACADEMIC SUMMARY
        # ---------------------------------------------------------------------
        elif intent == 'GRADE_ACADEMIC_SUMMARY':
            grade_obj = None
            if 'grade_level' in entities:
                grade_obj = Grade.objects.filter(level=entities['grade_level']).first()

            # Check teacher permission
            if user_role == 'TEACHER' and grade_obj:
                teacher = getattr(user, 'teacher_profile', None)
                if teacher and not TeacherAssignment.objects.filter(teacher=teacher, class_offering__grade=grade_obj).exists():
                    return {
                        'intent': intent,
                        'content': f"🔒 **Permission Notice:** As a teacher, your access is scoped to your assigned subjects and sections. Academic summaries for Grade {entities['grade_level']} require management permissions.",
                        'entities': entities,
                        'payload': {}
                    }

            matrix = AcademicAnalysisService.get_class_comparison_matrix(grade=grade_obj, user=user)
            if not matrix:
                response_md = f"No verified examination broadsheets or class offerings found for Grade {entities.get('grade_level', 'all')}."
            else:
                grade_label = grade_obj.name if grade_obj else "All Grades"
                rows = []
                for row in matrix:
                    rows.append(f"• **{row['class_name']}:** Average Score: **{row['class_average']}%** | Pass Rate: {row['pass_rate']}% ({row['enrolled_students']} students)")

                response_md = (
                    f"### 📈 Academic Performance Summary: {grade_label}\n\n"
                    f"Comparative performance across active class offerings:\n\n"
                    + "\n".join(rows) + "\n\n"
                    f"*Scores are compiled from verified semester examinations.*"
                )
            return {
                'intent': intent,
                'content': response_md,
                'entities': entities,
                'payload': {'class_comparison': matrix}
            }

        # ---------------------------------------------------------------------
        # 6. CHRONIC ABSENTEEISM REVIEW
        # ---------------------------------------------------------------------
        elif intent == 'CHRONIC_ABSENTEES':
            grade_obj = None
            if 'grade_level' in entities:
                grade_obj = Grade.objects.filter(level=entities['grade_level']).first()

            patterns = AttendanceAnalysisService.get_repeated_absenteeism_patterns(grade=grade_obj, user=user)
            absentees = patterns['frequent_absentees']

            if not absentees:
                response_md = "### ✅ Attendance Audit\n\nNo students currently meet or exceed the threshold for chronic unexcused absences (≥ 3 sessions)."
            else:
                rows = []
                for idx, a in enumerate(absentees[:5], 1):
                    rows.append(f"• **{a['student_name']}** ({a['admission_number']}) - {a['grade_section']}: **{a['unexcused_absences']} absences**")

                response_md = (
                    f"### ⚠️ Students Requiring Attendance Follow-Up\n\n"
                    f"The following {len(absentees)} student(s) have accumulated 3 or more unexcused absences:\n\n"
                    + "\n".join(rows) + "\n\n"
                    f"**Supportive Guidance:** This indicator is strictly non-punitive. It identifies pupils who may require "
                    f"pastoral counseling, health checks, or parental engagement."
                )
            return {
                'intent': intent,
                'content': response_md,
                'entities': entities,
                'payload': patterns
            }

        # ---------------------------------------------------------------------
        # 7. TIMETABLE & SCHEDULE INFORMATION
        # ---------------------------------------------------------------------
        elif intent == 'TIMETABLE_INFO':
            periods = Period.objects.filter(is_active=True).order_by('period_number')
            days = SchoolDay.objects.filter(is_active=True).order_by('order')

            day_names = [d.name for d in days] if days.exists() else ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
            period_lines = []
            for p in periods:
                tag = f" *(Break: {p.get_break_type_display()})*" if p.is_break else ""
                period_lines.append(f"• **{p.name}:** {p.start_time.strftime('%H:%M')} – {p.end_time.strftime('%H:%M')}{tag}")

            response_md = (
                f"### ⏰ School Working Hours & Period Schedule\n\n"
                f"• **Instructional Working Days:** {', '.join(day_names)}\n\n"
                f"**Daily Period Layout:**\n"
                + ("\n".join(period_lines) if period_lines else "• Standard Schedule: 08:30 – 15:30 (Periods 1–7)") + "\n\n"
                f"*Schedules can be modified in the Timetable Management module.*"
            )
            return {
                'intent': intent,
                'content': response_md,
                'entities': entities,
                'payload': {'working_days': day_names}
            }

        # ---------------------------------------------------------------------
        # 8. PROMOTION CRITERIA POLICY
        # ---------------------------------------------------------------------
        elif intent == 'PROMOTION_CRITERIA':
            criteria = PromotionCriteria.objects.filter(is_active=True, is_default=True).first()
            if not criteria:
                criteria = PromotionCriteria.objects.filter(is_active=True).first()

            min_avg = criteria.minimum_average if criteria else 50.0
            max_fail = criteria.max_failing_subjects if criteria else 2
            core_req = "Mandatory" if (criteria and criteria.require_all_core_passed) else "Standard"

            response_md = (
                f"### 📜 Majang Secondary School Promotion Policy\n\n"
                f"In accordance with regional curriculum guidelines:\n"
                f"• **Minimum Passing Average:** **{min_avg}%** overall academic average.\n"
                f"• **Maximum Permitted Failing Subjects:** **{max_fail} subjects**.\n"
                f"• **Core Curriculum Passing:** {core_req}.\n"
                f"• **Grade 10 to Grade 11 Transition:** Students must achieve promotion and select either **Natural Sciences** or **Social Sciences** stream.\n"
                f"• **Grade 12 Graduation:** Requires completion of secondary curriculum and national examination eligibility.\n\n"
                f"*Note: AI insights are advisory. All final promotion outcomes are authorized by the School Principal and Examination Committee.*"
            )
            return {
                'intent': intent,
                'content': response_md,
                'entities': entities,
                'payload': {'min_average': float(min_avg), 'max_failing': max_fail}
            }

        # ---------------------------------------------------------------------
        # 9. HELP & CAPABILITIES
        # ---------------------------------------------------------------------
        elif intent == 'HELP':
            response_md = (
                f"### 🤖 Local AI School Assistant Capabilities\n\n"
                f"I am your offline academic assistant, operating directly on the Majang secondary school server. "
                f"I can answer questions regarding:\n\n"
                f"1. **Student Demographics:** *\"How many students are registered?\"*\n"
                f"2. **Subject Diagnostics:** *\"Which subjects have the lowest average scores?\"*\n"
                f"3. **Attendance Intelligence:** *\"What is the attendance percentage of Grade 10?\"*\n"
                f"4. **Academic Summaries:** *\"Summarize Grade 11 academic performance.\"*\n"
                f"5. **Staffing & Faculty:** *\"How many teachers are registered?\"*\n"
                f"6. **Absenteeism Monitoring:** *\"Who are the frequent absentees?\"*\n"
                f"7. **Timetables & Bell Schedule:** *\"What are the school periods and working days?\"*\n"
                f"8. **Promotion Rules:** *\"What are the promotion criteria from Grade 10 to 11?\"*\n\n"
                f"*All responses respect your user permissions and use actual database records.*"
            )
            return {
                'intent': intent,
                'content': response_md,
                'entities': entities,
                'payload': {}
            }

        # ---------------------------------------------------------------------
        # 10. UNKNOWN / FALLBACK
        # ---------------------------------------------------------------------
        else:
            response_md = (
                f"I understood your question, but could not match it to a verified data query.\n\n"
                f"**Here are questions I can answer right now:**\n"
                f"• *\"How many students are registered?\"*\n"
                f"• *\"Which subjects have the lowest average scores?\"*\n"
                f"• *\"What is the attendance percentage of Grade 10?\"*\n"
                f"• *\"Summarize Grade 11 academic performance.\"*\n"
                f"• *\"How many teachers are registered?\"*\n"
                f"• *\"What are the school periods and working days?\"*\n"
                f"• *\"What are the promotion criteria?\"*\n\n"
                f"Feel free to click any of the suggested prompt buttons above."
            )
            return {
                'intent': 'UNKNOWN',
                'content': response_md,
                'entities': entities,
                'payload': {}
            }


class AIReportService:
    """
    Generates structured AI academic and attendance intelligence reports
    with support for streaming PDF (ReportLab) and Excel (OpenPyXL) exports.
    """

    @classmethod
    def generate_student_dossier(cls, student_id, user=None):
        return AcademicAnalysisService.get_student_academic_summary(student_id, user=user)

    @classmethod
    def generate_class_dossier(cls, class_offering_id, user=None):
        co = ClassOffering.objects.get(pk=class_offering_id)
        matrix = AcademicAnalysisService.get_class_comparison_matrix(academic_year=co.academic_year, grade=co.grade, user=user)
        target_row = next((r for r in matrix if r['class_offering_id'] == co.id), None)
        return {
            'class_offering': co,
            'summary': target_row,
            'subjects': AcademicAnalysisService.get_subject_averages(class_offering=co, user=user),
            'attendance': AttendanceAnalysisService.get_attendance_overview(class_offering=co, user=user),
        }

    @classmethod
    def export_ai_summary_pdf(cls, title, sections, user=None):
        """
        Builds a vector PDF using ReportLab with Ministry/School headers and AI disclaimer.
        """
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=36,
            rightMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        header_title = ParagraphStyle(
            'AITitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=16,
            leading=20,
            textColor=colors.HexColor('#1E3A8A'),
            alignment=1
        )
        subtitle = ParagraphStyle(
            'AISubtitle',
            parent=styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=10,
            leading=14,
            textColor=colors.HexColor('#4B5563'),
            alignment=1
        )
        disclaimer = ParagraphStyle(
            'AIDisclaimer',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=8,
            leading=11,
            textColor=colors.HexColor('#6B7280'),
            alignment=1
        )
        body = ParagraphStyle(
            'AIBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            leading=13,
            textColor=colors.HexColor('#1F2937')
        )

        elements = [
            Paragraph("MAJANG ZONE SECONDARY EDUCATION BUREAU", subtitle),
            Paragraph("SMART SCHOOL MANAGEMENT SYSTEM — AI INTELLIGENCE DOSSIER", subtitle),
            Spacer(1, 6),
            Paragraph(title.upper(), header_title),
            Spacer(1, 4),
            Paragraph(f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M')} | Offline Local Intelligence Engine", subtitle),
            Spacer(1, 8),
            Paragraph("*Advisory Notice: These AI analytics are decision-support insights derived from verified academic records. Final administrative and promotion determinations remain with school leadership.", disclaimer),
            Spacer(1, 14),
        ]

        for sec_title, table_data in sections:
            elements.append(Paragraph(f"<b>{sec_title}</b>", styles['Heading3']))
            elements.append(Spacer(1, 4))
            if table_data:
                t = Table(table_data, colWidths=None)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E3A8A')),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 8),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#D1D5DB')),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F9FAFB')])
                ]))
                elements.append(t)
            elements.append(Spacer(1, 12))

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

    @classmethod
    def export_ai_summary_excel(cls, sheet_name, headers, rows):
        """
        Builds a styled Excel workbook using OpenPyXL.
        """
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = sheet_name[:30]

        # Header style
        header_font = Font(name='Calibri', size=11, bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='1E3A8A', end_color='1E3A8A', fill_type='solid')
        border_thin = Border(
            left=Side(style='thin', color='E5E7EB'),
            right=Side(style='thin', color='E5E7EB'),
            top=Side(style='thin', color='E5E7EB'),
            bottom=Side(style='thin', color='E5E7EB'),
        )

        for col_idx, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=h)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center', vertical='center')

        for r_idx, row in enumerate(rows, 2):
            for c_idx, val in enumerate(row, 1):
                cell = ws.cell(row=r_idx, column=c_idx, value=val)
                cell.border = border_thin
                cell.font = Font(name='Calibri', size=10)

        for col in ws.columns:
            max_len = max(len(str(cell.value or '')) for cell in col)
            col_letter = get_column_letter(col[0].column)
            ws.column_dimensions[col_letter].width = max(max_len + 4, 12)

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer.getvalue()
