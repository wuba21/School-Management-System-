"""
View Controllers for AI-Powered School Assistant.
Operates 100% offline, enforcing RBAC and data privacy.
"""

import json
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse, HttpResponse
from django.contrib import messages
from django.views.decorators.http import require_POST
from django.utils import timezone

from accounts.decorators import (
    any_authenticated_role_required,
    management_staff_required,
)
from ai_assistant.models import ChatConversation, ChatMessage, AcademicInsight
from ai_assistant.forms import (
    ChatQueryForm,
    AcademicAnalysisFilterForm,
    AttendanceAnalysisFilterForm,
    AIReportExportForm,
)
from ai_assistant.services import (
    AcademicAnalysisService,
    AttendanceAnalysisService,
    ConversationalAssistantService,
    AIReportService,
)
from academics.models import AcademicYear, Grade, ClassOffering, Subject
from students.models import Student


# -----------------------------------------------------------------------------
# 1. AI ASSISTANT DASHBOARD
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def ai_dashboard_view(request):
    """
    Main landing hub for the offline AI Assistant.
    Provides executive diagnostic indicators, attention alerts, and navigation.
    """
    current_year = AcademicYear.objects.filter(is_current=True).first()

    # 1. Quick Stats
    attention_subjects = AcademicAnalysisService.get_subjects_requiring_attention(
        academic_year=current_year, user=request.user
    )
    attendance_overview = AttendanceAnalysisService.get_attendance_overview(
        academic_year=current_year, user=request.user
    )
    absenteeism_data = AttendanceAnalysisService.get_repeated_absenteeism_patterns(
        academic_year=current_year, user=request.user
    )
    class_matrix = AcademicAnalysisService.get_class_comparison_matrix(
        academic_year=current_year, user=request.user
    )

    # Calculate overall average across classes
    avg_scores = [c['class_average'] for c in class_matrix if c['class_average'] > 0]
    school_academic_avg = round(sum(avg_scores) / len(avg_scores), 1) if avg_scores else 0.0

    context = {
        'active_menu': 'ai_assistant',
        'page_title': 'AI Assistant & School Intelligence',
        'current_year': current_year,
        'school_academic_avg': school_academic_avg,
        'presence_rate': attendance_overview['presence_rate'],
        'attention_count': len(attention_subjects),
        'frequent_absentees_count': absenteeism_data['total_flagged_students'],
        'attention_subjects': attention_subjects[:5],
        'top_classes': class_matrix[:5],
        'user_role': request.user.role.code if request.user.role else 'STAFF',
    }
    return render(request, 'ai_assistant/dashboard.html', context)


# -----------------------------------------------------------------------------
# 2. ACADEMIC PERFORMANCE ANALYSIS
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def academic_analysis_view(request):
    """
    Deep-dive statistical analysis of student examination performance,
    identifying subjects requiring attention and benchmarking class sections.
    """
    form = AcademicAnalysisFilterForm(request.GET, user=request.user)
    academic_year = None
    grade = None
    class_offering = None

    if form.is_valid():
        academic_year = form.cleaned_data.get('academic_year')
        grade = form.cleaned_data.get('grade')
        class_offering = form.cleaned_data.get('class_offering')

    subject_stats = AcademicAnalysisService.get_subject_averages(
        academic_year=academic_year,
        grade=grade,
        class_offering=class_offering,
        user=request.user
    )
    attention_subjects = AcademicAnalysisService.get_subjects_requiring_attention(
        academic_year=academic_year,
        grade=grade,
        user=request.user
    )
    class_matrix = AcademicAnalysisService.get_class_comparison_matrix(
        academic_year=academic_year,
        grade=grade,
        user=request.user
    )
    trends = AcademicAnalysisService.get_academic_performance_trends(
        academic_year=academic_year,
        user=request.user
    )

    context = {
        'active_menu': 'ai_academic',
        'page_title': 'AI Academic Performance Analysis',
        'form': form,
        'subject_stats': subject_stats,
        'attention_subjects': attention_subjects,
        'class_matrix': class_matrix,
        'trends': trends,
        'trends_json': json.dumps(trends),
        'total_analyzed_subjects': len(subject_stats),
    }
    return render(request, 'ai_assistant/academic_analysis.html', context)


