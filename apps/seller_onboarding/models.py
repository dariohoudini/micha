"""
Seller Acquisition & Onboarding Models
======================================

Implements the AliExpress Seller Acquisition & Onboarding workflow
(CH1–CH22) end-to-end at the DB layer. Every chapter that describes
a table or a state machine has a model here:

    CH1.2  SellerLead                        — top-of-funnel CRM row
    CH2.2  SellerApplication                 — full FSM with status enum
    CH3    KycDocument                       — per-document OCR record
    CH4    AgreementTemplate, SellerAgreement — versioned legal contract
    CH5.2  SellerFeeInvoice                  — annual platform fee
    CH8    SellerTrainingProgress, SellerCertificate — Seller Academy
    CH9.1  SellerWelcomeBoost, SellerAdCredit, SellerCommissionOverride
    CH10.2 SellerCategoryEnrolment           — open/restricted/L1/L2/L3
    CH11   SellerCategoryUpgradeRequest      — tier-gated upgrades
    CH12   SellerBrand                       — own brand / authorised reseller
    CH14   SellerTierState, SellerTierHistory
    CH16   SellerHealthScore                 — daily 0-100 composite
    CH18   SellerHolidayLog                  — pause history + quota
    CH20   SellerReactivationRequest         — suspended → active

The doc is AliExpress-spec but we're shipping the Angola market via
MICHA. So a handful of fields (annual_fee_currency=AOA, qualification
score country tiers) are tuned for Angola in get_supported_countries()
and qualify_lead(). The model shapes match the doc 1:1.

Every state transition writes a SellerOnboardingEvent row — the
append-only audit log called out by the user ("every touch is logged
in the DB"). Reviewer actions, system gates, email sends, and seller
self-service all flow through emit_event().
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


# ── Choice enums ──────────────────────────────────────────────────

LEAD_SOURCE_CHOICES = (
    ('inbound_web', 'Inbound — Web'),
    ('outbound_bd', 'Outbound — Business Dev'),
    ('trade_show', 'Trade Show'),
    ('referral', 'Referral'),
    ('partner', 'Partner'),
    ('enterprise', 'Enterprise'),
)

LEAD_STATUS_CHOICES = (
    ('new', 'New'),
    ('contacted', 'Contacted'),
    ('qualified', 'Qualified'),
    ('applied', 'Applied'),
    ('rejected', 'Rejected'),
    ('converted', 'Converted'),
    ('lost', 'Lost'),
)

APPLICATION_STATUS_CHOICES = (
    ('draft',            'Draft'),
    ('submitted',        'Submitted'),
    ('kyc_pending',      'KYC — awaiting docs'),
    ('kyc_review',       'KYC — under review'),
    ('kyc_approved',     'KYC approved'),
    ('kyc_rejected',     'KYC rejected'),
    ('more_info',        'More info requested'),
    ('agreement_sent',   'Agreement sent'),
    ('agreement_signed', 'Agreement signed'),
    ('fee_pending',      'Fee pending'),
    ('fee_paid',         'Fee paid'),
    ('approved',         'Approved — seller active'),
    ('rejected',         'Rejected'),
    ('abandoned',        'Abandoned'),
)

# Valid transitions per CH2.2. Anything not in here is rejected by
# apply_transition() — keeps the state machine honest.
APPLICATION_TRANSITIONS = {
    'draft':            ('submitted', 'abandoned'),
    'submitted':        ('kyc_pending', 'rejected'),
    'kyc_pending':      ('kyc_review', 'abandoned'),
    'kyc_review':       ('kyc_approved', 'kyc_rejected', 'more_info'),
    'kyc_approved':     ('agreement_sent',),
    'more_info':        ('kyc_review', 'abandoned'),
    'agreement_sent':   ('agreement_signed', 'abandoned'),
    'agreement_signed': ('fee_pending',),
    'fee_pending':      ('fee_paid', 'abandoned'),
    'fee_paid':         ('approved',),
    'kyc_rejected':     ('rejected',),
    'approved':         (),
    'rejected':         (),
    'abandoned':        ('submitted',),  # re-engagement allowed
}

KYC_DOCUMENT_TYPE_CHOICES = (
    ('business_licence',   'Business Licence'),
    ('vat_certificate',    'VAT Certificate'),
    ('rep_id_front',       'Legal Rep ID — Front'),
    ('rep_id_back',        'Legal Rep ID — Back'),
    ('rep_selfie',         'Legal Rep Selfie'),
    ('bank_statement',     'Bank Statement / IBAN Letter'),
    ('brand_auth_letter',  'Brand Authorisation Letter'),
    ('safety_certificate', 'Product Safety Certificate'),
    ('import_licence',     'Import/Export Licence'),
)

KYC_DOCUMENT_STATUS_CHOICES = (
    ('uploaded',     'Uploaded'),
    ('ocr_pending',  'OCR pending'),
    ('ocr_complete', 'OCR complete'),
    ('approved',     'Approved'),
    ('rejected',     'Rejected'),
)

AGREEMENT_STATUS_CHOICES = (
    ('pending_signature', 'Pending signature'),
    ('signed',            'Signed'),
    ('expired',           'Expired'),
    ('superseded',        'Superseded by newer version'),
)

CATEGORY_TYPE_CHOICES = (
    ('open',           'Open — instant'),
    ('restricted_l1',  'Restricted — Level 1 (safety certs)'),
    ('restricted_l2',  'Restricted — Level 2 (brand/licence)'),
    ('restricted_l3',  'Restricted — Level 3 (BD approval)'),
    ('prohibited',     'Prohibited'),
)

CATEGORY_ENROLMENT_STATUS_CHOICES = (
    ('pending',   'Pending review'),
    ('approved',  'Approved'),
    ('rejected',  'Rejected'),
    ('expired',   'Expired'),
    ('suspended', 'Suspended'),
)

SELLER_TIER_CHOICES = (
    ('standard', 'Standard'),
    ('bronze',   'Bronze'),
    ('silver',   'Silver'),
    ('gold',     'Gold'),
    ('platinum', 'Platinum'),
    ('diamond',  'Diamond'),
)

TIER_ORDER = ['standard', 'bronze', 'silver', 'gold', 'platinum', 'diamond']

BRAND_TYPE_CHOICES = (
    ('own_brand',          'Own brand'),
    ('authorised_reseller','Authorised reseller'),
)

BRAND_STATUS_CHOICES = (
    ('pending',  'Pending'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('expired',  'Expired (authorisation lapsed)'),
)

TRAINING_MODULE_CHOICES = (
    ('M1', 'Platform Fundamentals'),
    ('M2', 'Listing Excellence'),
    ('M3', 'Pricing & Promotions'),
    ('M4', 'Order Management & Fulfilment'),
    ('M5', 'Customer Service Excellence'),
    ('M6', 'Advertising'),
    ('M7', 'Advanced Analytics'),
    ('M8', 'Choice Programme'),
)

TRAINING_STATUS_CHOICES = (
    ('not_started', 'Not started'),
    ('in_progress', 'In progress'),
    ('completed',   'Completed'),
    ('failed',      'Failed'),
)


# ── CH1.2 — Lead capture ──────────────────────────────────────────

class SellerLead(models.Model):
    """Top-of-funnel CRM record. Every visitor who fills the "Sell on
    MICHA" form lands here, regardless of qualification outcome."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead_source = models.CharField(max_length=20, choices=LEAD_SOURCE_CHOICES)
    referral_code = models.CharField(max_length=50, blank=True, default='')
    company_name = models.CharField(max_length=255)
    contact_name = models.CharField(max_length=100)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=30)
    # ISO 3166-1 alpha-2. Indexed because every funnel report groups
    # by country and we have orders of magnitude more reads than writes.
    country = models.CharField(max_length=2, db_index=True)
    primary_category = models.CharField(max_length=100, blank=True, default='')
    estimated_sku_count = models.PositiveIntegerField(default=0)
    annual_revenue_bracket = models.CharField(max_length=50, blank=True, default='')
    has_brand = models.BooleanField(default=False)
    current_platforms = models.CharField(max_length=500, blank=True, default='')

    # UTM tracking for the §1.1 paid-acquisition funnel.
    utm_source = models.CharField(max_length=100, blank=True, default='')
    utm_medium = models.CharField(max_length=100, blank=True, default='')
    utm_campaign = models.CharField(max_length=100, blank=True, default='')

    bd_owner = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='owned_leads',
    )
    status = models.CharField(
        max_length=20, choices=LEAD_STATUS_CHOICES, default='new', db_index=True,
    )
    qualification_score = models.PositiveSmallIntegerField(default=0)
    qualification_breakdown = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_contacted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['country', 'status']),
            models.Index(fields=['lead_source']),
        ]

    def __str__(self):
        return f'{self.company_name} ({self.country}) — {self.status}'


