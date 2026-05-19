"""
apps/notifications/notification_log_models.py

Append-only audit row for EVERY notification send decision —
including ones that DIDN'T send because the user opted out.

Critical for compliance: when a regulator asks "why did you send
this user a marketing email after they unsubscribed?", the answer
isn't "look at our send logs and notice the absence." The answer
is "here's the log row showing we DECIDED NOT to send, with the
reason." Negative-confirmation is the compliance artifact.

For successful sends, the audit row proves what we delivered + when,
which combined with NotificationPreference history shows that we
were honouring stated preferences at the time of send.

Retention: 90 days (set via beat task, like LoginAttempt) — long
enough for typical compliance audits, short enough to bound storage.
"""
from django.conf import settings
from django.db import models


User = settings.AUTH_USER_MODEL


class NotificationLog(models.Model):
    """One row per send DECISION (sent or suppressed)."""
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notification_logs',
    )
    # Store email verbatim too — covers the case where we logged a
    # decision but the user row was later anonymised via data_rights.
    email = models.EmailField(blank=True)
    category = models.CharField(max_length=40, db_index=True)
    channel = models.CharField(max_length=10, default='email')

    # TRUE = we called send_mail / push, FALSE = preference-blocked.
    sent = models.BooleanField(db_index=True)
    # Code from preferences.Reason (e.g. 'allowed', 'suppressed',
    # 'category_disabled', 'quiet_hours').
    reason = models.CharField(max_length=40)
    subject = models.CharField(max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['email', '-created_at']),
            models.Index(fields=['category', 'sent', '-created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        outcome = 'sent' if self.sent else f'blocked:{self.reason}'
        return f'{self.email} · {self.category} → {outcome}'
