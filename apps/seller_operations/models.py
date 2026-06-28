"""
Seller Operations — Deeper (doc: MICHA_Seller_Operations_Deeper.docx)

The Seller Center "operational cockpit". This app owns the genuinely-new
deep seller-operations surface. Chapters that already have a home elsewhere
are BRIDGED (not duplicated) — see services.py for the lazy cross-app calls:

  CH12 coupon self-service  -> apps.promotions / apps.marketing_engine / seller_tools
  CH17 onboarding drip      -> apps.seller_onboarding (SellerEmailLog) + apps.seller checklist
  CH18 reactivation review  -> apps.seller_onboarding.SellerReactivationRequest + SellerHealthScore
  CH13 low-stock signal     -> apps.stock_engine.InventorySku (safety/reorder fields)
  CH5/CH16 price history     -> apps.buyer_experience.ProductPriceHistory (+ anti-fake-discount)
  CH22/CH10 money            -> apps.payments (SellerWallet/PayoutRequest), apps.accounting
  CH20 returns               -> apps.disputes / apps.logistics_ops
  CH23 mobile                -> apps.mobile_app (offline queue, biometrics, push)

Catalog note: the seller catalog is apps.products.Product (store-based, has
sku/barcode/quantity/publish_at/moderation_status). The classifieds-style
apps.listings.Listing is owner-based and NOT the seller-ops catalog.
FK traps: Order.buyer (not user), Order.total (not total_amount),
Order.seller is a User; Store.owner is a User; bank accounts live in apps.payments.
All money is integer cents, ROUND_HALF_UP. Audit tables are INSERT-ONLY.
"""
import uuid

from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


def _default_approver_roles():
    return ['owner', 'manager']


# ---------------------------------------------------------------------------
# CH2 — Seller Sub-Account & Staff Management
# ---------------------------------------------------------------------------
# Permission matrix from doc 2.1, encoded once so token issuance, the @require
# permission checks, and the UI all read from a single source of truth.
# Canonical seller permission catalogue — the authoritative vocabulary
# (IAM/RBAC doc Part 2 CH30). 21 atomic, verb_noun permissions. The role
# bundles below assign deliberate subsets per the CH17 matrix. This is the
# single source of truth; the parametrised matrix test (tests_rbac_matrix.py)
# locks each role to the doc's CH17 grants exactly so an accidental grant or
# drop fails CI.
ALL_SELLER_PERMISSIONS = frozenset({
    'manage_listings', 'view_listings', 'manage_variants', 'view_orders',
    'process_orders', 'mark_shipped', 'print_packing_slip', 'issue_refund',
    'approve_refund', 'view_financials', 'manage_bank_account', 'request_payout',
    'respond_messages', 'bulk_message', 'manage_promotions', 'manage_repricing',
    'manage_staff', 'view_analytics', 'manage_return_policy',
    'manage_integrations', 'close_store',
})

# CH17 seller role-permission matrix (own=all; staff roles = curated subsets).
ROLE_PERMISSIONS = {
    # Owner holds every seller permission, including manage_staff,
    # manage_bank_account, request_payout, close_store.
    'owner': set(ALL_SELLER_PERMISSIONS),
    # Broad operational authority; NO manage_staff, bank account, payout,
    # or close_store (owner-only per CH17 "OWNER PROTECTIONS").
    'manager': {
        'manage_listings', 'view_listings', 'manage_variants', 'view_orders',
        'process_orders', 'mark_shipped', 'print_packing_slip', 'issue_refund',
        'approve_refund', 'view_financials', 'respond_messages', 'bulk_message',
        'manage_promotions', 'manage_repricing', 'view_analytics',
        'manage_return_policy', 'manage_integrations',
    },
    # Customer service: view + respond only. No refunds, financials, edits.
    'cs_agent': {'view_listings', 'view_orders', 'respond_messages'},
    # Fulfilment: view orders, process/ship, manage stock. No pricing/refunds.
    'warehouse': {
        'view_listings', 'manage_variants', 'view_orders', 'process_orders',
        'mark_shipped', 'print_packing_slip',
    },
    # Catalog work only: create/edit listings, variants, repricing rules.
    'listings_only': {
        'manage_listings', 'view_listings', 'manage_variants', 'manage_repricing',
    },
}


