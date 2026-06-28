"""
Seller Tools (Additional) — Seller Center backbone.

Source: AliExpress_Seller_Tools_Additional.docx (24 chapters).

Chapters that live HERE (genuinely new — no existing model covered them):
  CH3   SellerBulkEditJob       (the 2-hour revert/undo with before-snapshot)
  CH2   SellerBulkImportJob     (seller product import with error report)
  CH8   SellerReturnPolicy      (structured per-category/product return config)
  CH9   SellerHolidayMode       (pause store, notify followers, auto-resume)
  CH10  ProductQaVote           (helpfulness voting; ProductQA already exists)
  CH11  StoreFollower / SellerBroadcast / BroadcastDelivery
  CH12  CommissionStatement     (monthly PDF/CSV financial statement)
  CH13  ListingQualityScore     (0-100 completeness score + breakdown)
  CH14  PriceCompetitivenessSnapshot
  CH17  SellerVatRegistration   (per-country VAT/GST registration)
  CH18  StoreAccountLink        (multi-store linking + context switching)
  CH19  SellerDisputeAppeal     (bridges disputes.Dispute)
  CH20  SellerBankAccount / SellerPayoutSchedule
  CH22  ProductComplianceLabel  (CE/FCC/RoHS/UKCA/FDA)
  CH23  ApiQuotaUsage           (tiered daily/per-minute quota counters)
  CH24  SellerToolsKpiSnapshot

NOT duplicated here (bridged to the existing implementation):
  CH2/3 execution   → apps.bulk_ops.BulkJob / BulkJobItem (generic ops queue)
  CH4   OAuth/API   → apps.seller_onboarding.SellerApiApp/SellerApiKey/Token,
                      apps.dev_keys.APIKey
  CH5   shipping    → apps.shipping.ShippingTemplate / ShippingMethod
  CH6   promotions  → apps.promotions, apps.marketing_engine
  CH7   analytics   → apps.analytics, apps.data_analytics.SellerAnalyticsReport
  CH10  Q&A core    → apps.products.ProductQA
  CH15  health      → apps.seller_onboarding.SellerHealthScore
  CH16  listing AI  → apps.ai_engine
  CH21  academy     → apps.seller_onboarding.SellerTrainingProgress/Certificate
"""
from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


# ──────────────────────────────────────────────────────────────────────
# CH2 / CH3 — Bulk import + bulk edit (with revert)
# ──────────────────────────────────────────────────────────────────────

class SellerBulkImportJob(models.Model):
    """Seller catalogue import. Execution rows live in bulk_ops; this
    tracks the seller-facing job: file, validation counts, error report.
    """
    STATUS_CHOICES = [
        ('queued', 'Queued'), ('validating', 'Validating'),
        ('importing', 'Importing'), ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='bulk_import_jobs')
    category_id = models.CharField(max_length=64, blank=True)
    file_name = models.CharField(max_length=255, blank=True)
    file_key = models.CharField(max_length=300, blank=True)  # object store key
    overwrite_existing = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                              default='queued', db_index=True)
    rows_total = models.PositiveIntegerField(default=0)
    rows_succeeded = models.PositiveIntegerField(default=0)
    rows_failed = models.PositiveIntegerField(default=0)
    rows_skipped = models.PositiveIntegerField(default=0)
    error_report_key = models.CharField(max_length=300, blank=True)
    bulk_job_id = models.PositiveIntegerField(null=True, blank=True)  # bulk_ops bridge
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)


