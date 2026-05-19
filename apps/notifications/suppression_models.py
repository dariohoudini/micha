"""
apps/notifications/suppression_models.py

Suppression list — email addresses we MUST NOT send to. Hard block
across all categories regardless of preferences.

Three sources of entries:

  • Hard bounce from the email provider. When a domain MX rejects
    permanently, sending again degrades our deliverability
    reputation for everyone else.

  • Spam complaint (recipient marked our email as junk in their
    client). Continuing to send violates RFC 8058 best practices
    and tanks reputation.

  • Manual unsubscribe via the one-click footer link (RFC 8058,
    CAN-SPAM Section 5(a)(4)(A), GDPR Art. 7(3) consent withdrawal).

The model is intentionally minimal — email address + reason + when —
so it's cheap to look up on every send.
"""
from django.db import models


class SuppressedEmail(models.Model):
    email = models.EmailField(unique=True, db_index=True)
    reason = models.CharField(
        max_length=80,
        help_text='unsubscribe | hard_bounce | spam_complaint | manual',
    )
    source = models.CharField(
        max_length=40, blank=True,
        help_text='admin / webhook / unsubscribe_link / bounce_handler',
    )
    suppressed_at = models.DateTimeField(auto_now_add=True, db_index=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['-suppressed_at']
        indexes = [
            models.Index(fields=['reason', '-suppressed_at']),
        ]

    def __str__(self):
        return f'{self.email} · {self.reason}'
