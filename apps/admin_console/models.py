"""
Admin Console (Additional) — platform control-plane backbone.

Source: AliExpress_Admin_Additional.docx (24 chapters).

Chapters that live HERE (genuinely new control-plane surfaces):
  CH1   AdminRoleAssignment      6-level RBAC hierarchy
  CH1   ApprovalRequest          dual-approval workflow (4h expiry)
  CH17  AdminAuditEntry          immutable audit log w/ before/after state
  CH3   (commission override)    → ApprovalRequest(kind=commission_override)
  CH4   PersonalisationConfig    ranking weights + business rules + diversity
  CH5   AdminExperiment          admin A/B experiment + ship decision
  CH10  FeeSchedule              scheduled category commission changes
  CH13  PlatformSetting          versioned platform settings
  CH13  KillSwitch               emergency feature kill switches
  CH16  DataExportRequest        BI export with PII gating + audit reason
  CH18  LegalHold                blocks GDPR erasure / deletion
  CH18  LawEnforcementRequest    LE request intake + transparency counter
  CH19  PayoutHold / PayoutAdjustment   bridges payments.PayoutRequest
  CH21  AdminBanner              homepage banner editor + draft/approval
  CH22  PlatformAlert            platform-wide alerts to all users
  CH23  ServiceStatus / PlatformIncident   incident command
  CH24  AdminKpiSnapshot         executive KPI dashboard

NOT duplicated here (bridged to the existing implementation):
  CH2   financial dashboard → apps.data_analytics (GMV/revenue/P&L)
  CH6   campaigns           → apps.marketing_engine (Email/Push/Sms campaigns)
  CH7   carriers            → apps.logistics_ops.Carrier/CarrierService/SlaSnapshot
  CH8   seller mgmt         → apps.seller_onboarding (tier/health) + AdminActionLog
  CH9   listing moderation  → apps.moderation, apps.admin_actions.ProductModeration
  CH11  T&S ops centre      → apps.trust_safety
  CH12  dispute escalation  → apps.disputes
  CH13  feature flags       → apps.flags.Flag / FlagOverride
  CH14  category mgmt       → apps.products.Category (+ FeeSchedule for fee map)
  CH15  user mgmt           → apps.accounts + apps.admin_actions.AdminActionLog
  CH20  flash sales         → apps.marketing_engine.FlashSaleApplication
  audit (request-driven)    → apps.admin_actions.AdminActionLog (this app's
                              AdminAuditEntry is the richer before/after variant)
"""
from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


# ──────────────────────────────────────────────────────────────────────
# CH1 — RBAC role hierarchy
# ──────────────────────────────────────────────────────────────────────

# Higher number inherits all lower capabilities (doc CH1.1).
ADMIN_LEVELS = [
    (1, 'Viewer'),
    (2, 'Operator'),
    (3, 'Moderator'),
    (4, 'Senior admin'),
    (5, 'Super admin'),
    (6, 'Root (break-glass)'),
]


class AdminRoleAssignment(models.Model):
    """The admin's level in the 6-tier hierarchy. Access to the console
    still requires is_staff; this sets *capability*.
    """
    admin = models.OneToOneField(User, on_delete=models.CASCADE,
                                 related_name='admin_console_role')
    level = models.PositiveSmallIntegerField(choices=ADMIN_LEVELS, default=1)
    # Optional functional tag, e.g. 'legal', 'finance', 'engineering', 'dpo'.
    function = models.CharField(max_length=24, blank=True)
    granted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name='+')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.admin_id}:L{self.level}'


# ──────────────────────────────────────────────────────────────────────
# CH1 — Dual-approval workflow
# ──────────────────────────────────────────────────────────────────────

