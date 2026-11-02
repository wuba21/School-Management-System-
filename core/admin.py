from django.contrib import admin
from .models import AuditLog

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'actor', 'action', 'entity_name', 'record_id', 'ip_address')
    list_filter = ('action', 'entity_name', 'timestamp')
    search_fields = ('entity_name', 'record_id', 'actor__username')
    readonly_fields = ('actor', 'action', 'entity_name', 'record_id', 'ip_address', 'changes_json', 'timestamp')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
