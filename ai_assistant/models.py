"""
Database Models for AI-Powered School Assistant.
Stores user chat sessions, messages, and analytical insights.
"""

from django.db import models
from django.conf import settings
from academics.models import AcademicYear, Grade, ClassOffering, Subject


class ChatConversation(models.Model):
    """
    User conversation session with the local School Assistant.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_conversations'
    )
    title = models.CharField(max_length=200, default='New Conversation')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'AI Conversation'
        verbose_name_plural = 'AI Conversations'
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.user.username} - {self.title} ({self.created_at.strftime('%Y-%m-%d %H:%M')})"


class ChatMessage(models.Model):
    """
    Individual message turn in an offline AI conversation.
    """
    SENDER_CHOICES = [
        ('USER', 'User Query'),
        ('ASSISTANT', 'AI Assistant Response'),
        ('SYSTEM', 'System Notification'),
    ]

    conversation = models.ForeignKey(
        ChatConversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    sender = models.CharField(max_length=20, choices=SENDER_CHOICES)
    content = models.TextField(help_text="Plaintext or Markdown response content")
    intent = models.CharField(max_length=100, blank=True, help_text="Detected query intent code")
    entities = models.JSONField(default=dict, blank=True, help_text="Parsed query entities (grade, subject, section)")
    data_payload = models.JSONField(default=dict, blank=True, help_text="Structured data returned with the answer")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'AI Chat Message'
        verbose_name_plural = 'AI Chat Messages'
        ordering = ['timestamp']

    def __str__(self):
        return f"[{self.sender}] {self.content[:50]}..."


class AcademicInsight(models.Model):
    """
    Advisory academic performance, attendance, or operational insight.
    AI generates advisory intelligence; final decisions remain with human staff.
    """
    INSIGHT_TYPE_CHOICES = [
        ('SUBJECT_ATTENTION', 'Subject Requiring Attention'),
        ('CLASS_VARIANCE', 'Class Performance Variance'),
        ('ATTENDANCE_PATTERN', 'Repeated Absence Pattern'),
        ('PERFORMANCE_TREND', 'Academic Trend Trajectory'),
        ('CURRICULUM_GAP', 'Curriculum Coverage Gap'),
    ]

    SEVERITY_CHOICES = [
        ('INFO', 'Informational / Advisory'),
        ('WARNING', 'Moderate Attention Recommended'),
        ('CRITICAL', 'Urgent Pastoral / Academic Action'),
    ]

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='ai_insights'
    )
    grade = models.ForeignKey(
        Grade,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='ai_insights'
    )
    class_offering = models.ForeignKey(
        ClassOffering,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='ai_insights'
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='ai_insights'
    )
    insight_type = models.CharField(max_length=50, choices=INSIGHT_TYPE_CHOICES)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='INFO')
    title = models.CharField(max_length=200)
    summary = models.TextField()
    recommendation = models.TextField(blank=True, help_text="Constructive, pedagogical suggestion")
    metrics = models.JSONField(default=dict, blank=True, help_text="Quantitative backing metrics (average, pass rate, count)")
    is_resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Academic Insight'
        verbose_name_plural = 'Academic Insights'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_severity_display()}] {self.title}"