class SellerBulkEditJob(models.Model):
    """Mass edit of existing listings. ``before_snapshot`` enables the
    doc's 2-hour revert window (price/stock/status only).
    """
    ACTION_CHOICES = [
        ('price_adjustment', 'Price adjustment'),
        ('stock_update', 'Stock update'),
        ('attribute_add', 'Attribute add'),
        ('status_change', 'Status change'),
        ('shipping_template', 'Shipping template'),
    ]
    STATUS_CHOICES = [
        ('queued', 'Queued'), ('running', 'Running'),
        ('completed', 'Completed'), ('failed', 'Failed'),
        ('reverted', 'Reverted'),
    ]
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='bulk_edit_jobs')
    action_type = models.CharField(max_length=20, choices=ACTION_CHOICES)
    action_params = models.JSONField(default=dict)
    listing_ids = models.JSONField(default=list)  # resolved target product ids
    status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                              default='queued', db_index=True)
    total = models.PositiveIntegerField(default=0)
    succeeded = models.PositiveIntegerField(default=0)
    failed = models.PositiveIntegerField(default=0)
    # {product_id: {field: old_value}} — only for revertible actions
    before_snapshot = models.JSONField(default=dict, blank=True)
    revertible_until = models.DateTimeField(null=True, blank=True)
    reverted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)


# ──────────────────────────────────────────────────────────────────────
# CH8 — Return policy configuration
# ──────────────────────────────────────────────────────────────────────

class SellerReturnPolicy(models.Model):
    """Per-seller return policy, optionally scoped to categories/products.
    Platform minimum window is enforced in services (cannot undercut).
    """
    SCOPE_CHOICES = [('all', 'All products'), ('category', 'Category'),
                     ('product', 'Product')]
    REASON_CHOICES = [
        ('any_reason', 'Any reason'),
        ('defective_only', 'Defective only'),
        ('not_as_described', 'Not as described'),
    ]
    SHIPPING_PAID_CHOICES = [('seller', 'Seller'), ('buyer', 'Buyer')]
    REFUND_TO_CHOICES = [
        ('original_payment', 'Original payment'),
        ('wallet', 'Wallet'),
        ('seller_discretion', 'Seller discretion'),
    ]
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='return_policies')
    policy_name = models.CharField(max_length=100)
    applicable_to = models.CharField(max_length=10, choices=SCOPE_CHOICES,
                                     default='all')
    category_ids = models.JSONField(default=list, blank=True)
    product_ids = models.JSONField(default=list, blank=True)
    return_window_days = models.PositiveSmallIntegerField(default=15)  # 15-90
    accepts_returns_if = models.CharField(max_length=20, choices=REASON_CHOICES,
                                          default='any_reason')
    return_shipping_paid_by = models.CharField(
        max_length=8, choices=SHIPPING_PAID_CHOICES, default='buyer')
    refund_to = models.CharField(max_length=20, choices=REFUND_TO_CHOICES,
                                 default='original_payment')
    non_returnable_reasons = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['seller', 'applicable_to', 'is_active'])]

    @property
    def free_returns(self):
        return self.return_shipping_paid_by == 'seller'


# ──────────────────────────────────────────────────────────────────────
# CH9 — Holiday mode
# ──────────────────────────────────────────────────────────────────────

class SellerHolidayMode(models.Model):
    """One row per seller (their current/most-recent holiday config)."""
    seller = models.OneToOneField(User, on_delete=models.CASCADE,
                                  related_name='holiday_mode')
    enabled = models.BooleanField(default=False, db_index=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    message = models.CharField(max_length=300, blank=True)
    notify_followers = models.BooleanField(default=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    resumed_at = models.DateTimeField(null=True, blank=True)
    auto_resumed = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)


# ──────────────────────────────────────────────────────────────────────
# CH10 — Q&A helpfulness voting (ProductQA already exists in apps.products)
# ──────────────────────────────────────────────────────────────────────

class ProductQaVote(models.Model):
    """Buyer 'helpful' vote on a published Q&A answer."""
    qa_id = models.PositiveIntegerField(db_index=True)  # products.ProductQA pk
    user = models.ForeignKey(User, on_delete=models.CASCADE,
                             related_name='qa_votes')
    helpful = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('qa_id', 'user')]


# ──────────────────────────────────────────────────────────────────────
# CH11 — Store followers + broadcast messages
# ──────────────────────────────────────────────────────────────────────

class StoreFollower(models.Model):
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='store_followers')
    user = models.ForeignKey(User, on_delete=models.CASCADE,
                             related_name='followed_stores')
    opt_out_broadcasts = models.BooleanField(default=False)
    followed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('seller', 'user')]
        indexes = [models.Index(fields=['seller', 'opt_out_broadcasts'])]