class SellerStaff(models.Model):
    """A sub-account under a seller, with a scoped role (doc CH2)."""
    ROLE_CHOICES = [(r, r) for r in ROLE_PERMISSIONS]
    STATUS_CHOICES = [
        ('active', 'active'), ('invited', 'invited'),
        ('suspended', 'suspended'), ('removed', 'removed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_staff')
    invited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                   blank=True, related_name='so_staff_invited')
    full_name = models.CharField(max_length=200)
    email = models.EmailField(max_length=200)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES,
                              default='invited')
    # Invitation: setup link with 7-day expiry (doc CH2 invitation flow).
    invite_token = models.CharField(max_length=64, blank=True, db_index=True)
    invite_expires_at = models.DateTimeField(null=True, blank=True)
    linked_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                    blank=True, related_name='so_staff_identity')
    last_login_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('seller', 'email')
        indexes = [models.Index(fields=['seller', 'status'])]

    @property
    def permissions(self):
        return sorted(ROLE_PERMISSIONS.get(self.role, set()))

    def has_perm(self, perm):
        return perm in ROLE_PERMISSIONS.get(self.role, set())


class SellerStaffAuditLog(models.Model):
    """INSERT-ONLY accountability log — every staff action (doc CH2)."""
    id = models.BigAutoField(primary_key=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_staff_audit')
    staff = models.ForeignKey(SellerStaff, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name='audit_entries')
    action_type = models.CharField(max_length=80)
    target_type = models.CharField(max_length=60, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    payload_summary = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=['seller', '-created_at'])]


