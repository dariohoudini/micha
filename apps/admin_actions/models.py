from django.db import models, transaction
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class AdminActionLog(models.Model):
    """Immutable, hash-chained audit trail of every admin action.

    Append-only is enforced at the model layer (``save`` rejects updates,
    ``delete`` is blocked), and every row is hash-chained to its predecessor
    so any later alteration, deletion, or insertion is *detectable* — the
    difference between a log and evidence (Audit/Compliance/SLA doc CH8).
    The chain is re-verified by ``audit.verify_admin_chain`` (apps/
    admin_actions/tasks.py), which pages on-call if a break is found.
    """
    OUTCOMES = (
        ('success', 'Success'),
        ('failure', 'Failure'),
        ('denied', 'Denied'),
    )
    ACTION_TYPES = (
        ('suspend_user', 'Suspend User'),
        ('ban_user', 'Ban User'),
        ('activate_user', 'Activate User'),
        ('approve_verification', 'Approve Verification'),
        ('reject_verification', 'Reject Verification'),
        ('approve_payout', 'Approve Payout'),
        ('reject_payout', 'Reject Payout'),
        ('resolve_dispute_buyer', 'Resolve Dispute (Buyer)'),
        ('resolve_dispute_seller', 'Resolve Dispute (Seller)'),
        ('remove_product', 'Remove Product'),
        ('feature_product', 'Feature Product'),
        ('set_commission', 'Set Commission Rate'),
        ('issue_refund', 'Issue Refund'),
        ('create_announcement', 'Create Announcement'),
        ('assign_role', 'Assign Role'),
        ('revoke_role', 'Revoke Role'),
        ('view_encrypted_data', 'View Encrypted Data'),
        # R4 moderation queue decisions — distinct keys so audit logs
        # are queryable by intent. ``moderate_approve`` dismisses a
        # flag (content was OK); ``moderate_reject`` removes content
        # AND counts toward escalation; ``moderate_escalate`` kicks to
        # senior review without an infraction count.
        ('moderate_approve', 'Moderate: Approve (dismiss flag)'),
        ('moderate_reject', 'Moderate: Reject (remove content)'),
        ('moderate_escalate', 'Moderate: Escalate (senior review)'),
    )

    admin = models.ForeignKey(User, on_delete=models.PROTECT, related_name='admin_actions_taken')
    action = models.CharField(max_length=50, choices=ACTION_TYPES)
    target_type = models.CharField(max_length=50)
    target_id = models.CharField(max_length=100)
    target_repr = models.CharField(max_length=200, blank=True)
    note = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    metadata = models.JSONField(default=dict)
    # Explicit outcome (CH5 — a denied/failed action is security-relevant and
    # must be audited too, not just successes).
    outcome = models.CharField(max_length=16, choices=OUTCOMES, default='success')
    # default= (not auto_now_add) so the timestamp is set before the row is
    # hashed and is part of the integrity envelope — and recomputable on verify.
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    # ── Tamper-evidence (CH8) ────────────────────────────────────────
    # Monotonic per-table sequence — ordering + gap detection (a missing seq
    # = a deleted/suppressed record). Nullable only so the field can be added
    # to an existing table; the data migration backfills it and save() always
    # assigns it thereafter.
    seq = models.PositiveBigIntegerField(null=True, blank=True, unique=True)
    prev_hash = models.CharField(max_length=80, blank=True, default='')
    entry_hash = models.CharField(max_length=80, blank=True, default='', db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['admin', '-created_at']),
            models.Index(fields=['action', '-created_at']),
            models.Index(fields=['target_type', 'target_id']),
            models.Index(fields=['seq']),
        ]

    def chain_payload(self):
        """The canonical content that is hashed into the chain. Must be
        deterministic and stable: the verification job recomputes the hash
        from exactly these stored fields."""
        return {
            'seq': self.seq,
            'admin_id': self.admin_id,
            'action': self.action,
            'target_type': self.target_type,
            'target_id': self.target_id,
            'target_repr': self.target_repr,
            'note': self.note,
            'ip_address': self.ip_address,
            'user_agent': self.user_agent,
            'metadata': self.metadata,
            'outcome': self.outcome,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    def save(self, *args, **kwargs):
        # Append-only: an existing row can never be re-saved (CH8 / CH2 p2).
        if self.pk:
            raise ValueError(
                'AdminActionLog is append-only and tamper-evident — existing '
                'records cannot be modified (Audit/Compliance/SLA CH8).'
            )
        from apps.core.audit_chain import compute_entry_hash
        if self.created_at is None:
            self.created_at = timezone.now()
        # Serialize chain extension: lock the current tail so two concurrent
        # inserts can't fork the chain off the same prev_hash. On SQLite
        # (dev/tests) select_for_update is a no-op but execution is serial.
        with transaction.atomic():
            last = (
                AdminActionLog.objects
                .select_for_update()
                .order_by('-seq')
                .first()
            )
            self.seq = (last.seq + 1) if (last and last.seq) else 1
            self.prev_hash = last.entry_hash if last else ''
            self.entry_hash = compute_entry_hash(self.chain_payload(), self.prev_hash)
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError(
            'AdminActionLog is append-only — records cannot be deleted '
            '(Audit/Compliance/SLA CH8 tamper-evidence).'
        )

    @classmethod
    def log(cls, request, action, target, note='', metadata=None):
        ip = ''
        ua = ''
        if request:
            xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
            ip = xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '')
            ua = request.META.get('HTTP_USER_AGENT', '')[:200]
        if target is not None:
            target_repr = (
                getattr(target, 'email', None)
                or getattr(target, 'title', None)
                or str(target)[:200]
            )
            target_type = type(target).__name__.lower()
            target_id = str(getattr(target, 'pk', ''))
        else:
            target_repr, target_type, target_id = '', 'request', ''
        row = cls.objects.create(
            admin=request.user, action=action,
            target_type=target_type, target_id=target_id,
            target_repr=target_repr, note=note,
            ip_address=ip or None, user_agent=ua,
            metadata=metadata or {},
        )
        # Suppress the auto-audit middleware for this request — we've
        # already written a richer (manually-targeted) row.
        if request is not None:
            try:
                from .middleware import mark_logged
                mark_logged(request)
            except Exception:
                pass
        return row

    def __str__(self):
        return f"{self.admin.email} → {self.action} on {self.target_type}:{self.target_id}"