class SellerBroadcast(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'), ('scheduled', 'Scheduled'),
        ('sending', 'Sending'), ('sent', 'Sent'),
        ('blocked', 'Blocked'), ('failed', 'Failed'),
    ]
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='broadcasts')
    subject = models.CharField(max_length=160)
    message_body = models.TextField()
    coupon_id = models.CharField(max_length=64, blank=True)
    linked_product_ids = models.JSONField(default=list, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                              default='draft', db_index=True)
    recipients_count = models.PositiveIntegerField(default=0)
    delivered_count = models.PositiveIntegerField(default=0)
    open_count = models.PositiveIntegerField(default=0)
    click_count = models.PositiveIntegerField(default=0)
    order_count = models.PositiveIntegerField(default=0)  # 24h attribution
    spam_report_count = models.PositiveIntegerField(default=0)
    block_reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)


class BroadcastDelivery(models.Model):
    broadcast = models.ForeignKey(SellerBroadcast, on_delete=models.CASCADE,
                                  related_name='deliveries')
    user = models.ForeignKey(User, on_delete=models.CASCADE,
                             related_name='broadcast_deliveries')
    delivered = models.BooleanField(default=False)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    reported_spam = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('broadcast', 'user')]


# ──────────────────────────────────────────────────────────────────────
# CH12 — Commission statements
# ──────────────────────────────────────────────────────────────────────

class CommissionStatement(models.Model):
    STATUS_CHOICES = [('generating', 'Generating'), ('ready', 'Ready'),
                      ('failed', 'Failed')]
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='commission_statements')
    period_year = models.PositiveSmallIntegerField()
    period_month = models.PositiveSmallIntegerField()
    reference_number = models.CharField(max_length=40, unique=True)
    gross_sales_cents = models.BigIntegerField(default=0)
    commission_cents = models.BigIntegerField(default=0)
    refunds_cents = models.BigIntegerField(default=0)
    net_payout_cents = models.BigIntegerField(default=0)
    order_count = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                              default='generating')
    pdf_key = models.CharField(max_length=300, blank=True)
    csv_key = models.CharField(max_length=300, blank=True)
    detail = models.JSONField(default=dict, blank=True)  # per-order rows
    generated_at = models.DateTimeField(auto_now_add=True)
    downloaded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('seller', 'period_year', 'period_month')]
        ordering = ['-period_year', '-period_month']


# ──────────────────────────────────────────────────────────────────────
# CH13 — Listing Quality Score
# ──────────────────────────────────────────────────────────────────────

class ListingQualityScore(models.Model):
    product_id = models.PositiveIntegerField(unique=True, db_index=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='listing_quality_scores')
    total_score = models.PositiveSmallIntegerField(default=0)  # 0-100
    title_score = models.PositiveSmallIntegerField(default=0)
    image_score = models.PositiveSmallIntegerField(default=0)
    description_score = models.PositiveSmallIntegerField(default=0)
    attribute_score = models.PositiveSmallIntegerField(default=0)
    pricing_score = models.PositiveSmallIntegerField(default=0)
    missing = models.JSONField(default=list, blank=True)  # improvement actions
    breakdown = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['seller', 'total_score'])]


# ──────────────────────────────────────────────────────────────────────
# CH14 — Price competitiveness
# ──────────────────────────────────────────────────────────────────────

class PriceCompetitivenessSnapshot(models.Model):
    POSITION_CHOICES = [
        ('competitive', 'Cheaper than most'),
        ('neutral', 'Near market average'),
        ('slight_risk', 'Above market average'),
        ('review', 'Significantly above market'),
    ]
    product_id = models.PositiveIntegerField(db_index=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='price_competitiveness')
    seller_price_cents = models.IntegerField(default=0)
    market_median_cents = models.IntegerField(default=0)
    market_p25_cents = models.IntegerField(default=0)
    market_p75_cents = models.IntegerField(default=0)
    position_ratio = models.FloatField(default=1.0)
    position_label = models.CharField(max_length=16, choices=POSITION_CHOICES,
                                      default='neutral')
    sample_size = models.PositiveSmallIntegerField(default=0)
    suggestion = models.CharField(max_length=300, blank=True)
    computed_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ──────────────────────────────────────────────────────────────────────