class ApprovalRequest(models.Model):
    """High-impact action awaiting a second senior admin's approval.
    Used for: permanent bans, fee changes, legal holds, commission
    overrides, kill switches, large refunds (doc CH1.1 HIGH_IMPACT_ACTIONS).
    """
    KIND_CHOICES = [
        ('permanent_seller_ban', 'Permanent seller ban'),
        ('bulk_seller_suspension', 'Bulk seller suspension'),
        ('fee_rate_change', 'Fee rate change'),
        ('legal_hold', 'Legal hold'),
        ('platform_emergency_shutdown', 'Platform emergency shutdown'),
        ('delete_user_data', 'Delete user data'),
        ('bulk_refund', 'Bulk refund > $100k'),
        ('commission_override', 'Commission override'),
        ('kill_switch', 'Kill switch toggle'),
        ('permanent_user_ban', 'Permanent user ban'),
    ]
    STATUS_CHOICES = [
        ('pending_approval', 'Pending approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('expired', 'Expired'),
        ('executed', 'Executed'),
        ('execution_failed', 'Execution failed'),
    ]
    kind = models.CharField(max_length=32, choices=KIND_CHOICES, db_index=True)
    submitted_by = models.ForeignKey(User, on_delete=models.PROTECT,
                                     related_name='approval_requests_submitted')
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                    blank=True,
                                    related_name='approval_requests_reviewed')
    target_type = models.CharField(max_length=40, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    reason = models.TextField()
    business_justification = models.TextField(blank=True)
    # Parameters the executor needs once approved (e.g. new rate, dates).
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,
                              default='pending_approval', db_index=True)
    decision_note = models.CharField(max_length=300, blank=True)
    execution_result = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField()
    decided_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'kind'])]
        ordering = ['-created_at']


# ──────────────────────────────────────────────────────────────────────
# CH17 — Immutable audit log (richer before/after variant)
# ──────────────────────────────────────────────────────────────────────

class AdminAuditEntry(models.Model):
    """Insert-only audit row with before/after state and result. The
    model exposes no update/delete affordance; the worker DB grants
    enforce write-only in production (doc CH17 data model).
    """
    RESULT_CHOICES = [
        ('success', 'Success'), ('failed', 'Failed'),
        ('pending_approval', 'Pending approval'),
    ]
    admin = models.ForeignKey(User, on_delete=models.PROTECT,
                              related_name='admin_console_audit_entries')
    admin_level = models.PositiveSmallIntegerField(default=1)
    action_type = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=40, blank=True)
    target_id = models.CharField(max_length=64, blank=True, db_index=True)
    before_state = models.JSONField(default=dict, blank=True)
    after_state = models.JSONField(default=dict, blank=True)
    reason = models.CharField(max_length=300, blank=True)
    result = models.CharField(max_length=20, choices=RESULT_CHOICES,
                              default='success', db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    session_id = models.CharField(max_length=64, blank=True)
    approval_request = models.ForeignKey(
        ApprovalRequest, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='audit_entries')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['action_type', '-created_at'])]


# ──────────────────────────────────────────────────────────────────────
# CH4 — Personalisation engine config
# ──────────────────────────────────────────────────────────────────────

class PersonalisationConfig(models.Model):
    """Versioned ranking config. A new version cannot be the live one
    unless it links an approved experiment (doc CH4 guardrail).
    """
    version = models.PositiveIntegerField(unique=True)
    is_live = models.BooleanField(default=False, db_index=True)
    # {signal: weight} — must sum ~1.0 (validated in services)
    signal_weights = models.JSONField(default=dict)
    # [{rule, active}] hard overrides applied after ML ranking
    business_rules = models.JSONField(default=list, blank=True)
    # diversity controls
    max_same_seller_per_page = models.PositiveSmallIntegerField(default=3)
    max_same_category_per_page = models.PositiveSmallIntegerField(default=5)
    min_new_seller_pct = models.PositiveSmallIntegerField(default=10)
    # cold-start
    cold_start_default = models.CharField(max_length=40,
                                          default='bestsellers')
    cold_start_switch_after_purchases = models.PositiveSmallIntegerField(
        default=3)
    linked_experiment = models.ForeignKey(
        'AdminExperiment', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='deployed_configs')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    deployed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-version']


# ──────────────────────────────────────────────────────────────────────
# CH5 — Admin A/B experiment + decision
# ──────────────────────────────────────────────────────────────────────

