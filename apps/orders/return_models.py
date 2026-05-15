"""
apps/orders/return_models.py

Full returns state machine. The status field is the source of truth for what
the buyer/seller/admin can do next; every transition is recorded as a
ReturnEvent row (who, when, from → to, optional note).

States:

    pending
        Buyer just filed the return; seller has SLA window to respond.

    approved
        Seller approved → buyer ships the item back (or arranges pickup).
        Has a pickup_deadline_at; if buyer doesn't act, return auto-cancels.

    rejected
        Seller refused. Buyer can escalate to admin within 48h.

    completed
        Refund issued and (if applicable) stock restored. Terminal.

    withdrawn
        Buyer cancelled the return before seller acted. Terminal.

    escalated
        Buyer disputed a rejection. Admin owns it now.

    auto_approved
        Seller missed their SLA → system auto-approved on buyer's behalf.
        Treated identically to 'approved' downstream but flagged for ops
        review (seller may have an SLA problem).

Transitions are enforced by the views via VALID_TRANSITIONS; bypassing the
state machine is possible only through the admin override endpoint, which
records the override in the audit trail.
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

User = settings.AUTH_USER_MODEL


# SLA windows. Centralised here so they're easy to tune without grepping
# across views and tasks.
SELLER_RESPONSE_HOURS = 72   # seller must approve/reject within 3 days
PICKUP_DEADLINE_DAYS  = 7    # buyer must ship/dropoff within 7 days of approval
ESCALATION_WINDOW_HOURS = 48 # buyer can dispute a rejection within 48h


class ReturnStatus(models.TextChoices):
    PENDING       = 'pending',       'Pending seller'
    APPROVED      = 'approved',      'Approved'
    AUTO_APPROVED = 'auto_approved', 'Auto-approved (seller SLA missed)'
    REJECTED      = 'rejected',      'Rejected'
    ESCALATED     = 'escalated',     'Escalated to admin'
    COMPLETED     = 'completed',     'Completed'
    WITHDRAWN     = 'withdrawn',     'Withdrawn by buyer'
    CANCELLED     = 'cancelled',     'Cancelled (deadline lapsed)'


class ReturnRequest(models.Model):
    REASON = [
        ('wrong_item','Wrong item'),
        ('damaged','Damaged'),
        ('not_as_described','Not as described'),
        ('missing_parts','Missing parts'),
        ('changed_mind','Changed mind'),
    ]
    PICKUP = [('pickup','Pickup'),('dropoff','Drop-off')]
    REFUND_DESTINATION = [
        ('store_credit', 'Store credit'),
        ('original',     'Original payment method'),
    ]

    order = models.ForeignKey('orders.Order', on_delete=models.CASCADE, related_name='return_requests')
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='return_requests')

    reason = models.CharField(max_length=30, choices=REASON)
    description = models.TextField(blank=True)
    photo = models.ImageField(upload_to='return_photos/', null=True, blank=True)
    pickup_method = models.CharField(max_length=10, choices=PICKUP, default='pickup')
    refund_destination = models.CharField(
        max_length=15, choices=REFUND_DESTINATION, default='store_credit',
    )

    status = models.CharField(
        max_length=20, choices=ReturnStatus.choices,
        default=ReturnStatus.PENDING, db_index=True,
    )
    admin_note = models.TextField(blank=True)

    # Deadline-driven auto-actions
    seller_response_deadline_at = models.DateTimeField(null=True, blank=True, db_index=True)
    pickup_deadline_at = models.DateTimeField(null=True, blank=True, db_index=True)
    # When buyer can no longer escalate a rejection
    escalation_deadline_at = models.DateTimeField(null=True, blank=True)

    # Refund/restock side effects — populated when completed.
    refunded_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    restocked = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'seller_response_deadline_at']),
            models.Index(fields=['status', 'pickup_deadline_at']),
        ]

    def __str__(self):
        return f"Return {self.order_id} — {self.reason} ({self.status})"

    def save(self, *args, **kwargs):
        # On first save: stamp the SLA deadline so the sweeper knows when to
        # auto-act. Done here (not in the view) so admin-created returns also
        # get the deadline.
        if self.pk is None and not self.seller_response_deadline_at:
            self.seller_response_deadline_at = (
                timezone.now() + timedelta(hours=SELLER_RESPONSE_HOURS)
            )
        super().save(*args, **kwargs)


class ReturnEvent(models.Model):
    """Immutable per-transition audit row. One per state change."""
    return_request = models.ForeignKey(
        ReturnRequest, on_delete=models.CASCADE, related_name='events',
    )
    # Who triggered it. NULL = system (deadline sweeper, etc.)
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='return_events',
    )
    actor_role = models.CharField(
        max_length=10,
        choices=[('buyer','Buyer'),('seller','Seller'),('admin','Admin'),('system','System')],
    )
    from_status = models.CharField(max_length=20, blank=True)
    to_status   = models.CharField(max_length=20)
    note = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['return_request', 'created_at']),
        ]

    def __str__(self):
        return f'{self.return_request_id}: {self.from_status} → {self.to_status} by {self.actor_role}'