# ── CH2.2 — Application FSM ───────────────────────────────────────

class SellerApplication(models.Model):
    """The full application from first form submit through to seller
    activation. Holds the state machine that drives every email,
    review queue assignment, and side-effect downstream."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(
        SellerLead, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='applications',
    )

    # The applying user — only present once the seller has registered.
    # Lead → unauthenticated form. Application → may convert to a
    # registered MICHA user. Once approved → linked to the active
    # seller User via `seller`.
    applicant_email = models.EmailField(db_index=True)
    applicant = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='seller_applications',
    )
    seller = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='active_seller_application',
    )

    status = models.CharField(
        max_length=24, choices=APPLICATION_STATUS_CHOICES, default='draft',
        db_index=True,
    )

    # CH2.1 form fields (the doc spec — every field that matters for
    # cross-validation against KYC docs is stored here so reviewers
    # can diff side-by-side without re-reading the form payload).
    company_name = models.CharField(max_length=255)
    country = models.CharField(max_length=2)
    business_reg_number = models.CharField(max_length=100, blank=True, default='')
    legal_representative_name = models.CharField(max_length=255, blank=True, default='')
    legal_representative_id_type = models.CharField(max_length=30, blank=True, default='')
    contact_phone = models.CharField(max_length=30, blank=True, default='')
    primary_category_id = models.CharField(max_length=64, blank=True, default='')
    return_address = models.JSONField(default=dict, blank=True)
    estimated_monthly_orders = models.CharField(max_length=30, blank=True, default='')
    referral_code = models.CharField(max_length=50, blank=True, default='')

    # Review pipeline metadata.
    reviewer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_applications',
    )
    rejection_reason = models.CharField(max_length=500, blank=True, default='')
    # Structured codes — array-like for SQLite. Caller sets/clears.
    rejection_codes = models.JSONField(default=list, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    # 0–100 OCR confidence + reviewer kicker (CH3.3).
    kyc_score = models.PositiveSmallIntegerField(default=0)

    # CH2.3 — auto-eligibility gate results. Persisted so we don't
    # silently fail the same applicant repeatedly without telling them
    # what's wrong.
    eligibility_passed = models.BooleanField(default=False)
    eligibility_failure_code = models.CharField(max_length=64, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'country']),
            models.Index(fields=['submitted_at']),
        ]

    def __str__(self):
        return f'{self.company_name} ({self.country}) — {self.status}'

    # FSM helper. Raises ValueError on invalid transitions so callers
    # can't accidentally skip a step (e.g. submitted → approved).
    def apply_transition(self, new_status, *, actor=None, notes='', metadata=None):
        from .signals import application_status_changed
        allowed = APPLICATION_TRANSITIONS.get(self.status, ())
        if new_status not in allowed:
            raise ValueError(
                f'Invalid transition {self.status} → {new_status} '
                f'(allowed: {", ".join(allowed) or "none"})'
            )
        old_status = self.status
        self.status = new_status
        # Stamp the lifecycle timestamps so the funnel queries in
        # CH24.2 work without joins.
        now = timezone.now()
        if new_status == 'submitted' and not self.submitted_at:
            self.submitted_at = now
        if new_status in ('kyc_approved', 'kyc_rejected', 'rejected') and not self.reviewed_at:
            self.reviewed_at = now
        if new_status == 'approved' and not self.approved_at:
            self.approved_at = now
        self.save(update_fields=[
            'status', 'submitted_at', 'reviewed_at', 'approved_at', 'updated_at',
        ])
        SellerOnboardingEvent.log(
            application=self, kind='application.status_changed', actor=actor,
            payload={'from': old_status, 'to': new_status,
                     'notes': notes[:500] if notes else '',
                     **(metadata or {})},
        )
        application_status_changed.send(
            sender=SellerApplication, application=self,
            old_status=old_status, new_status=new_status, actor=actor,
        )
        return self


# ── CH3 — KYC documents ──────────────────────────────────────────

class KycDocument(models.Model):
    """One row per uploaded document. OCR fields and discrepancies are
    captured here so the reviewer's side-by-side panel has all data
    without joining back to the application payload."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        SellerApplication, on_delete=models.CASCADE, related_name='kyc_documents',
    )
    document_type = models.CharField(max_length=40, choices=KYC_DOCUMENT_TYPE_CHOICES)
    file_key = models.CharField(max_length=255)  # S3/local storage key
    status = models.CharField(
        max_length=20, choices=KYC_DOCUMENT_STATUS_CHOICES, default='uploaded',
    )
    ocr_fields = models.JSONField(default=dict, blank=True)
    ocr_confidence = models.FloatField(default=0.0)
    discrepancies = models.JSONField(default=list, blank=True)
    liveness_score = models.FloatField(default=0.0)   # selfie only
    face_match_score = models.FloatField(default=0.0) # selfie vs ID
    ocr_completed_at = models.DateTimeField(null=True, blank=True)
    reviewer_notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['application', 'document_type'])]


