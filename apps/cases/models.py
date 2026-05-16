"""
apps/cases/models.py

Trust & Safety case management. A Case is a unifying object that links
disparate signals — disputes, returns, reports, fraud holds, chargebacks —
into one investigatable workflow.

Why a separate Case model and not just "use Disputes":
  • Disputes are 1:1 with an Order. Real T&S incidents span MULTIPLE orders
    (a fraud ring, a serial returner, a counterfeit seller).
  • A case has its OWN lifecycle independent of any single piece of evidence.
    A return resolves; the case behind it may stay open until the seller
    is suspended.
  • Operators need to query "all cases involving user X" — that's a join
    a flat Dispute table can't easily answer.

Four tables:

  Case          The investigation. Subject (the user/seller/order it's
                primarily about), state, priority, severity, assigned admin,
                SLA deadline.

  CaseLink      Many-to-many between Case and external evidence rows.
                Polymorphic via (link_type, ref_type, ref_id) — same
                pattern we use in OutboxEvent / TaxCalculation.

  CaseEvent     Append-only audit. Every state change, assignment,
                link addition, note — one row.

  CaseSubject   Many-to-many of "users involved in this case". Lets us
                answer "all cases involving user X" in one indexed query.
"""
from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class CaseStatus(models.TextChoices):
    NEW           = 'new',           'New (untriaged)'
    TRIAGED       = 'triaged',       'Triaged'
    INVESTIGATING = 'investigating', 'Investigating'
    AWAITING_INFO = 'awaiting_info', 'Awaiting info (user/seller)'
    ESCALATED     = 'escalated',     'Escalated (senior admin)'
    RESOLVED      = 'resolved',      'Resolved'
    CLOSED        = 'closed',        'Closed (no action)'


class CasePriority(models.TextChoices):
    LOW    = 'low',    'Low'
    NORMAL = 'normal', 'Normal'
    HIGH   = 'high',   'High'
    URGENT = 'urgent', 'Urgent'


class CaseKind(models.TextChoices):
    """Coarse-grained category so dashboards can group like with like.
    Free-form sub-types live in metadata."""
    FRAUD          = 'fraud',          'Fraud / risk hold'
    COUNTERFEIT    = 'counterfeit',    'Counterfeit / IP'
    HARASSMENT     = 'harassment',     'Harassment / abuse'
    REFUND_DISPUTE = 'refund_dispute', 'Refund / dispute'
    POLICY         = 'policy',         'Policy violation'
    SECURITY       = 'security',       'Account security'
    OTHER          = 'other',          'Other'


class CaseResolution(models.TextChoices):
    """Why a case ended. Drives downstream policy decisions (false_positive
    rebates fraud-score trust; abuse_confirmed schedules a strike on the
    offending user; etc.)."""
    NO_ACTION       = 'no_action',       'Closed — no action needed'
    WARNING_ISSUED  = 'warning_issued',  'Warning issued'
    ACCOUNT_SUSPENDED = 'account_suspended', 'Account suspended'
    ACCOUNT_BANNED  = 'account_banned',  'Account banned'
    REFUND_GRANTED  = 'refund_granted',  'Refund granted'
    PRODUCT_REMOVED = 'product_removed', 'Product removed'
    POLICY_UPDATE   = 'policy_update',   'Policy updated'
    DUPLICATE       = 'duplicate',       'Duplicate of another case'
    FALSE_POSITIVE  = 'false_positive',  'False positive'