# -----------------------------------------------------------------------------
# 3. ATTENDANCE INTELLIGENCE ANALYSIS
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def attendance_analysis_view(request):
    """
    Evaluates institutional attendance health, identifies repeated absenteeism patterns,
    and highlights day-of-week correlations without punitive labeling.
    """
    form = AttendanceAnalysisFilterForm(request.GET, user=request.user)
    academic_year = None
    grade = None
    class_offering = None

    if form.is_valid():
        academic_year = form.cleaned_data.get('academic_year')
        grade = form.cleaned_data.get('grade')
        class_offering = form.cleaned_data.get('class_offering')

    overview = AttendanceAnalysisService.get_attendance_overview(
        academic_year=academic_year,
        grade=grade,
        class_offering=class_offering,
        user=request.user
    )
    patterns = AttendanceAnalysisService.get_repeated_absenteeism_patterns(
        academic_year=academic_year,
        grade=grade,
        class_offering=class_offering,
        user=request.user
    )
    class_benchmarks = AttendanceAnalysisService.get_class_attendance_comparison(
        academic_year=academic_year,
        grade=grade,
        user=request.user
    )

    context = {
        'active_menu': 'ai_attendance',
        'page_title': 'AI Attendance & Absenteeism Analysis',
        'form': form,
        'overview': overview,
        'day_patterns': patterns['day_patterns'],
        'day_patterns_json': json.dumps(patterns['day_patterns']),
        'frequent_absentees': patterns['frequent_absentees'],
        'class_benchmarks': class_benchmarks,
    }
    return render(request, 'ai_assistant/attendance_analysis.html', context)


# -----------------------------------------------------------------------------
# 4. CONVERSATIONAL SCHOOL ASSISTANT (CHAT)
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def chat_assistant_view(request):
    """
    Interactive conversational assistant console.
    Handles AJAX queries for instantaneous responses as well as standard POST.
    """
    # Retrieve or create active conversation for current user
    conversation, _ = ChatConversation.objects.get_or_create(
        user=request.user,
        is_active=True,
        defaults={'title': 'School Assistant Inquiry'}
    )

    if request.method == 'POST':
        form = ChatQueryForm(request.POST)
        if form.is_valid():
            query_text = form.cleaned_data['query'].strip()

            # Record user turn
            user_msg = ChatMessage.objects.create(
                conversation=conversation,
                sender='USER',
                content=query_text
            )

            # Process query via local NLP engine
            result = ConversationalAssistantService.handle_query(query_text, user=request.user)

            # Record assistant turn
            assistant_msg = ChatMessage.objects.create(
                conversation=conversation,
                sender='ASSISTANT',
                content=result['content'],
                intent=result.get('intent', ''),
                entities=result.get('entities', {}),
                data_payload=result.get('payload', {})
            )

            # If AJAX request, return JSON
            if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('format') == 'json':
                return JsonResponse({
                    'status': 'success',
                    'query': query_text,
                    'intent': result.get('intent'),
                    'response': result['content'],
                    'timestamp': assistant_msg.timestamp.strftime('%H:%M'),
                })

            return redirect('ai_chat_assistant')
    else:
        form = ChatQueryForm()

    # Load recent conversation history (last 20 turns)
    messages_history = conversation.messages.all().order_by('timestamp')[:30]

    context = {
        'active_menu': 'ai_chat',
        'page_title': 'AI Conversational School Assistant',
        'conversation': conversation,
        'messages_history': messages_history,
        'form': form,
    }
    return render(request, 'ai_assistant/chat.html', context)


@require_POST
@any_authenticated_role_required
def chat_clear_history_view(request):
    """Clears previous message history for the active chat conversation."""
    conversation = ChatConversation.objects.filter(user=request.user, is_active=True).first()
    if conversation:
        conversation.messages.all().delete()
        messages.success(request, "Conversation history has been cleared.")
    return redirect('ai_chat_assistant')


# -----------------------------------------------------------------------------
# 5. AI REPORT GENERATOR & EXPORTS
# -----------------------------------------------------------------------------