# ── CH4 — Agreements ─────────────────────────────────────────────

class AgreementTemplate(models.Model):
    """Version-controlled agreement copy. The doc spells out a re-sign
    flow (4.3) so we keep templates as first-class records — when a
    template's requires_re_sign=True is set, the recurring job
    re-binds every active seller to it."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    version = models.CharField(max_length=20, db_index=True)
    # JSON arrays so SQLite plays nicely. ['*'] = global.
    country_scope = models.JSONField(default=list)
    category_scope = models.JSONField(default=list)
    change_summary = models.TextField(blank=True, default='')
    body = models.TextField()  # the agreement copy with {{MERGE_FIELDS}}
    requires_re_sign = models.BooleanField(default=False)
    effective_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-effective_date', '-created_at']
        unique_together = [('version',)]


class SellerAgreement(models.Model):
    """A personalised, signed (or pending) agreement. SHA-256 of the
    body+signature+ip is stored so we can detect tampering long after
    the fact — that hash is the legal evidence."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        SellerApplication, on_delete=models.CASCADE, related_name='agreements',
    )
    template = models.ForeignKey(AgreementTemplate, on_delete=models.PROTECT)
    seller = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='seller_agreements',
    )
    body_personalised = models.TextField()
    pdf_key = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(
        max_length=24, choices=AGREEMENT_STATUS_CHOICES, default='pending_signature',
    )
    signing_token = models.CharField(max_length=64, db_index=True, unique=True)
    expires_at = models.DateTimeField()
    signed_at = models.DateTimeField(null=True, blank=True)
    signer_ip = models.GenericIPAddressField(null=True, blank=True)
    signer_ua = models.CharField(max_length=255, blank=True, default='')
    signature_name = models.CharField(max_length=255, blank=True, default='')
    signature_hash = models.CharField(max_length=64, blank=True, default='')
    scroll_completion_pct = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @staticmethod
    def generate_token():
        return secrets.token_urlsafe(48)[:64]

    def compute_signature_hash(self):
        raw = (
            (self.body_personalised or '') + '|' +
            (self.signature_name or '') + '|' +
            (str(self.signer_ip) if self.signer_ip else '') + '|' +
            (self.signed_at.isoformat() if self.signed_at else '')
        )
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()