class AdminAction(models.Model):
    """Legacy alias — kept for backwards compatibility with old views."""
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name='old_admin_actions')
    action = models.CharField(max_length=100)
    target_id = models.CharField(max_length=100, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.admin.email}: {self.action}"


class ProductModeration(models.Model):
    """Track product moderation decisions."""
    STATUS = (
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('suspended', 'Suspended'),
    )
    product = models.OneToOneField(
        'products.Product', on_delete=models.CASCADE, related_name='moderation'
    )
    status = models.CharField(max_length=10, choices=STATUS, default='pending')
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='moderated_products'
    )
    rejection_reason = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', '-created_at'])]

    def __str__(self):
        return f"Moderation({self.product.title}): {self.status}"


class UserRestriction(models.Model):
    """Admin User Management doc CH5 — graduated enforcement short of a
    full suspend. A RESTRICT limits specific capabilities (cannot sell /
    cannot withdraw / cannot message) for a targeted concern, reversible,
    reason-required, audited — the least-force response in the ladder.
    One row per user; ``is_active=False`` = lifted (un-restricted).
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='restriction')
    no_selling = models.BooleanField(default=False)
    no_withdrawal = models.BooleanField(default=False)
    no_messaging = models.BooleanField(default=False)
    reason = models.CharField(max_length=300, blank=True)
    restricted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True,
        blank=True, related_name='restrictions_applied')
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'admin_user_restriction'

    def __str__(self):
        return f'Restriction({self.user_id}, active={self.is_active})'
