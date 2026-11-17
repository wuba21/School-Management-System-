from django.db import models
from django.conf import settings

class ImmutableAuditLogQuerySet(models.QuerySet):
    """
    Prevents bulk deletion and bulk modification of AuditLog records.
    """
    def delete(self):
        raise PermissionError("AuditLog records are immutable: bulk deletion via QuerySet is prohibited.")

    def update(self, **kwargs):
        raise PermissionError("AuditLog records are immutable: updates via QuerySet are prohibited.")


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

    objects = ImmutableAuditLogQuerySet.as_manager()

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

    def delete(self, *args, **kwargs):
        """AuditLog records are strictly immutable and cannot be deleted."""
        raise PermissionError("AuditLog records are immutable and cannot be deleted.")

    def __str__(self):
        user_str = self.actor.username if self.actor else "System"
        return f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] {user_str} - {self.action} on {self.entity_name} ({self.record_id})"



class LoginAttempt(models.Model):
    """
    Persistent record of every login event (successful, failed, or blocked).
    Complements the cache-based IP lockout with an immutable audit trail.
    """
    STATUS_SUCCESS = 'SUCCESS'
    STATUS_FAILED = 'FAILED'
    STATUS_LOCKED = 'LOCKED'
    STATUS_CHOICES = [
        (STATUS_SUCCESS, 'Successful Login'),
        (STATUS_FAILED, 'Failed Attempt'),
        (STATUS_LOCKED, 'Blocked — IP Locked Out'),
    ]

    username_attempted = models.CharField(max_length=150, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='login_attempts',
        help_text='Authenticated user (populated only on success)',
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        verbose_name = 'Login Attempt'
        verbose_name_plural = 'Login Attempts'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['ip_address', 'timestamp']),
            models.Index(fields=['status', 'timestamp']),
        ]

    def __str__(self):
        return (
            f"[{self.timestamp.strftime('%Y-%m-%d %H:%M')}] "
            f"{self.status} — {self.username_attempted} from {self.ip_address}"
        )