# ── CH5.2 — Annual fee ───────────────────────────────────────────

class SellerFeeInvoice(models.Model):
    """The platform annual fee. Doc CH5.2 is denominated in USD/EUR
    per country; MICHA-Angola adds AOA as the default currency. The
    discount stack (first-year, BD-strategic, score>90) is replayable
    via `discounts` JSON so finance can audit how a final_amount was
    arrived at."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        SellerApplication, on_delete=models.CASCADE, related_name='fee_invoices',
    )
    seller = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fee_invoices',
    )
    base_amount = models.DecimalField(max_digits=12, decimal_places=2)
    discounts = models.JSONField(default=list, blank=True)
    final_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(
        max_length=20, default='pending',
        choices=(('pending', 'Pending'), ('paid', 'Paid'),
                 ('overdue', 'Overdue'), ('waived', 'Waived'),
                 ('refunded', 'Refunded')),
    )
    due_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    payment_reference = models.CharField(max_length=120, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


# ── CH8 — Training & certificates ────────────────────────────────

class SellerTrainingProgress(models.Model):
    """One row per (seller, module). PK is composite so a re-attempt
    on the same module updates the existing row instead of creating
    duplicates. Quiz attempts are capped at the model level by the
    view that records them."""

    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='training_progress')
    module_id = models.CharField(max_length=10, choices=TRAINING_MODULE_CHOICES)
    status = models.CharField(
        max_length=20, choices=TRAINING_STATUS_CHOICES, default='not_started',
    )
    progress_pct = models.PositiveSmallIntegerField(default=0)
    quiz_attempts = models.PositiveSmallIntegerField(default=0)
    quiz_score = models.PositiveSmallIntegerField(default=0)
    passed = models.BooleanField(default=False)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('seller', 'module_id')]
        indexes = [models.Index(fields=['seller', 'passed'])]


class SellerCertificate(models.Model):
    """Issued on training pass. `certificate_hash` is part of the
    public verification URL flow — a third party can confirm a
    certificate is genuine by hashing the public payload and matching
    against this row."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='certificates')
    module_id = models.CharField(max_length=10, choices=TRAINING_MODULE_CHOICES)
    certificate_type = models.CharField(max_length=64)
    issued_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    verification_url = models.URLField(blank=True, default='')
    certificate_hash = models.CharField(max_length=64, db_index=True)

    class Meta:
        ordering = ['-issued_at']


# ── CH9.1 — Welcome package ──────────────────────────────────────

class SellerVisibilityBoost(models.Model):
    """Search ranking boost applied automatically on activation
    (1.3× for the first 90 days) and bumped per tier upgrade."""

    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='visibility_boosts')
    boost_type = models.CharField(max_length=64)
    boost_multiplier = models.FloatField()
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    applies_to = models.CharField(max_length=64, default='all_listings')
    created_at = models.DateTimeField(auto_now_add=True)


class SellerAdCredit(models.Model):
    """Credit pool for AliExpress-equivalent paid promotion. Decremented
    when the seller spends on Sponsored Listings; expires per the
    welcome package rules (60 days for new-seller credits)."""

    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ad_credits')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    spent_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    credit_type = models.CharField(max_length=64)
    valid_until = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class SellerCommissionOverride(models.Model):
    """Temporary commission rate (e.g. 50% reduction for first 30 days)."""

    seller = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='commission_overrides',
    )
    rate = models.DecimalField(max_digits=5, decimal_places=4)
    reason = models.CharField(max_length=64)
    valid_until = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


# ── CH10.2 — Category enrolment ──────────────────────────────────

class SellerCategoryEnrolment(models.Model):
    """Which categories a seller may list in. Open categories are
    auto-approved on insert; restricted L1/L2 go to a review queue;
    L3 is BD-approval; prohibited never lands here (it's blocked at
    request time and logged as a security event)."""

    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='category_enrolments')
    category_id = models.CharField(max_length=64)
    enrolment_type = models.CharField(
        max_length=20,
        choices=(('open', 'Open'), ('restricted_l1', 'L1'),
                 ('restricted_l2', 'L2'), ('restricted_l3', 'L3')),
    )
    status = models.CharField(
        max_length=20, choices=CATEGORY_ENROLMENT_STATUS_CHOICES, default='pending',
    )
    documents_submitted = models.JSONField(default=list, blank=True)
    reviewer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_category_enrolments',
    )
    rejection_reason = models.TextField(blank=True, default='')
    approved_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('seller', 'category_id')]