class Case(models.Model):
    """One T&S investigation."""
    # Human-readable code. Generated on save: TS-2026-00042
    code = models.CharField(max_length=24, unique=True, db_index=True)
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, choices=CaseKind.choices, db_index=True)
    status = models.CharField(
        max_length=16, choices=CaseStatus.choices,
        default=CaseStatus.NEW, db_index=True,
    )
    priority = models.CharField(
        max_length=8, choices=CasePriority.choices,
        default=CasePriority.NORMAL, db_index=True,
    )

    # The primary subject of the case — typically a user. Loose FK so we can
    # also open cases about non-user subjects (orders, products) without a
    # second column.
    subject_type = models.CharField(max_length=40, blank=True, db_index=True)
    subject_id   = models.CharField(max_length=80, blank=True, db_index=True)

    # Who opened the case. Either a user (self-report) or admin (auto-open
    # from a fraud hold / pattern detection). Not both.
    opened_by_user  = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cases_opened',
    )
    opened_by_admin = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cases_admin_opened',
    )
    # Currently-assigned admin. SET_NULL so a departing employee's name
    # doesn't break audit history.
    assigned_to = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cases_assigned',
    )

    summary = models.TextField(blank=True)
    resolution = models.CharField(
        max_length=24, choices=CaseResolution.choices, blank=True,
    )
    resolution_note = models.TextField(blank=True)

    # SLA. Set on creation based on priority; admins can override.
    sla_at = models.DateTimeField(null=True, blank=True, db_index=True)

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['kind', 'status']),
        ]
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.code:
            # TS-<year>-<id_padded>. ID isn't known until first save, so
            # we use a placeholder, save once to allocate the PK, then
            # update the code in the same transaction.
            self.code = ''
        super().save(*args, **kwargs)
        if not self.code:
            self.code = f'TS-{self.created_at.year if self.created_at else timezone.now().year}-{self.id:06d}'
            type(self).objects.filter(pk=self.pk).update(code=self.code)

    def __str__(self):
        return f'{self.code or "#?"}: {self.title[:50]}'


class CaseSubject(models.Model):
    """Users involved in a case (subject, complainant, reported party, witness).
    Many-to-many with a role so "all cases against seller X" is one query."""
    ROLES = [
        ('reporter',     'Reporter (filed the complaint)'),
        ('reported',     'Reported (subject of the complaint)'),
        ('witness',      'Witness / additional party'),
        ('beneficiary',  'Beneficiary (e.g. refund recipient)'),
    ]
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='subjects')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='case_appearances')
    role = models.CharField(max_length=16, choices=ROLES)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['case', 'user', 'role'],
                                    name='uniq_case_user_role'),
        ]
        indexes = [
            models.Index(fields=['user', '-added_at']),
        ]


class CaseLink(models.Model):
    """Polymorphic evidence link. ``link_type`` tags the relationship class
    (e.g. 'dispute', 'return', 'order', 'fraud_assessment'); ref_type+ref_id
    point at the actual row."""
    LINK_TYPES = [
        ('order',            'Order'),
        ('dispute',          'Dispute'),
        ('return',           'Return request'),
        ('fraud_assessment', 'Fraud / risk assessment'),
        ('product',          'Product listing'),
        ('payment',          'Payment'),
        ('chat_message',     'Chat message'),
        ('user_report',      'User report'),
        ('webhook',          'Inbound webhook event'),
        ('saga',             'Saga (failed compensation)'),
    ]
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='links')
    link_type = models.CharField(max_length=24, choices=LINK_TYPES, db_index=True)
    ref_type = models.CharField(max_length=40, db_index=True)
    ref_id   = models.CharField(max_length=80, db_index=True)
    note = models.CharField(max_length=300, blank=True)
    added_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['case', 'link_type', 'ref_type', 'ref_id'],
                                    name='uniq_case_link'),
        ]
        indexes = [
            models.Index(fields=['ref_type', 'ref_id']),
        ]


class CaseEvent(models.Model):
    """Append-only audit row. EVERY interaction with a case writes one of these
    — state change, assignment, link, note. The full chain of custody."""
    EVENT_TYPES = [
        ('opened',        'Opened'),
        ('state_change',  'State change'),
        ('assigned',      'Assigned'),
        ('priority_change', 'Priority change'),
        ('link_added',    'Evidence linked'),
        ('link_removed',  'Evidence unlinked'),
        ('subject_added', 'Subject added'),
        ('note',          'Note'),
        ('resolved',      'Resolved'),
        ('reopened',      'Reopened'),
    ]
    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='events')
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    actor_role = models.CharField(max_length=12,
                                  choices=[('user','User'),('admin','Admin'),('system','System')])
    event_type = models.CharField(max_length=20, choices=EVENT_TYPES)
    body = models.TextField(blank=True)
    # Free-form context: {'from': 'new', 'to': 'triaged'} for state changes,
    # {'link_id': X} for link events, etc.
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['case', 'created_at']),
            models.Index(fields=['event_type', '-created_at']),
        ]