# CH17 — Seller VAT / tax registration
# ──────────────────────────────────────────────────────────────────────

class SellerVatRegistration(models.Model):
    VALIDATION_CHOICES = [
        ('pending', 'Pending'), ('valid', 'Valid'),
        ('invalid', 'Invalid'), ('unchecked', 'Unchecked'),
    ]
    DISPLAY_CHOICES = [('inclusive', 'VAT inclusive'),
                       ('exclusive', 'VAT exclusive')]
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='vat_registrations')
    country = models.CharField(max_length=2)  # ISO alpha-2
    tax_type = models.CharField(max_length=12, default='VAT')  # VAT/GST/ABN
    registration_number = models.CharField(max_length=40)
    validation_status = models.CharField(max_length=12,
                                         choices=VALIDATION_CHOICES,
                                         default='pending')
    price_display_mode = models.CharField(max_length=10,
                                          choices=DISPLAY_CHOICES,
                                          default='inclusive')
    is_active = models.BooleanField(default=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('seller', 'country', 'registration_number')]


# ──────────────────────────────────────────────────────────────────────
# CH18 — Multi-store linking + account switching
# ──────────────────────────────────────────────────────────────────────

class StoreAccountLink(models.Model):
    """Links a controlling user to a seller account they can switch into.
    The active context is sent per-request via X-Seller-ID and validated
    against these rows. Max 5 stores per owner (enterprise approval to lift).
    """
    ROLE_CHOICES = [('owner', 'Owner'), ('manager', 'Manager'),
                    ('staff', 'Staff')]
    owner = models.ForeignKey(User, on_delete=models.CASCADE,
                              related_name='linked_store_memberships')
    store_seller = models.ForeignKey(User, on_delete=models.CASCADE,
                                     related_name='store_account_links')
    role = models.CharField(max_length=8, choices=ROLE_CHOICES, default='owner')
    approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('owner', 'store_seller')]


# ──────────────────────────────────────────────────────────────────────
# CH19 — Dispute appeal (bridges disputes.Dispute)
# ──────────────────────────────────────────────────────────────────────

class SellerDisputeAppeal(models.Model):
    STATUS_CHOICES = [
        ('submitted', 'Submitted'), ('under_review', 'Under review'),
        ('upheld', 'Upheld (seller won)'),
        ('rejected', 'Rejected (original decision stands)'),
    ]
    dispute_id = models.PositiveIntegerField(unique=True, db_index=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='dispute_appeals')
    appeal_reason = models.TextField()
    evidence_keys = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                              default='submitted', db_index=True)
    decision_note = models.CharField(max_length=300, blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)


# ──────────────────────────────────────────────────────────────────────
# CH20 — Payout configuration (bank accounts + schedule)
# ──────────────────────────────────────────────────────────────────────

# NOTE: bank accounts + withdrawals are NOT modelled here — they already
# exist in apps.payments (SellerBankAccount with field-level encryption +
# PayoutRequest). CH20 bridges to those. Only the *schedule* config is new.

class SellerPayoutSchedule(models.Model):
    MODE_CHOICES = [('automatic', 'Automatic'), ('manual', 'Manual')]
    seller = models.OneToOneField(User, on_delete=models.CASCADE,
                                  related_name='payout_schedule')
    mode = models.CharField(max_length=10, choices=MODE_CHOICES,
                            default='automatic')
    weekday = models.PositiveSmallIntegerField(default=0)  # 0 = Monday
    min_amount_cents = models.PositiveIntegerField(default=10000)  # $100
    # references apps.payments.SellerBankAccount.id (no cross-app FK to keep
    # the migration graph decoupled)
    default_bank_account_id = models.PositiveIntegerField(null=True, blank=True)
    express_release_eligible = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)


# ──────────────────────────────────────────────────────────────────────
# CH22 — Product compliance labels
# ──────────────────────────────────────────────────────────────────────