class SellerCategoryUpgradeRequest(models.Model):
    """CH11 — explicit upgrade path from open/L1 to a higher tier.
    Snapshots the seller's metrics at request time so the reviewer
    can see exactly what was used to evaluate eligibility (and so a
    later metric drift can't be confused with bad reviewer judgment)."""

    seller = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='category_upgrade_requests',
    )
    current_category_id = models.CharField(max_length=64)
    target_category_id = models.CharField(max_length=64)
    upgrade_reason = models.TextField()
    supporting_docs = models.JSONField(default=list, blank=True)
    metrics_snapshot = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20, default='pending',
        choices=(('pending', 'Pending'), ('approved', 'Approved'),
                 ('rejected', 'Rejected'), ('more_info', 'More info')),
    )
    reviewer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_upgrade_requests',
    )
    decision_notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)


# ── CH12 — Brands ────────────────────────────────────────────────

class SellerBrand(models.Model):
    """Verified brand on the platform. Own-brand verification requires
    trademark certs; authorised-reseller flow requires an auth letter
    + territory scope (CH12.2)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='brands')
    brand_name = models.CharField(max_length=255)
    brand_type = models.CharField(max_length=24, choices=BRAND_TYPE_CHOICES)
    logo_key = models.CharField(max_length=255, blank=True, default='')
    trademark_registered = models.BooleanField(default=False)
    trademark_documents = models.JSONField(default=list, blank=True)
    brand_story = models.TextField(blank=True, default='')
    product_examples = models.JSONField(default=list, blank=True)
    website_url = models.URLField(blank=True, default='')
    # CH12.2 — geographic enforcement. Empty array = global.
    allowed_territories = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=BRAND_STATUS_CHOICES, default='pending')
    verified_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)  # auth letter expiry
    rejection_reason = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['seller', 'status'])]


# ── CH14 — Tier state ────────────────────────────────────────────

class SellerTierState(models.Model):
    """Current tier per seller. Computed monthly by tier_recalculation
    Celery task. `pending_tier` + `downgrade_warning_sent_at` model
    the 30-day grace before a downgrade actually takes effect
    (CH15.1)."""

    seller = models.OneToOneField(User, on_delete=models.CASCADE, related_name='tier_state')
    current_tier = models.CharField(max_length=20, choices=SELLER_TIER_CHOICES, default='standard')
    pending_tier = models.CharField(
        max_length=20, choices=SELLER_TIER_CHOICES, blank=True, default='',
    )
    last_score = models.PositiveSmallIntegerField(default=0)
    last_metrics = models.JSONField(default=dict, blank=True)
    tier_updated_at = models.DateTimeField(auto_now=True)
    downgrade_warning_sent_at = models.DateTimeField(null=True, blank=True)


class SellerTierHistory(models.Model):
    """Append-only ledger of tier changes for reporting + appeals."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tier_history')
    old_tier = models.CharField(max_length=20, choices=SELLER_TIER_CHOICES)
    new_tier = models.CharField(max_length=20, choices=SELLER_TIER_CHOICES)
    computed_score = models.PositiveSmallIntegerField()
    metrics_snapshot = models.JSONField(default=dict, blank=True)
    effective_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-effective_date']


# ── CH16 — Health score ──────────────────────────────────────────

class SellerHealthScore(models.Model):
    """Daily snapshot of the composite 0–100 score. We persist a row
    per (seller, snapshot_date) so dashboards can render a trend
    without recomputing — and so an admin can answer "what was their
    health score on the day of the incident?" months later."""

    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='health_scores')
    snapshot_date = models.DateField(db_index=True)
    score = models.PositiveSmallIntegerField()
    feedback_component = models.FloatField(default=0.0)
    dispute_component = models.FloatField(default=0.0)
    shipping_component = models.FloatField(default=0.0)
    response_component = models.FloatField(default=0.0)
    listing_quality_component = models.FloatField(default=0.0)
    returns_component = models.FloatField(default=0.0)
    intervention_band = models.CharField(
        max_length=20,
        choices=(('excellent', 'Excellent (80-100)'),
                 ('good', 'Good (60-79)'),
                 ('at_risk', 'At risk (40-59)'),
                 ('poor', 'Poor (20-39)'),
                 ('critical', 'Critical (0-19)')),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('seller', 'snapshot_date')]
        indexes = [models.Index(fields=['seller', '-snapshot_date'])]


# ── CH18 — Holiday log ───────────────────────────────────────────

class SellerHolidayLog(models.Model):
    """Per-activation row. The 30-day cap and 3-per-year quota are
    enforced by querying this table (count + sum-of-duration)."""

    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='holiday_logs')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=255, blank=True, default='')
    message_to_buyers = models.TextField(blank=True, default='')
    activated_at = models.DateTimeField(auto_now_add=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    early_deactivated = models.BooleanField(default=False)


# ── CH20.2 — Reactivation ────────────────────────────────────────

class SellerReactivationRequest(models.Model):
    seller = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='reactivation_requests',
    )
    suspension_reason = models.CharField(max_length=80)
    suspension_reason_acknowledged = models.BooleanField(default=False)
    corrective_actions = models.TextField()
    supporting_docs = models.JSONField(default=list, blank=True)
    improvement_plan = models.TextField(blank=True, default='')
    status = models.CharField(
        max_length=20, default='pending',
        choices=(('pending', 'Pending'), ('approved', 'Approved'),
                 ('rejected', 'Rejected'), ('auto_approved', 'Auto-approved')),
    )
    reviewer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reactivation_decisions',
    )
    decision_notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)