class AdminExperiment(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'), ('running', 'Running'),
        ('decided', 'Decided'), ('stopped', 'Stopped'),
    ]
    DECISION_CHOICES = [
        ('', 'Undecided'),
        ('ship_treatment', 'Ship treatment 100%'),
        ('continue', 'Continue running'),
        ('stop_no_change', 'Stop — no change'),
        ('partial_rollout', 'Partial rollout'),
    ]
    name = models.CharField(max_length=160)
    hypothesis = models.TextField(blank=True)
    experiment_type = models.CharField(max_length=24, default='feature')
    owner_email = models.EmailField(blank=True)
    team = models.CharField(max_length=40, blank=True)
    variants = models.JSONField(default=list)  # [{id, allocation, config}]
    traffic_allocation_pct = models.PositiveSmallIntegerField(default=20)
    assignment_key = models.CharField(max_length=24, default='user_id')
    primary_metric = models.CharField(max_length=64, blank=True)
    min_detectable_effect_pct = models.DecimalField(max_digits=5,
                                                    decimal_places=2,
                                                    default=1.5)
    confidence_threshold_pct = models.PositiveSmallIntegerField(default=95)
    secondary_metrics = models.JSONField(default=list, blank=True)
    guardrail_metrics = models.JSONField(default=list, blank=True)
    min_duration_days = models.PositiveSmallIntegerField(default=7)
    max_duration_days = models.PositiveSmallIntegerField(default=30)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default='draft', db_index=True)
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES,
                                blank=True, default='')
    decision_note = models.CharField(max_length=300, blank=True)
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name='+')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)


# ──────────────────────────────────────────────────────────────────────
# CH10 — Fee schedule (scheduled category commission changes)
# ──────────────────────────────────────────────────────────────────────

class FeeSchedule(models.Model):
    CHANGE_TYPE_CHOICES = [
        ('permanent', 'Permanent'), ('temporary', 'Temporary'),
        ('promotional', 'Promotional'),
    ]
    STATUS_CHOICES = [
        ('scheduled', 'Scheduled'), ('active', 'Active'),
        ('superseded', 'Superseded'), ('cancelled', 'Cancelled'),
    ]
    category_id = models.CharField(max_length=64, db_index=True)
    category_name = models.CharField(max_length=120, blank=True)
    current_rate_pct = models.DecimalField(max_digits=5, decimal_places=2)
    new_rate_pct = models.DecimalField(max_digits=5, decimal_places=2)
    change_type = models.CharField(max_length=12, choices=CHANGE_TYPE_CHOICES,
                                   default='permanent')
    effective_date = models.DateField(db_index=True)
    is_emergency = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                              default='scheduled', db_index=True)
    approval_request = models.ForeignKey(
        ApprovalRequest, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+')
    seller_notice_sent_at = models.DateTimeField(null=True, blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ──────────────────────────────────────────────────────────────────────
# CH13 — Platform settings + kill switches
# ──────────────────────────────────────────────────────────────────────

class PlatformSetting(models.Model):
    """Versioned key/value platform setting. Previous values are kept in
    PlatformSettingHistory so any change can be restored (doc CH13).
    """
    key = models.CharField(max_length=64, unique=True)
    value = models.JSONField(default=dict)
    description = models.CharField(max_length=200, blank=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name='+')
    version = models.PositiveIntegerField(default=1)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key


class PlatformSettingHistory(models.Model):
    setting_key = models.CharField(max_length=64, db_index=True)
    old_value = models.JSONField(default=dict)
    new_value = models.JSONField(default=dict)
    version = models.PositiveIntegerField()
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name='+')
    changed_at = models.DateTimeField(auto_now_add=True)


class KillSwitch(models.Model):
    """Emergency feature disable. Engaging a kill switch is a high-impact
    action requiring dual approval (doc CH13).
    """
    KEY_CHOICES = [
        ('disable_payments', 'Disable payments'),
        ('disable_new_orders', 'Disable new orders'),
        ('maintenance_mode', 'Maintenance mode'),
        ('disable_checkout', 'Disable checkout'),
        ('disable_signups', 'Disable signups'),
    ]
    key = models.CharField(max_length=24, choices=KEY_CHOICES, unique=True)
    is_engaged = models.BooleanField(default=False, db_index=True)
    engaged_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name='+')
    reason = models.CharField(max_length=300, blank=True)
    engaged_at = models.DateTimeField(null=True, blank=True)
    disengaged_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.key}={"ON" if self.is_engaged else "off"}'