# ---------------------------------------------------------------------------
# CH3 — Draft & Scheduled Publishing (sidecar over apps.products.Product)
# ---------------------------------------------------------------------------
class ListingPublishState(models.Model):
    """Publishing state machine for a Product, kept as a non-invasive sidecar
    so the core Product model (relied on by checkout/search) is untouched.
    The scheduled-activation Celery job flips this AND Product.is_active."""
    STATUS_CHOICES = [
        ('DRAFT', 'DRAFT'), ('SCHEDULED', 'SCHEDULED'), ('ACTIVE', 'ACTIVE'),
        ('PAUSED', 'PAUSED'), ('OUT_OF_STOCK', 'OUT_OF_STOCK'),
        ('REMOVED', 'REMOVED'), ('UNDER_REVIEW', 'UNDER_REVIEW'),
    ]
    # doc 3.1 transition table — enforced in services.transition_listing.
    ALLOWED_TRANSITIONS = {
        'DRAFT': {'SCHEDULED', 'ACTIVE', 'REMOVED'},
        'SCHEDULED': {'ACTIVE', 'DRAFT'},
        'ACTIVE': {'PAUSED', 'OUT_OF_STOCK', 'REMOVED', 'UNDER_REVIEW'},
        'PAUSED': {'ACTIVE', 'REMOVED'},
        'OUT_OF_STOCK': {'ACTIVE'},
        'UNDER_REVIEW': {'ACTIVE', 'REMOVED'},
        'REMOVED': set(),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product_id = models.CharField(max_length=64, unique=True, db_index=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_publish_states')
    status = models.CharField(max_length=14, choices=STATUS_CHOICES,
                              default='DRAFT', db_index=True)
    scheduled_publish_at = models.DateTimeField(null=True, blank=True,
                                                db_index=True)
    moderation_passed = models.BooleanField(default=False)
    moderation_notes = models.TextField(blank=True)
    autosave_payload = models.JSONField(default=dict, blank=True)
    autosaved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class ListingPublishTransition(models.Model):
    """INSERT-ONLY log of every publish-state change (correlation/audit)."""
    id = models.BigAutoField(primary_key=True)
    product_id = models.CharField(max_length=64, db_index=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_publish_transitions')
    from_status = models.CharField(max_length=14)
    to_status = models.CharField(max_length=14)
    reason = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ---------------------------------------------------------------------------
# CH4 — Product Cloning (audit; clone creates a real Product)
# ---------------------------------------------------------------------------
class ProductCloneLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_clone_logs')
    source_product_id = models.CharField(max_length=64, db_index=True)
    clone_product_id = models.CharField(max_length=64, db_index=True)
    bulk_batch_id = models.CharField(max_length=64, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ---------------------------------------------------------------------------
# CH5 — Automated Repricing Rules
# ---------------------------------------------------------------------------
class RepricingRule(models.Model):
    RULE_TYPES = [
        ('competitor_based', 'competitor_based'), ('stock_based', 'stock_based'),
        ('time_based', 'time_based'), ('margin_floor', 'margin_floor'),
        ('demand_based', 'demand_based'),
    ]
    SCOPES = [('all_listings', 'all_listings'), ('category', 'category'),
              ('specific_listings', 'specific_listings')]
    FREQ = [('hourly', 'hourly'), ('daily', 'daily'), ('on_trigger', 'on_trigger')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_repricing_rules')
    name = models.CharField(max_length=100)
    rule_type = models.CharField(max_length=20, choices=RULE_TYPES)
    scope = models.CharField(max_length=20, choices=SCOPES, default='all_listings')
    scope_ids = models.JSONField(default=list, blank=True)
    enabled = models.BooleanField(default=True)
    priority = models.IntegerField(default=100)  # higher wins on conflict
    parameters = models.JSONField(default=dict, blank=True)
    # Guardrails — ALWAYS enforced regardless of rule maths (doc 5.1).
    floor_price_cents = models.IntegerField(default=0)
    ceiling_price_cents = models.IntegerField(default=0)  # 0 = no ceiling
    evaluation_frequency = models.CharField(max_length=12, choices=FREQ,
                                            default='daily')
    last_evaluated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['seller', 'enabled'])]
        ordering = ['-priority']


class RepricingAction(models.Model):
    """INSERT-ONLY audit of each automated price change (doc 5.1)."""
    id = models.BigAutoField(primary_key=True)
    rule = models.ForeignKey(RepricingRule, on_delete=models.CASCADE,
                             related_name='actions')
    product_id = models.CharField(max_length=64, db_index=True)
    old_price_cents = models.IntegerField()
    new_price_cents = models.IntegerField()
    reason = models.CharField(max_length=60, default='auto_repricing_rule')
    created_at = models.DateTimeField(auto_now_add=True)


class ManualPriceOverride(models.Model):
    """Seller manual price set disables rules for that listing for 24h."""
    id = models.BigAutoField(primary_key=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_price_overrides')
    product_id = models.CharField(max_length=64, db_index=True)
    overridden_until = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ---------------------------------------------------------------------------
# CH6 — Packing Slip & Bulk Order Export
# ---------------------------------------------------------------------------
class BulkExportJob(models.Model):
    KIND = [
        ('packing_slips_merged', 'packing_slips_merged'),
        ('packing_slips_zip', 'packing_slips_zip'),
        ('order_csv', 'order_csv'), ('order_xlsx', 'order_xlsx'),
        ('pick_list', 'pick_list'),
    ]
    STATUS = [('queued', 'queued'), ('processing', 'processing'),
              ('ready', 'ready'), ('failed', 'failed')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_export_jobs')
    kind = models.CharField(max_length=24, choices=KIND)
    order_ids = models.JSONField(default=list, blank=True)
    filters = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default='queued')
    result_s3_key = models.CharField(max_length=300, blank=True)
    result_url = models.URLField(blank=True)
    row_count = models.IntegerField(default=0)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)


# ---------------------------------------------------------------------------
# CH7 — Shipping Cost Reconciliation
# ---------------------------------------------------------------------------
class ShipmentCostReconciliation(models.Model):
    STATUS = [('pending', 'pending'), ('matched', 'matched'),
              ('overcharge', 'overcharge'), ('undercharge', 'undercharge')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_shipping_recon')
    shipment_id = models.CharField(max_length=64, db_index=True)
    order_id = models.CharField(max_length=64, blank=True, db_index=True)
    shipping_fee_charged_cents = models.IntegerField(default=0)
    actual_carrier_cost_cents = models.IntegerField(default=0)
    difference_cents = models.IntegerField(default=0)  # charged - actual
    declared_weight_g = models.IntegerField(default=0)
    actual_weight_g = models.IntegerField(default=0)
    reconciliation_status = models.CharField(max_length=12, choices=STATUS,
                                             default='pending')
    seller_adjustment_cents = models.IntegerField(default=0)
    fault = models.CharField(max_length=20, blank=True)  # seller/platform/none
    contested = models.BooleanField(default=False)
    contest_evidence_s3_keys = models.JSONField(default=list, blank=True)
    contest_resolved = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reconciled_at = models.DateTimeField(null=True, blank=True)


# ---------------------------------------------------------------------------
# CH8 — Message Auto-Responder
# ---------------------------------------------------------------------------
class SellerAutoResponder(models.Model):
    MODE = [('always', 'always'), ('outside_hours', 'outside_hours'),
            ('holiday', 'holiday')]
    seller = models.OneToOneField(User, on_delete=models.CASCADE,
                                  related_name='so_auto_responder')
    enabled = models.BooleanField(default=False)
    mode = models.CharField(max_length=16, choices=MODE, default='outside_hours')
    business_hours = models.JSONField(default=dict, blank=True)
    message_pt = models.TextField(blank=True)
    delay_minutes = models.IntegerField(default=0)
    include_faq = models.BooleanField(default=False)
    faq_topics = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class AutoReplyLog(models.Model):
    """Tracks the 24h-per-buyer dedup window (doc CH8)."""
    id = models.BigAutoField(primary_key=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_autoreply_log')
    buyer_id = models.CharField(max_length=64, db_index=True)
    message_id = models.CharField(max_length=64, blank=True)
    sent_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ---------------------------------------------------------------------------
# CH9 — Refund Approval Workflow
# ---------------------------------------------------------------------------
class SellerRefundPolicy(models.Model):
    seller = models.OneToOneField(User, on_delete=models.CASCADE,
                                  related_name='so_refund_policy')
    refund_approval_required = models.BooleanField(default=False)
    approval_threshold_cents = models.IntegerField(default=500000)  # 5,000 Kz
    auto_approve_below_cents = models.IntegerField(default=100000)  # 1,000 Kz
    approver_roles = models.JSONField(default=_default_approver_roles,
                                      blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class RefundApprovalRequest(models.Model):
    STATUS = [('pending', 'pending'), ('approved', 'approved'),
              ('rejected', 'rejected'), ('auto_approved', 'auto_approved')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_refund_requests')
    order_id = models.CharField(max_length=64, db_index=True)
    requested_by_staff = models.ForeignKey(SellerStaff, on_delete=models.SET_NULL,
                                           null=True, blank=True,
                                           related_name='refund_requests')
    amount_cents = models.IntegerField()
    reason = models.TextField(blank=True)
    evidence_s3_keys = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=14, choices=STATUS, default='pending',
                              db_index=True)
    reviewed_by_staff = models.ForeignKey(SellerStaff, on_delete=models.SET_NULL,
                                          null=True, blank=True,
                                          related_name='refund_reviews')
    review_note = models.TextField(blank=True)
    owner_escalated = models.BooleanField(default=False)   # > 48h
    admin_escalated = models.BooleanField(default=False)   # > 72h
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)


# ---------------------------------------------------------------------------
# CH10 — Income Tax Summary
# ---------------------------------------------------------------------------
class SellerIncomeTaxSummary(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_income_summaries')
    year = models.IntegerField(db_index=True)
    nif = models.CharField(max_length=40, blank=True)
    gross_sales_cents = models.BigIntegerField(default=0)
    commission_cents = models.BigIntegerField(default=0)
    shipping_costs_cents = models.BigIntegerField(default=0)
    refunds_cents = models.BigIntegerField(default=0)
    chargebacks_cents = models.BigIntegerField(default=0)
    net_earnings_cents = models.BigIntegerField(default=0)
    payouts_cents = models.BigIntegerField(default=0)
    iva_collected_cents = models.BigIntegerField(default=0)
    withholding_tax_cents = models.BigIntegerField(default=0)
    monthly_breakdown = models.JSONField(default=list, blank=True)
    statement_reference = models.CharField(max_length=40, blank=True)
    document_s3_key = models.CharField(max_length=300, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('seller', 'year')


# ---------------------------------------------------------------------------
# CH11 — Store Design & Customisation
# ---------------------------------------------------------------------------
class StoreDesign(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    store_id = models.CharField(max_length=64, unique=True, db_index=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_store_designs')
    hero_desktop_s3_key = models.CharField(max_length=300, blank=True)
    hero_mobile_s3_key = models.CharField(max_length=300, blank=True)
    hero_starts_at = models.DateTimeField(null=True, blank=True)
    hero_ends_at = models.DateTimeField(null=True, blank=True)
    tagline = models.CharField(max_length=200, blank=True)
    announcement_text = models.CharField(max_length=300, blank=True)
    logo_s3_key = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    category_focus_tags = models.JSONField(default=list, blank=True)
    featured_product_ids = models.JSONField(default=list, blank=True)  # cap 8
    featured_auto_refresh = models.BooleanField(default=False)
    sections = models.JSONField(default=list, blank=True)  # store-level groupings
    published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


# ---------------------------------------------------------------------------
# CH12 — Coupon stack config (rest bridges to promotions/marketing_engine)
# ---------------------------------------------------------------------------
class SellerCouponStackConfig(models.Model):
    seller = models.OneToOneField(User, on_delete=models.CASCADE,
                                  related_name='so_coupon_stack')
    stackable_with_platform = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)


# ---------------------------------------------------------------------------
# CH13 — Inventory Alert config (signal bridges to stock_engine)
# ---------------------------------------------------------------------------
class SellerInventoryAlertConfig(models.Model):
    id = models.BigAutoField(primary_key=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_inventory_alerts')
    sku_id = models.CharField(max_length=64, db_index=True)
    custom_threshold_qty = models.IntegerField(null=True, blank=True)
    channel_push = models.BooleanField(default=True)
    channel_email = models.BooleanField(default=True)
    channel_sms = models.BooleanField(default=False)
    channel_whatsapp = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('seller', 'sku_id')


# ---------------------------------------------------------------------------
# CH14 — Fulfilment SLA Tracking
# ---------------------------------------------------------------------------
class FulfilmentSLARecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_sla_records')
    order_id = models.CharField(max_length=64, unique=True, db_index=True)
    processing_days = models.IntegerField(default=2)
    paid_at = models.DateTimeField()
    sla_deadline = models.DateTimeField(db_index=True)
    picked_up_at = models.DateTimeField(null=True, blank=True)
    on_time = models.BooleanField(null=True)  # null until shipped/cancelled
    is_late = models.BooleanField(default=False)
    reminded = models.BooleanField(default=False)
    late_reason = models.CharField(max_length=200, blank=True)
    excused = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SellerSLAExcuse(models.Model):
    STATUS = [('pending', 'pending'), ('approved', 'approved'),
              ('rejected', 'rejected')]
    id = models.BigAutoField(primary_key=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_sla_excuses')
    reason = models.CharField(max_length=200)
    date_from = models.DateField()
    date_to = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)


# ---------------------------------------------------------------------------
# CH15 — Payment Hold Disputes
# ---------------------------------------------------------------------------
class PaymentHoldDispute(models.Model):
    STATUS = [('submitted', 'submitted'), ('under_review', 'under_review'),
              ('resolved_released', 'resolved_released'),
              ('resolved_retained', 'resolved_retained')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_hold_disputes')
    payout_id = models.CharField(max_length=64, db_index=True)
    hold_reason = models.CharField(max_length=60, blank=True)
    seller_contest_reason = models.TextField()
    evidence_s3_keys = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='submitted',
                              db_index=True)
    resolution_note = models.TextField(blank=True)
    escalated_head_finance = models.BooleanField(default=False)  # > 30 days
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)


# ---------------------------------------------------------------------------
# CH16 — Listing Compliance Monitoring
# ---------------------------------------------------------------------------
class ListingComplianceViolation(models.Model):
    ISSUE_TYPES = [
        ('prohibited_keyword', 'prohibited_keyword'),
        ('missing_hs_code', 'missing_hs_code'),
        ('missing_certification', 'missing_certification'),
        ('fake_discount', 'fake_discount'),
        ('weight_discrepancy_pattern', 'weight_discrepancy_pattern'),
    ]
    SEVERITY = [('LOW', 'LOW'), ('MED', 'MED'), ('HIGH', 'HIGH')]
    STATUS = [('open', 'open'), ('fix_pending_review', 'fix_pending_review'),
              ('cleared', 'cleared'), ('auto_removed', 'auto_removed')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_compliance_violations')
    product_id = models.CharField(max_length=64, db_index=True)
    issue_type = models.CharField(max_length=30, choices=ISSUE_TYPES)
    severity = models.CharField(max_length=4, choices=SEVERITY)
    action_required = models.CharField(max_length=200, blank=True)
    deadline = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='open',
                              db_index=True)
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['seller', 'status'])]


# ---------------------------------------------------------------------------
# CH17 — Activation milestones (drip bridges to seller_onboarding)
# ---------------------------------------------------------------------------
class SellerActivationState(models.Model):
    seller = models.OneToOneField(User, on_delete=models.CASCADE,
                                  related_name='so_activation_state')
    kyc_complete = models.BooleanField(default=False)
    bank_account_added = models.BooleanField(default=False)
    first_listing_active = models.BooleanField(default=False)
    shipping_template_configured = models.BooleanField(default=False)
    return_policy_configured = models.BooleanField(default=False)
    academy_module1_complete = models.BooleanField(default=False)
    first_order_on_time = models.BooleanField(default=False)
    activated = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True, blank=True)
    badge_expires_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    MILESTONE_FIELDS = [
        'kyc_complete', 'bank_account_added', 'first_listing_active',
        'shipping_template_configured', 'return_policy_configured',
        'academy_module1_complete', 'first_order_on_time',
    ]

    @property
    def completed_count(self):
        return sum(1 for f in self.MILESTONE_FIELDS if getattr(self, f))


# ---------------------------------------------------------------------------
# CH18 — Performance Recovery Plan (review bridges to seller_onboarding)
# ---------------------------------------------------------------------------
class SellerRecoveryPlan(models.Model):
    SUSPENSION_TYPES = [
        ('auto', 'auto'), ('violation', 'violation'),
        ('manual', 'manual'), ('payment', 'payment'),
    ]
    STATUS = [('active', 'active'), ('submitted', 'submitted'),
              ('reinstated', 'reinstated'), ('rejected', 'rejected')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_recovery_plans')
    suspension_type = models.CharField(max_length=12, choices=SUSPENSION_TYPES)
    suspension_reason = models.TextField(blank=True)
    required_steps = models.JSONField(default=list, blank=True)  # [{key,label,done}]
    status = models.CharField(max_length=12, choices=STATUS, default='active',
                              db_index=True)
    probation_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)


# ---------------------------------------------------------------------------
# CH19 — Competitor & Market Intelligence
# ---------------------------------------------------------------------------
class SellerMarketBenchmark(models.Model):
    id = models.BigAutoField(primary_key=True)
    category_id = models.CharField(max_length=64, db_index=True)
    week_start = models.DateField(db_index=True)
    median_price_cents = models.IntegerField(default=0)
    price_min_cents = models.IntegerField(default=0)
    price_max_cents = models.IntegerField(default=0)
    avg_on_time_pct = models.FloatField(default=0)
    avg_dispute_rate_pct = models.FloatField(default=0)
    avg_rating = models.FloatField(default=0)
    avg_response_hours = models.FloatField(default=0)
    top_search_terms = models.JSONField(default=list, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('category_id', 'week_start')


# ---------------------------------------------------------------------------
# CH20 — Returns Management Centre (return inspection decision)
# ---------------------------------------------------------------------------
class ReturnInspection(models.Model):
    CONDITION = [('perfect', 'perfect'), ('good', 'good'),
                 ('damaged', 'damaged'), ('counterfeit', 'counterfeit')]
    ACTION = [('restock', 'restock'), ('write_off', 'write_off'),
              ('dispute', 'dispute'), ('ts_escalation', 'ts_escalation')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_return_inspections')
    order_id = models.CharField(max_length=64, db_index=True)
    return_id = models.CharField(max_length=64, blank=True, db_index=True)
    sku_id = models.CharField(max_length=64, blank=True)
    quantity = models.IntegerField(default=1)
    condition = models.CharField(max_length=12, choices=CONDITION)
    action = models.CharField(max_length=14, choices=ACTION)
    restocked = models.BooleanField(default=False)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ---------------------------------------------------------------------------
# CH21 — Bulk Messaging (post-order)
# ---------------------------------------------------------------------------
class SellerBulkMessage(models.Model):
    SCOPE = [('order_date_range', 'order_date_range'),
             ('product_buyers', 'product_buyers'),
             ('open_disputes', 'open_disputes')]
    STATUS = [('pending_moderation', 'pending_moderation'),
              ('blocked', 'blocked'), ('sent', 'sent')]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_bulk_messages')
    scope = models.CharField(max_length=20, choices=SCOPE)
    from_date = models.DateField(null=True, blank=True)
    to_date = models.DateField(null=True, blank=True)
    product_id = models.CharField(max_length=64, blank=True)
    message = models.TextField()
    channel = models.CharField(max_length=12, default='in_app')
    status = models.CharField(max_length=20, choices=STATUS,
                              default='pending_moderation')
    moderation_reason = models.CharField(max_length=120, blank=True)
    recipient_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class SellerBulkMessageRecipient(models.Model):
    """One row per (message, order) — enforces 1-per-order harassment cap."""
    id = models.BigAutoField(primary_key=True)
    bulk_message = models.ForeignKey(SellerBulkMessage, on_delete=models.CASCADE,
                                     related_name='recipients')
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='so_bulk_recipients')
    buyer_id = models.CharField(max_length=64, db_index=True)
    order_id = models.CharField(max_length=64, db_index=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # A buyer cannot be re-messaged about the SAME order (doc CH21).
        unique_together = ('seller', 'order_id')


# ---------------------------------------------------------------------------
# CH24 — KPI snapshot + universal audit event
# ---------------------------------------------------------------------------
class SellerOperationsKpiSnapshot(models.Model):
    id = models.BigAutoField(primary_key=True)
    snapshot_date = models.DateField(unique=True, db_index=True)
    activation_rate_pct = models.FloatField(default=0)
    median_processing_hours = models.FloatField(default=0)
    on_time_fulfilment_pct = models.FloatField(default=0)
    auto_responder_adoption_pct = models.FloatField(default=0)
    scheduled_listing_usage_pct = models.FloatField(default=0)
    repricing_adoption_pct = models.FloatField(default=0)
    avg_compliance_score_pct = models.FloatField(default=0)
    refund_approval_sla_pct = models.FloatField(default=0)
    suspension_recovery_pct = models.FloatField(default=0)
    return_response_rate_pct = models.FloatField(default=0)
    active_repricing_rules = models.IntegerField(default=0)
    open_compliance_violations = models.IntegerField(default=0)
    pending_refund_approvals = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class SellerOperationsEvent(models.Model):
    """INSERT-ONLY universal audit. log() NEVER raises (fail-open)."""
    id = models.BigAutoField(primary_key=True)
    kind = models.CharField(max_length=60, db_index=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name='so_events')
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    @staticmethod
    def log(kind, actor=None, **payload):
        try:
            SellerOperationsEvent.objects.create(
                kind=kind, actor=actor if _is_user(actor) else None,
                payload=_jsonable(payload))
        except Exception:
            pass


def _is_user(obj):
    return obj is not None and hasattr(obj, 'pk') and hasattr(obj, 'is_authenticated')


def _jsonable(d):
    out = {}
    for k, v in d.items():
        try:
            import json
            json.dumps(v)
            out[k] = v
        except Exception:
            out[k] = str(v)
    return out