# ── Append-only audit log ────────────────────────────────────────

class SellerOnboardingEvent(models.Model):
    """Every onboarding-flow side-effect writes one row. This is the
    "every touch is logged in the DB" guarantee for this domain. Index
    on (application, kind) so the admin panel can render a per-app
    timeline cheaply."""

    id = models.BigAutoField(primary_key=True)
    application = models.ForeignKey(
        SellerApplication, on_delete=models.CASCADE,
        related_name='events', null=True, blank=True,
    )
    seller = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='onboarding_events',
    )
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='emitted_onboarding_events',
    )
    kind = models.CharField(max_length=64, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['application', 'kind'])]

    @staticmethod
    def log(*, application=None, seller=None, actor=None, kind, payload=None):
        try:
            return SellerOnboardingEvent.objects.create(
                application=application, seller=seller, actor=actor,
                kind=kind, payload=payload or {},
            )
        except Exception:
            # NEVER let an audit-log write fail a business operation.
            # If the table is gone or the DB is read-only, we swallow
            # — the caller already has the primary side-effect.
            return None


# ─────────────────────────────────────────────────────────────────
# CH6 — Onboarding email drip
# ─────────────────────────────────────────────────────────────────

EMAIL_SEQUENCE_CHOICES = (
    ('day0_welcome',           'D0 — Welcome'),
    ('day1_no_login',          'D1 — No login yet'),
    ('day2_setup_3_things',    'D2 — 3 things before first sale'),
    ('day3_profile_incomplete','D3 — Profile <50%'),
    ('day4_first_listing',     'D4 — Ready to list?'),
    ('day5_no_listing',        'D5 — Sellers who list in 5 days'),
    ('day7_optimise_listing',  'D7 — Optimise your listing'),
    ('day10_no_orders',        'D10 — How top sellers get first sale'),
    ('day14_training',         'D14 — Certified sellers earn 28% more'),
    ('day21_first_order',      'D21 — Your first sale'),
    ('day30_checkin',          'D30 — First month performance'),
    ('day45_no_shipping',      'D45 — Set up shipping'),
    ('day60_tier',             'D60 — Path to Gold'),
    ('day90_benchmark',        'D90 — Top sellers in your category'),
    # Behaviour-triggered transactional (CH6.2).
    ('tx_kyc_approved',        'TX — KYC approved'),
    ('tx_agreement_signed',    'TX — Agreement signed'),
    ('tx_alipay_linked',       'TX — Alipay linked'),
    ('tx_first_listing_under_review', 'TX — First listing under review'),
    ('tx_listing_rejected',    'TX — Listing rejected'),
    ('tx_first_order',         'TX — First order'),
    ('tx_shipping_overdue',    'TX — Shipping overdue'),
    ('tx_dispute_opened',      'TX — Dispute opened'),
    ('tx_fee_renewal_60d',     'TX — Fee renewal D-60'),
    ('tx_tier_upgrade',        'TX — Tier upgrade'),
    ('tx_tier_downgrade_warn', 'TX — Tier downgrade warning'),
    ('tx_payout_sent',         'TX — Payout sent'),
)


class SellerEmailLog(models.Model):
    """Records every onboarding email queued + sent. Acts as the
    suppression ledger: before queueing a drip step we check
    .filter(seller=, sequence_key=).exists().

    `sent_at` is set when the provider acknowledges acceptance
    (SendGrid/SES). In dev we mark `sent_at` immediately on enqueue
    so the suppression logic still works without a real provider."""

    id = models.BigAutoField(primary_key=True)
    seller = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='onboarding_emails',
        null=True, blank=True,
    )
    application = models.ForeignKey(
        SellerApplication, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='onboarding_emails',
    )
    sequence_key = models.CharField(max_length=64, choices=EMAIL_SEQUENCE_CHOICES, db_index=True)
    to_email = models.EmailField()
    subject = models.CharField(max_length=255)
    body_preview = models.TextField(blank=True, default='')
    template_context = models.JSONField(default=dict, blank=True)
    provider = models.CharField(max_length=32, default='stub')
    provider_message_id = models.CharField(max_length=120, blank=True, default='')
    status = models.CharField(
        max_length=20, default='queued',
        choices=(('queued', 'Queued'), ('sent', 'Sent'),
                 ('failed', 'Failed'), ('suppressed', 'Suppressed')),
    )
    suppression_reason = models.CharField(max_length=64, blank=True, default='')
    queued_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-queued_at']
        indexes = [
            models.Index(fields=['seller', 'sequence_key']),
            models.Index(fields=['status', 'queued_at']),
        ]


# ─────────────────────────────────────────────────────────────────
# CH13 — Store types
# ─────────────────────────────────────────────────────────────────

STORE_TYPE_CHOICES = (
    ('standard',        'Standard Seller'),
    ('certified',       'Certified Seller'),
    ('gold',            'Gold Seller'),
    ('official_brand',  'Official Brand Store'),
    ('factory_direct',  'Factory Direct'),
    ('choice',          'Choice Programme'),
)