@any_authenticated_role_required
def ai_report_generator_view(request):
    """
    Report generation console allowing authorized personnel to generate
    and download AI intelligence dossiers in PDF or Excel formats.
    """
    if request.method == 'POST':
        form = AIReportExportForm(request.POST)
        if form.is_valid():
            report_type = form.cleaned_data['report_type']
            export_format = form.cleaned_data['format']
            student = form.cleaned_data.get('student')
            class_offering = form.cleaned_data.get('class_offering')
            subject = form.cleaned_data.get('subject')

            # 1. Student Academic Summary Report
            if report_type == 'STUDENT_SUMMARY':
                if not student:
                    messages.error(request, "Please select a specific student to generate their academic summary.")
                    return redirect('ai_report_generator')

                summary = AcademicAnalysisService.get_student_academic_summary(student.id, user=request.user)

                if export_format == 'PDF':
                    sections = [
                        ("1. Student Profile & Diagnostic Overview", [
                            ["Metric", "Value"],
                            ["Student Name", summary['student'].full_name],
                            ["Admission Number", summary['student'].admission_number],
                            ["Overall Academic Average", f"{summary['overall_average']}%"],
                            ["Attendance Presence Rate", f"{summary['attendance_rate']}%"],
                            ["Diagnostic Narrative", summary['narrative']],
                        ]),
                        ("2. High Academic Achievements (Strengths >= 75%)", [
                            ["Subject", "Assessment", "Score Attained", "Max Marks"]
                        ] + [
                            [s['subject'], s['exam'], str(s['score']), str(s['max_marks'])]
                            for s in summary['strengths']
                        ] if summary['strengths'] else [["No assessments >= 75% recorded", "-", "-", "-"]]),
                        ("3. Areas Requiring Targeted Support (Scores < Pass Mark)", [
                            ["Subject", "Assessment", "Score Attained", "Max Marks"]
                        ] + [
                            [s['subject'], s['exam'], str(s['score']), str(s['max_marks'])]
                            for s in summary['support_needed']
                        ] if summary['support_needed'] else [["All subjects meeting or exceeding pass marks", "-", "-", "-"]]),
                    ]
                    pdf_bytes = AIReportService.export_ai_summary_pdf(
                        title=f"Student Academic Summary: {summary['student'].full_name}",
                        sections=sections,
                        user=request.user
                    )
                    response = HttpResponse(pdf_bytes, content_type='application/pdf')
                    response['Content-Disposition'] = f'attachment; filename="AI_Summary_{summary["student"].admission_number.replace("/", "_")}.pdf"'
                    return response

                else:  # Excel
                    headers = ["Subject", "Assessment", "Score Attained", "Max Marks", "Result Category"]
                    rows = []
                    for s in summary['strengths']:
                        rows.append([s['subject'], s['exam'], s['score'], s['max_marks'], 'Strength'])
                    for s in summary['support_needed']:
                        rows.append([s['subject'], s['exam'], s['score'], s['max_marks'], 'Needs Support'])
                    excel_bytes = AIReportService.export_ai_summary_excel("Student Summary", headers, rows)
                    response = HttpResponse(excel_bytes, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                    response['Content-Disposition'] = f'attachment; filename="AI_Summary_{summary["student"].admission_number.replace("/", "_")}.xlsx"'
                    return response

            # 2. Class Section Analysis Report
            elif report_type == 'CLASS_DOSSIER':
                if not class_offering:
                    messages.error(request, "Please select a class section to generate its performance dossier.")
                    return redirect('ai_report_generator')

                dossier = AIReportService.generate_class_dossier(class_offering.id, user=request.user)

                if export_format == 'PDF':
                    co = dossier['class_offering']
                    s_summary = dossier['summary'] or {}
                    att = dossier['attendance']
                    sections = [
                        ("1. Class Section Overview", [
                            ["Class Name", co.display_name],
                            ["Enrolled Students", str(s_summary.get('enrolled_students', 0))],
                            ["Class Academic Average", f"{s_summary.get('class_average', 0.0)}%"],
                            ["Overall Pass Rate", f"{s_summary.get('pass_rate', 0.0)}%"],
                            ["Attendance Rate", f"{att['presence_rate']}%"],
                        ]),
                        ("2. Subject Score Breakdown", [
                            ["Subject", "Sat Count", "Average Score", "Pass Rate", "Diagnostic Status"]
                        ] + [
                            [sub['subject_name'], str(sub['sat_count']), f"{sub['average_score']}%", f"{sub['pass_rate']}%", sub['attention_reason']]
                            for sub in dossier['subjects']
                        ] if dossier['subjects'] else [["No subject marks recorded", "-", "-", "-", "-"]]),
                    ]
                    pdf_bytes = AIReportService.export_ai_summary_pdf(
                        title=f"Class Performance Dossier: {co.display_name}",
                        sections=sections,
                        user=request.user
                    )
                    response = HttpResponse(pdf_bytes, content_type='application/pdf')
                    response['Content-Disposition'] = f'attachment; filename="Class_Dossier_{co.display_name.replace(" ", "_")}.pdf"'
                    return response

                else:  # Excel
                    headers = ["Subject", "Enrolled", "Sat Count", "Average Score", "Median", "Max Score", "Min Score", "Pass Rate (%)", "Diagnostic Status"]
                    rows = []
                    for sub in dossier['subjects']:
                        rows.append([
                            sub['subject_name'], sub['total_enrolled'], sub['sat_count'],
                            sub['average_score'], sub['median_score'], sub['max_score'],
                            sub['min_score'], sub['pass_rate'], sub['attention_reason']
                        ])
                    excel_bytes = AIReportService.export_ai_summary_excel("Class Dossier", headers, rows)
                    response = HttpResponse(excel_bytes, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                    response['Content-Disposition'] = f'attachment; filename="Class_Dossier_{class_offering.display_name.replace(" ", "_")}.xlsx"'
                    return response

            # 3. Subject Diagnostic Report
            elif report_type == 'SUBJECT_DIAGNOSTIC':
                subject_stats = AcademicAnalysisService.get_subject_averages(user=request.user)
                if subject:
                    subject_stats = [s for s in subject_stats if s['subject_id'] == subject.id]

                if export_format == 'PDF':
                    sections = [
                        ("Subject Performance Diagnostic Matrix", [
                            ["Subject", "Grade", "Sat Count", "Average", "Pass Rate", "Status"]
                        ] + [
                            [s['subject_name'], s['grade_name'], str(s['sat_count']), f"{s['average_score']}%", f"{s['pass_rate']}%", s['attention_reason']]
                            for s in subject_stats
                        ])
                    ]
                    pdf_bytes = AIReportService.export_ai_summary_pdf(
                        title="Subject Performance & Difficulty Diagnostic",
                        sections=sections,
                        user=request.user
                    )
                    response = HttpResponse(pdf_bytes, content_type='application/pdf')
                    response['Content-Disposition'] = 'attachment; filename="Subject_Diagnostic_Report.pdf"'
                    return response
                else:
                    headers = ["Subject", "Grade", "Exam", "Sat Count", "Average", "Pass Rate", "Std Dev", "Status"]
                    rows = [
                        [s['subject_name'], s['grade_name'], s['examination_name'], s['sat_count'], s['average_score'], s['pass_rate'], s['std_dev'], s['attention_reason']]
                        for s in subject_stats
                    ]
                    excel_bytes = AIReportService.export_ai_summary_excel("Subject Diagnostic", headers, rows)
                    response = HttpResponse(excel_bytes, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                    response['Content-Disposition'] = 'attachment; filename="Subject_Diagnostic_Report.xlsx"'
                    return response

            # 4. Attendance Patterns Report
            elif report_type == 'ATTENDANCE_PATTERNS':
                patterns = AttendanceAnalysisService.get_repeated_absenteeism_patterns(user=request.user)

                if export_format == 'PDF':
                    sections = [
                        ("1. Weekday Absence Distribution", [
                            ["Weekday", "Total Recorded", "Absences", "Absence Rate"]
                        ] + [
                            [d['day_name'], str(d['total_records']), str(d['absent_count']), f"{d['absence_rate']}%"]
                            for d in patterns['day_patterns']
                        ]),
                        ("2. Students with Repeated Unexcused Absences (>= 3)", [
                            ["Student Name", "Admission No", "Grade & Section", "Absence Count", "Pastoral Recommendation"]
                        ] + [
                            [a['student_name'], a['admission_number'], a['grade_section'], str(a['unexcused_absences']), a['advisory_recommendation']]
                            for a in patterns['frequent_absentees']
                        ] if patterns['frequent_absentees'] else [["No students meeting chronic absence threshold", "-", "-", "-", "-"]])
                    ]
                    pdf_bytes = AIReportService.export_ai_summary_pdf(
                        title="Attendance & Absenteeism Pattern Analysis",
                        sections=sections,
                        user=request.user
                    )
                    response = HttpResponse(pdf_bytes, content_type='application/pdf')
                    response['Content-Disposition'] = 'attachment; filename="Attendance_Pattern_Analysis.pdf"'
                    return response
                else:
                    headers = ["Student Name", "Admission Number", "Class", "Unexcused Absences", "Guidance Note"]
                    rows = [
                        [a['student_name'], a['admission_number'], a['grade_section'], a['unexcused_absences'], a['advisory_recommendation']]
                        for a in patterns['frequent_absentees']
                    ]
                    excel_bytes = AIReportService.export_ai_summary_excel("Attendance Patterns", headers, rows)
                    response = HttpResponse(excel_bytes, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                    response['Content-Disposition'] = 'attachment; filename="Attendance_Pattern_Analysis.xlsx"'
                    return response

    else:
        form = AIReportExportForm()

    context = {
        'active_menu': 'ai_reports',
        'page_title': 'AI Intelligence Report Generator',
        'form': form,
    }
    return render(request, 'ai_assistant/report_generator.html', context)
