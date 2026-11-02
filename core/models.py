from django.db import models
from django.conf import settings

class AuditLog(models.Model):
    """
    Immutable audit trail for monitoring sensitive administrative and academic actions.
    """
    ACTION_CHOICES = [
        ('CREATE', 'Create Record'),
        ('UPDATE', 'Update Record'),
        ('DELETE', 'Delete Record'),
        ('LOGIN', 'User Login'),
        ('OVERRIDE', 'Administrative Override'),
    ]

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='audit_logs',
        help_text="User who initiated this action"
    )
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    entity_name = models.CharField(max_length=100, help_text="Table or model name affected (e.g. Mark, Student)")
    record_id = models.CharField(max_length=50, blank=True, help_text="Primary key of modified record")
    ip_address = models.GenericIPAddressField(null=True, blank=True, help_text="Client IP address on school LAN")
    changes_json = models.JSONField(default=dict, blank=True, help_text="Structured JSON diff of changes (old vs new)")
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Audit Log'
        verbose_name_plural = 'Audit Logs'
        ordering = ['-timestamp']

    def __str__(self):
        user_str = self.actor.username if self.actor else "System"
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {user_str} - {self.action} on {self.entity_name} ({self.record_id})"