# ──────────────────────────────────────────────────────────────────────
# CH16 — Data export request (BI access)
# ──────────────────────────────────────────────────────────────────────

class DataExportRequest(models.Model):
    DATASET_CHOICES = [
        ('gmv_report', 'GMV report'),
        ('commission_revenue', 'Commission revenue'),
        ('payout_ledger', 'Payout ledger'),
        ('refund_report', 'Refund report'),
        ('fraud_loss', 'Fraud loss report'),
        ('seller_performance', 'Seller performance (anonymised)'),
        ('seller_violations', 'Seller violations'),
        ('order_report', 'Order report'),
        ('buyer_pii', 'Buyer PII (restricted)'),
        ('seller_kyc', 'Seller KYC (restricted)'),
    ]
    STATUS_CHOICES = [
        ('queued', 'Queued'), ('running', 'Running'),
        ('ready', 'Ready'), ('denied', 'Denied'), ('failed', 'Failed'),
    ]
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT,
                                     related_name='data_export_requests')
    dataset = models.CharField(max_length=24, choices=DATASET_CHOICES)
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)
    granularity = models.CharField(max_length=12, default='daily')
    export_format = models.CharField(max_length=8, default='csv')
    reason = models.CharField(max_length=300)  # audit reason — required
    is_pii = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default='queued', db_index=True)
    deny_reason = models.CharField(max_length=200, blank=True)
    result_key = models.CharField(max_length=300, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)


# ──────────────────────────────────────────────────────────────────────
# CH18 — Legal hold + law-enforcement request
# ──────────────────────────────────────────────────────────────────────

class LegalHold(models.Model):
    SUBJECT_CHOICES = [
        ('seller', 'Seller'), ('buyer', 'Buyer'),
        ('order', 'Order'), ('group', 'Group of accounts'),
    ]
    SCOPE_CHOICES = [
        ('all_data', 'All data'), ('orders_only', 'Orders only'),
        ('communications_only', 'Communications only'),
    ]
    BASIS_CHOICES = [
        ('le_request', 'Law enforcement request'),
        ('litigation', 'Litigation hold'),
        ('regulatory', 'Regulatory investigation'),
    ]
    STATUS_CHOICES = [('active', 'Active'), ('released', 'Released'),
                      ('expired', 'Expired')]
    hold_ref = models.CharField(max_length=32, unique=True)
    subject_type = models.CharField(max_length=8, choices=SUBJECT_CHOICES)
    subject_id = models.CharField(max_length=64, db_index=True)
    scope = models.CharField(max_length=24, choices=SCOPE_CHOICES,
                             default='all_data')
    legal_basis = models.CharField(max_length=16, choices=BASIS_CHOICES)
    requesting_authority = models.CharField(max_length=120, blank=True)
    case_reference = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)
    placed_by = models.ForeignKey(User, on_delete=models.PROTECT,
                                  related_name='legal_holds_placed')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default='active', db_index=True)
    placed_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)  # null = indefinite
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                    blank=True, related_name='+')

    class Meta:
        indexes = [models.Index(fields=['subject_type', 'subject_id',
                                         'status'])]


class LawEnforcementRequest(models.Model):
    REQUEST_TYPE_CHOICES = [
        ('preservation', 'Preservation'),
        ('disclosure', 'Disclosure'),
        ('removal', 'Removal'),
    ]
    STATUS_CHOICES = [
        ('received', 'Received'), ('accepted', 'Accepted'),
        ('rejected', 'Rejected'), ('clarification', 'Clarification requested'),
    ]
    request_ref = models.CharField(max_length=40, unique=True)
    request_type = models.CharField(max_length=14,
                                    choices=REQUEST_TYPE_CHOICES)
    authority = models.CharField(max_length=120)
    case_reference = models.CharField(max_length=120, blank=True)
    subject_id = models.CharField(max_length=64, blank=True)
    jurisdiction = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=14, choices=STATUS_CHOICES,
                              default='received', db_index=True)
    decision_note = models.CharField(max_length=300, blank=True)
    legal_hold = models.ForeignKey(LegalHold, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='+')
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='+')
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)


