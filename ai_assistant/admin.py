from django.contrib import admin
from ai_assistant.models import ChatConversation, ChatMessage, AcademicInsight


@admin.register(ChatConversation)
class ChatConversationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('title', 'user__username', 'user__first_name', 'user__last_name')


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('conversation', 'sender', 'intent', 'timestamp')
    list_filter = ('sender', 'intent', 'timestamp')
    search_fields = ('content', 'intent', 'conversation__user__username')


@admin.register(AcademicInsight)
class AcademicInsightAdmin(admin.ModelAdmin):
    list_display = ('title', 'insight_type', 'severity', 'grade', 'subject', 'is_resolved', 'created_at')
    list_filter = ('insight_type', 'severity', 'is_resolved', 'grade')
    search_fields = ('title', 'summary', 'recommendation')