# Search-ranking multipliers per CH13.1.
STORE_TYPE_MULTIPLIERS = {
    'standard':       1.00,
    'certified':      1.10,
    'gold':           1.20,
    'official_brand': 1.40,
    'factory_direct': 1.25,
    'choice':         1.50,
}


class SellerStoreType(models.Model):
    """The "store type" a seller's store presents to buyers. Driven
    by tier + certifications + brand verification. One row per seller
    — recomputed by the daily snapshot worker, with manual overrides
    available for the Official Brand Store application path."""

    seller = models.OneToOneField(User, on_delete=models.CASCADE, related_name='store_type')
    store_type = models.CharField(max_length=20, choices=STORE_TYPE_CHOICES, default='standard')
    search_multiplier = models.FloatField(default=1.0)
    badge_label = models.CharField(max_length=80, blank=True, default='')
    is_pinned = models.BooleanField(
        default=False,
        help_text='If true, daily recalc will NOT downgrade the type '
                  '(e.g. negotiated Official Brand Store).',
    )
    updated_at = models.DateTimeField(auto_now=True)


class OfficialBrandStoreApplication(models.Model):
    """CH13.2. Separate row because it's a heavyweight review with
    brand-team sign-off, dispute-rate gate, and commission negotiation.
    A seller can have at most one pending or approved application per
    brand at a time."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='official_brand_store_applications',
    )
    brand = models.ForeignKey(SellerBrand, on_delete=models.CASCADE)
    banner_key = models.CharField(max_length=255, blank=True, default='')
    logo_key = models.CharField(max_length=255, blank=True, default='')
    featured_product_ids = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20, default='pending',
        choices=(('pending', 'Pending'), ('approved', 'Approved'),
                 ('rejected', 'Rejected'), ('more_info', 'More info')),
    )
    reviewer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_official_brand_apps',
    )
    decision_notes = models.TextField(blank=True, default='')
    metrics_snapshot = models.JSONField(default=dict, blank=True)
    negotiated_commission_rate = models.DecimalField(
        max_digits=5, decimal_places=4, null=True, blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)


# ─────────────────────────────────────────────────────────────────
# CH17 — Annual fee renewal + GMV rebate
# ─────────────────────────────────────────────────────────────────

class FeeRebate(models.Model):
    """Year-end GMV rebate per CH17. We compute at fee-period close,
    persist the source GMV + rebate %, and credit to the seller's
    Alipay balance (or, for MICHA-Angola, the AOA balance)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='fee_rebates')
    fee_period_start = models.DateField()
    fee_period_end = models.DateField()
    gmv_usd = models.DecimalField(max_digits=14, decimal_places=2)
    rebate_pct = models.PositiveSmallIntegerField()
    rebate_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(
        max_length=20, default='computed',
        choices=(('computed', 'Computed'), ('credited', 'Credited'),
                 ('refused', 'Refused')),
    )
    credited_at = models.DateTimeField(null=True, blank=True)
    payment_reference = models.CharField(max_length=120, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('seller', 'fee_period_start')]


# ─────────────────────────────────────────────────────────────────
# CH19 — Open Platform API
# ─────────────────────────────────────────────────────────────────

class SellerApiKey(models.Model):
    """API Key direct-integration mode. We store a SHA-256 of the
    secret — the cleartext is shown to the seller once at creation
    and never persisted. Auth middleware hashes incoming
    `X-MICHA-API-Key` and looks up by `key_hash`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='seller_api_keys')
    label = models.CharField(max_length=80)
    key_prefix = models.CharField(max_length=12, db_index=True)   # shown in UI for ident
    key_hash = models.CharField(max_length=64, unique=True)       # sha256 of secret
    last_used_at = models.DateTimeField(null=True, blank=True)
    request_count = models.PositiveBigIntegerField(default=0)
    rate_limit_per_hour = models.PositiveIntegerField(default=1000)
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @staticmethod
    def generate_secret():
        # 32-byte url-safe token, prefixed with "mka_" so it can be
        # detected in git scans / secret-scanners.
        return 'mka_' + secrets.token_urlsafe(32)

    @staticmethod
    def hash_secret(raw):
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()


class SellerApiApp(models.Model):
    """OAuth third-party app registration (CH19 Mode B). Sellers
    grant access via OAuth; access tokens live in `SellerApiToken`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120)
    client_id = models.CharField(max_length=64, unique=True)
    client_secret_hash = models.CharField(max_length=64)
    redirect_uris = models.JSONField(default=list)
    scopes_allowed = models.JSONField(default=list)
    owner_email = models.EmailField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