# ──────────────────────────────────────────────────────────────────────
# CH19 — Payout holds + adjustments (bridges payments.PayoutRequest)
# ──────────────────────────────────────────────────────────────────────

class PayoutHold(models.Model):
    REASON_CHOICES = [
        ('fraud_investigation', 'Fraud investigation'),
        ('legal_hold', 'Legal hold'),
        ('seller_dispute', 'Seller dispute'),
        ('aml_review', 'AML review'),
    ]
    STATUS_CHOICES = [('active', 'Active'), ('released', 'Released')]
    payout_request_id = models.CharField(max_length=64, db_index=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='payout_holds')
    reason = models.CharField(max_length=24, choices=REASON_CHOICES)
    notify_seller = models.BooleanField(default=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default='active', db_index=True)
    placed_by = models.ForeignKey(User, on_delete=models.PROTECT,
                                  related_name='+')
    placed_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)


class PayoutAdjustment(models.Model):
    KIND_CHOICES = [('credit', 'Manual credit'), ('deduction', 'Manual deduction')]
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='payout_adjustments')
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    amount_cents = models.BigIntegerField()
    reason = models.CharField(max_length=300)  # shows on commission statement
    approval_request = models.ForeignKey(
        ApprovalRequest, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+')
    created_by = models.ForeignKey(User, on_delete=models.PROTECT,
                                   related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)


# ──────────────────────────────────────────────────────────────────────
# CH21 — Homepage banner editor (admin editorial)
# ──────────────────────────────────────────────────────────────────────

class AdminBanner(models.Model):
    """Homepage slot banner with draft → approval → live flow. Editorial
    *collections* live in apps.search_discovery; this is the banner/slot
    manager with a separate approver (doc CH21 content approval).
    """
    SLOT_CHOICES = [
        ('hero_banner_1', 'Hero banner 1'),
        ('hero_banner_2', 'Hero banner 2'),
        ('featured_categories', 'Featured categories'),
        ('editorial_collection_1', 'Editorial collection 1'),
        ('second_editorial', 'Second editorial'),
    ]
    STATUS_CHOICES = [
        ('draft', 'Draft'), ('pending_approval', 'Pending approval'),
        ('approved', 'Approved'), ('live', 'Live'),
        ('expired', 'Expired'), ('rejected', 'Rejected'),
    ]
    slot = models.CharField(max_length=24, choices=SLOT_CHOICES, db_index=True)
    headline = models.CharField(max_length=160)
    subline = models.CharField(max_length=200, blank=True)
    image_desktop_key = models.CharField(max_length=300, blank=True)
    image_mobile_key = models.CharField(max_length=300, blank=True)
    cta_text = models.CharField(max_length=40, blank=True)
    cta_link = models.CharField(max_length=300, blank=True)
    target_countries = models.JSONField(default=list, blank=True)  # [] = all
    priority = models.PositiveSmallIntegerField(default=1)
    is_paid_placement = models.BooleanField(default=False)  # brand partnership
    status = models.CharField(max_length=16, choices=STATUS_CHOICES,
                              default='draft', db_index=True)
    go_live_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name='+')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                    blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['slot', 'priority']


# ──────────────────────────────────────────────────────────────────────
# CH22 — Platform-wide alerts
# ──────────────────────────────────────────────────────────────────────

class PlatformAlert(models.Model):
    TYPE_CHOICES = [
        ('service_disruption', 'Service disruption'),
        ('policy_update', 'Policy update'),
        ('maintenance', 'Maintenance'),
        ('security', 'Security'),
    ]
    SEVERITY_CHOICES = [('low', 'Low'), ('medium', 'Medium'),
                        ('high', 'High'), ('critical', 'Critical')]
    STATUS_CHOICES = [
        ('draft', 'Draft'), ('published', 'Published'),
        ('resolved', 'Resolved'),
    ]
    alert_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    message = models.TextField()
    channels = models.JSONField(default=list)  # ['in_app','email','push']
    audience = models.CharField(max_length=24, default='all_users')
    severity = models.CharField(max_length=8, choices=SEVERITY_CHOICES,
                                default='high')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default='draft', db_index=True)
    auto_resolve_with_incident = models.ForeignKey(
        'PlatformIncident', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='alerts')
    published_by = models.ForeignKey(User, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)


