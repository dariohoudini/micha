"""
apps/data_rights/models.py

Data Subject Request — one row per Article-20 (data portability / export) or
Article-17 (right-to-erasure) request. Driven by sagas under the hood; this
table is the human-facing audit + status surface.

Why a separate model (not just a flag on User):
  - Same user may file multiple requests over their lifetime
  - Requests have lifecycle (pending → running → completed | failed)
  - Compliance: must keep request records even AFTER the user is erased
    (deletion_requested_at on User goes away when User is anonymised)
  - Operators need to query "how many open erase requests, sorted by SLA?"
"""
from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class RequestKind(models.TextChoices):
    EXPORT = 'export', 'Export (data portability)'
    ERASE  = 'erase',  'Erase (right to be forgotten)'


class RequestStatus(models.TextChoices):
    PENDING    = 'pending',    'Pending'
    RUNNING    = 'running',    'Running'
    COMPLETED  = 'completed',  'Completed'
    FAILED     = 'failed',     'Failed'
    CANCELLED  = 'cancelled',  'Cancelled by requester'


class DataSubjectRequest(models.Model):
    """One request per data-subject action. Always preserved; survives user erase."""
    # Use SET_NULL — once the user is anonymised, the request row stays around
    # as audit but no longer references the (now-anonymised) user row.
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='data_requests',
    )
    # Snapshot at request time so we can still identify which user this was
    # *for* even after erasure.
    user_email_at_request = models.CharField(max_length=320, blank=True)

    kind   = models.CharField(max_length=10, choices=RequestKind.choices, db_index=True)
    status = models.CharField(
        max_length=12, choices=RequestStatus.choices,
        default=RequestStatus.PENDING, db_index=True,
    )

    # IP / UA captured at request time — needed for audit / regulator inquiries.
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)

    # For EXPORT: where the manifest lives once produced. For ERASE: the
    # summary of what was anonymised (tables/rows touched).
    payload = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    # SLA bookkeeping. Compliance windows differ:
    #   Export: best-effort, target <24h (no hard regulatory cap)
    #   Erase:  30 days max (Angola Lei 22/11 ≈ GDPR)
    sla_deadline_at = models.DateTimeField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'sla_deadline_at']),
            models.Index(fields=['kind', 'status']),
        ]

    def __str__(self):
        return f'{self.kind}#{self.id} ({self.status})'


# R6: cookie consent — re-export from cookie_consent module so Django
# picks up the model.
from .cookie_consent import CookieConsent  # noqa: F401,E402