class SellerApiAuthorisation(models.Model):
    """The grant — when a seller authorises an app, we mint
    access/refresh tokens here. Access token TTL = 24h, refresh = 90d
    per CH19."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='api_authorisations',
    )
    app = models.ForeignKey(SellerApiApp, on_delete=models.CASCADE)
    access_token_hash = models.CharField(max_length=64, db_index=True)
    refresh_token_hash = models.CharField(max_length=64, db_index=True)
    scopes_granted = models.JSONField(default=list)
    access_expires_at = models.DateTimeField()
    refresh_expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class SellerWebhookEndpoint(models.Model):
    """CH19 webhook subscription. Payloads are HMAC-SHA256 signed
    with `secret`. We store the hash of the secret so we can compute
    sigs without leaking the plain value — and so an admin can issue
    a rotation without seeing the current secret."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='webhook_endpoints',
    )
    url = models.URLField()
    events = models.JSONField(default=list)   # ["order.created", "dispute.opened", ...]
    secret_hash = models.CharField(max_length=64)
    is_active = models.BooleanField(default=True)
    consecutive_failures = models.PositiveSmallIntegerField(default=0)
    disabled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class SellerWebhookDelivery(models.Model):
    """Append-only log of webhook dispatches. Lets the seller debug
    why their endpoint missed an event and lets ops disable noisy
    endpoints after N consecutive failures."""

    id = models.BigAutoField(primary_key=True)
    endpoint = models.ForeignKey(
        SellerWebhookEndpoint, on_delete=models.CASCADE, related_name='deliveries',
    )
    event_type = models.CharField(max_length=80, db_index=True)
    payload = models.JSONField(default=dict)
    signature = models.CharField(max_length=128, blank=True, default='')
    response_status = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body_snippet = models.CharField(max_length=500, blank=True, default='')
    attempt = models.PositiveSmallIntegerField(default=1)
    delivered_at = models.DateTimeField(null=True, blank=True)
    failed_reason = models.CharField(max_length=200, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH21 — Voluntary deregistration
# ─────────────────────────────────────────────────────────────────

DEREG_STATUS_CHOICES = (
    ('requested',     'Requested'),
    ('cooling_off',   'Cooling-off period'),
    ('cancelled',     'Cancelled by seller'),
    ('completed',     'Completed'),
    ('blocked',       'Blocked by eligibility gate'),
)


class SellerDeregistrationRequest(models.Model):
    """CH21. Tracks the 30-day cooling-off window and the
    eligibility-gate result. If any gate fails (open orders, open
    disputes, non-zero balance, etc.) we land in `blocked` with the
    failure code so the seller knows what to clear first."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='deregistration_requests',
    )
    status = models.CharField(max_length=20, choices=DEREG_STATUS_CHOICES, default='requested')
    eligibility_gate = models.JSONField(default=dict, blank=True)
    blocked_reason = models.CharField(max_length=80, blank=True, default='')
    requested_at = models.DateTimeField(auto_now_add=True)
    effective_at = models.DateTimeField()      # = requested_at + 30 days
    cancelled_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    data_export_key = models.CharField(max_length=255, blank=True, default='')


# ─────────────────────────────────────────────────────────────────
# CH22 — Choice programme
# ─────────────────────────────────────────────────────────────────

CHOICE_STATUS_CHOICES = (
    ('pending',     'Pending review'),
    ('approved',    'Approved — awaiting inbound'),
    ('active',      'Active — inventory received'),
    ('rejected',    'Rejected'),
    ('paused',      'Paused by seller or QC'),
)


class ChoiceWarehouse(models.Model):
    """Cainiao-equivalent fulfilment warehouse. For MICHA-Angola the
    seed row is "Luanda Central" — the model is multi-region-ready
    so a future expansion just inserts more rows."""

    code = models.CharField(max_length=20, primary_key=True)
    name = models.CharField(max_length=120)
    country = models.CharField(max_length=2)
    address = models.TextField()
    capacity_units = models.PositiveIntegerField(default=10000)
    is_active = models.BooleanField(default=True)


class ChoiceEnrolment(models.Model):
    """One row per (seller, warehouse). `product_ids` is the subset
    of the seller's catalogue enrolled in Choice — not every product
    qualifies. QC sample units are tracked in `sample_quantity`."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='choice_enrolments',
    )
    warehouse = models.ForeignKey(ChoiceWarehouse, on_delete=models.PROTECT)
    product_ids = models.JSONField(default=list)
    estimated_monthly_units = models.PositiveIntegerField(default=0)
    sample_quantity = models.PositiveSmallIntegerField(default=0)
    supplier_lead_time_days = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=20, choices=CHOICE_STATUS_CHOICES, default='pending')
    metrics_snapshot = models.JSONField(default=dict, blank=True)
    decision_notes = models.TextField(blank=True, default='')
    inbound_deadline = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH24 — Acquisition funnel snapshot
# ─────────────────────────────────────────────────────────────────

class AcquisitionFunnelSnapshot(models.Model):
    """Daily roll-up of the funnel metrics from CH24.1. Recomputed by
    a Celery task so dashboard reads are O(1) instead of running
    multi-table aggregates on every request."""

    snapshot_date = models.DateField(primary_key=True)
    landing_visits = models.PositiveIntegerField(default=0)
    leads_submitted = models.PositiveIntegerField(default=0)
    leads_qualified = models.PositiveIntegerField(default=0)
    applications_started = models.PositiveIntegerField(default=0)
    applications_submitted = models.PositiveIntegerField(default=0)
    kyc_approved = models.PositiveIntegerField(default=0)
    activated = models.PositiveIntegerField(default=0)
    first_listing_within_7d = models.PositiveIntegerField(default=0)
    first_sale_within_30d = models.PositiveIntegerField(default=0)
    retained_at_90d = models.PositiveIntegerField(default=0)
    by_country = models.JSONField(default=dict, blank=True)
    by_lead_source = models.JSONField(default=dict, blank=True)
    by_tier = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