# ──────────────────────────────────────────────────────────────────────
# CH23 — Service status + incident command
# ──────────────────────────────────────────────────────────────────────

class ServiceStatus(models.Model):
    STATE_CHOICES = [
        ('operational', 'Operational'), ('degraded', 'Degraded'),
        ('partial_outage', 'Partial outage'), ('major_outage', 'Major outage'),
    ]
    service_name = models.CharField(max_length=64, unique=True)
    state = models.CharField(max_length=16, choices=STATE_CHOICES,
                             default='operational', db_index=True)
    latency_p99_ms = models.PositiveIntegerField(default=0)
    error_rate_pct = models.DecimalField(max_digits=6, decimal_places=3,
                                         default=0)
    last_incident_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class PlatformIncident(models.Model):
    SEVERITY_CHOICES = [('p0', 'P0'), ('p1', 'P1'), ('p2', 'P2'),
                        ('p3', 'P3')]
    STATUS_CHOICES = [
        ('investigating', 'Investigating'), ('identified', 'Identified'),
        ('monitoring', 'Monitoring'), ('resolved', 'Resolved'),
    ]
    title = models.CharField(max_length=200)
    severity = models.CharField(max_length=2, choices=SEVERITY_CHOICES,
                                default='p2', db_index=True)
    affected_service = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=14, choices=STATUS_CHOICES,
                              default='investigating', db_index=True)
    status_page_message = models.CharField(max_length=300, blank=True)
    estimated_affected_users = models.PositiveIntegerField(default=0)
    owner_email = models.EmailField(blank=True)
    declared_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                    blank=True, related_name='+')
    timeline = models.JSONField(default=list, blank=True)  # [{at, status, note}]
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']


# ──────────────────────────────────────────────────────────────────────
# CH24 — Admin KPI snapshot
# ──────────────────────────────────────────────────────────────────────

class AdminKpiSnapshot(models.Model):
    snapshot_date = models.DateField(unique=True)
    daily_gmv_cents = models.BigIntegerField(default=0)
    platform_availability_pct = models.DecimalField(max_digits=7,
                                                    decimal_places=4,
                                                    default=0)   # >99.99
    take_rate_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                        default=0)
    moderation_queue_age_hours = models.DecimalField(max_digits=6,
                                                     decimal_places=2,
                                                     default=0)   # <4
    seller_suspension_rate_pct = models.DecimalField(max_digits=5,
                                                     decimal_places=2,
                                                     default=0)   # <0.5
    dispute_escalation_rate_pct = models.DecimalField(max_digits=5,
                                                      decimal_places=2,
                                                      default=0)  # <15
    payment_success_rate_pct = models.DecimalField(max_digits=5,
                                                   decimal_places=2,
                                                   default=0)     # >99
    fraud_loss_bps = models.DecimalField(max_digits=8, decimal_places=2,
                                         default=0)               # <5
    active_experiments = models.PositiveIntegerField(default=0)    # 5-15
    carrier_on_time_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                              default=0)           # >90
    audit_coverage_pct = models.DecimalField(max_digits=6, decimal_places=2,
                                             default=100)          # 100
    dual_approval_compliance_pct = models.DecimalField(max_digits=6,
                                                       decimal_places=2,
                                                       default=100)  # 100
    pending_approvals = models.PositiveIntegerField(default=0)
    active_incidents = models.PositiveIntegerField(default=0)
    computed_at = models.DateTimeField(auto_now=True)


# ──────────────────────────────────────────────────────────────────────
# Append-only console event log
# ──────────────────────────────────────────────────────────────────────

class AdminConsoleEvent(models.Model):
    kind = models.CharField(max_length=48, db_index=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name='admin_console_events')
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    @staticmethod
    def log(kind, actor=None, **payload):
        try:
            AdminConsoleEvent.objects.create(
                kind=kind,
                actor=actor if getattr(actor, 'pk', None) else None,
                payload=payload,
            )
        except Exception:
            pass