class ProductComplianceLabel(models.Model):
    LABEL_CHOICES = [
        ('CE', 'CE mark'), ('FCC', 'FCC ID'), ('RoHS', 'RoHS'),
        ('UKCA', 'UKCA'), ('FDA', 'FDA'), ('other', 'Other'),
    ]
    VERIFICATION_CHOICES = [
        ('self_declared', 'Self-declared'),
        ('under_review', 'Under review'),
        ('verified', 'Verified'), ('rejected', 'Rejected'),
    ]
    product_id = models.PositiveIntegerField(db_index=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='compliance_labels')
    label_type = models.CharField(max_length=8, choices=LABEL_CHOICES)
    label_value = models.CharField(max_length=120)  # certificate number
    issuing_body = models.CharField(max_length=120, blank=True)
    issue_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    certificate_key = models.CharField(max_length=300, blank=True)
    verification_status = models.CharField(max_length=16,
                                           choices=VERIFICATION_CHOICES,
                                           default='self_declared')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('product_id', 'label_type')]


# ──────────────────────────────────────────────────────────────────────
# CH23 — API quota usage (tiered)
# ──────────────────────────────────────────────────────────────────────

class ApiQuotaUsage(models.Model):
    """Daily counter per seller. Tier sets daily + per-minute ceilings.
    The per-minute burst is enforced with a sliding counter in services.
    """
    TIER_CHOICES = [
        ('standard', 'Standard'), ('bronze', 'Bronze'), ('silver', 'Silver'),
        ('gold', 'Gold'), ('enterprise', 'Enterprise'),
    ]
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='api_quota_usage')
    usage_date = models.DateField(db_index=True)
    tier = models.CharField(max_length=12, choices=TIER_CHOICES,
                            default='standard')
    daily_quota = models.PositiveIntegerField(default=100000)
    calls_today = models.PositiveIntegerField(default=0)
    minute_bucket = models.CharField(max_length=20, blank=True)  # 'YYYYMMDDHHMM'
    calls_this_minute = models.PositiveIntegerField(default=0)
    per_minute_limit = models.PositiveIntegerField(default=100)
    throttled_count = models.PositiveIntegerField(default=0)  # 429s today

    class Meta:
        unique_together = [('seller', 'usage_date')]
        indexes = [models.Index(fields=['seller', 'usage_date'])]


# ──────────────────────────────────────────────────────────────────────
# CH24 — Seller tools KPI snapshot
# ──────────────────────────────────────────────────────────────────────

class SellerToolsKpiSnapshot(models.Model):
    snapshot_date = models.DateField(unique=True)
    bulk_import_success_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                                  default=0)   # >90
    bulk_edit_success_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                                default=0)     # >95
    api_adoption_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                           default=0)          # >40
    dispute_self_resolution_pct = models.DecimalField(max_digits=5,
                                                      decimal_places=2,
                                                      default=0)  # >70
    holiday_abuse_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                            default=0)         # <2
    qa_answer_rate_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                             default=0)        # >80
    avg_listing_quality = models.DecimalField(max_digits=5, decimal_places=2,
                                              default=0)       # >70
    statement_download_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                                 default=0)    # >60
    shipping_template_coverage_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=0)             # >70
    academy_m1_completion_pct = models.DecimalField(max_digits=5,
                                                    decimal_places=2,
                                                    default=0)  # >85
    broadcast_engagement_pct = models.DecimalField(max_digits=5,
                                                   decimal_places=2,
                                                   default=0)   # >8
    price_competitive_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                                default=0)      # >60
    computed_at = models.DateTimeField(auto_now=True)


# ──────────────────────────────────────────────────────────────────────
# Append-only audit log ("every touch is logged in the DB")
# ──────────────────────────────────────────────────────────────────────

class SellerToolsEvent(models.Model):
    kind = models.CharField(max_length=48, db_index=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name='seller_tools_events')
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    @staticmethod
    def log(kind, actor=None, **payload):
        try:
            SellerToolsEvent.objects.create(
                kind=kind,
                actor=actor if getattr(actor, 'pk', None) else None,
                payload=payload,
            )
        except Exception:
            pass
