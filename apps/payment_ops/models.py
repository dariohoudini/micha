"""
Payment Operations — data model
===============================

Implements AliExpress_Payment_Operations_Additional.docx CH1-CH24
where existing apps don't already own the schema. We intentionally
DO NOT duplicate:

  - apps.payments.SellerWallet / WalletTransaction / PayoutRequest /
    Chargeback / PaymentReconciliationLog
  - apps.ledger.Account / Journal / LedgerEntry
  - apps.tax.TaxJurisdiction / TaxRate / TaxCalculation
  - apps.gift_cards.GiftCard / GiftCardTransaction
  - apps.fx.FXRate / ConversionEvent
  - apps.payment_gateways.PaymentIntent / GatewayTransaction

What's new here (gap-filling):

  CH2   ChargebackEvidence, ChargebackOutcome  — evidence package + win/loss
  CH3   ReconciliationException                — auto-reconciler exception queue
  CH4   FxHedgePosition                        — open hedge book
  CH5   MultiCurrencyDisplay                   — per-(product, currency) snapshots
  CH7   TaxInvoice                             — PDF metadata for buyer + seller
  CH9   AmlAlert, SarFiling                    — suspicious activity workflow
  CH10  SellerAnnualTaxExport                  — 1099-K/equivalent generator
  CH11  PaymentMethodEligibilityRule           — country×currency×amount matrix
  CH12  BnplProvider, BnplInstalmentPlan       — Klarna/Affirm/Huabei
  CH13  StoreCredit, StoreCreditTransaction    — buyer-side virtual credit
  CH15  B2BAccount, B2BInvoice                 — Net30/60 terms
  CH16  SplitPaymentAllocation                 — multiple methods on one order
  CH18  BuyerWallet, WalletTopUp               — buyer-side wallet
  CH19  PaymentFailureLog, PaymentRecoveryAttempt
  CH20  CurrencyConversionDispute              — buyer FX complaint
  CH21  FinancialReportSnapshot                — daily P&L / GMV / commission
  CH22  SanctionsScreen                        — OFAC/EU/UN watchlist hit log
  CH23  TokenisedPaymentMethod                 — PAN-free token register
  CH24  PaymentOpsKpiSnapshot
  Audit PaymentOpsEvent
"""
from __future__ import annotations

import hashlib
import secrets
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


# ─────────────────────────────────────────────────────────────────
# CH2 — Chargeback evidence package + outcome
# ─────────────────────────────────────────────────────────────────

EVIDENCE_KIND_CHOICES = (
    ('proof_of_delivery',  'Proof of delivery'),
    ('signed_receipt',     'Signed receipt'),
    ('buyer_communication','Buyer communication thread'),
    ('product_photos',     'Product photos'),
    ('shipping_label',     'Shipping label'),
    ('customs_doc',        'Customs documentation'),
    ('refund_policy',      'Refund / return policy'),
    ('seller_tos',         'Seller terms of service'),
    ('previous_purchases', 'Buyer purchase history'),
    ('ip_geolocation',     'IP geolocation'),
    ('device_fingerprint', 'Device fingerprint'),
    ('other',              'Other'),
)


class ChargebackEvidence(models.Model):
    """One evidence artefact per row. The package assembled by the
    ops team comprises N rows — uploaded individually for audit."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Reference the legacy apps.payments.Chargeback by string id so
    # we don't hard-FK across apps.
    chargeback_id = models.CharField(max_length=64, db_index=True)
    order_id = models.CharField(max_length=64, db_index=True)
    kind = models.CharField(max_length=24, choices=EVIDENCE_KIND_CHOICES)
    file_key = models.CharField(
        max_length=255, blank=True, default='',
        help_text='S3 / local key of the artefact.',
    )
    notes = models.TextField(blank=True, default='')
    submitted_at = models.DateTimeField(null=True, blank=True)
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='uploaded_chargeback_evidence',
    )
    created_at = models.DateTimeField(auto_now_add=True)


CHARGEBACK_OUTCOME_CHOICES = (
    ('pending',      'Pending'),
    ('won',          'Won — merchant'),
    ('lost',         'Lost — buyer'),
    ('partial_win',  'Partial — partial recovery'),
    ('withdrawn',    'Withdrawn by issuer'),
)


class ChargebackOutcome(models.Model):
    """Final outcome from the issuer. One per chargeback. Captures
    the financial recovery and feeds the seller-payable adjustment."""

    chargeback_id = models.CharField(max_length=64, primary_key=True)
    outcome = models.CharField(
        max_length=12, choices=CHARGEBACK_OUTCOME_CHOICES, default='pending',
    )
    recovery_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    seller_liability_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    platform_liability_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    fee_charged = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='AOA')
    issuer_reference = models.CharField(max_length=120, blank=True, default='')
    decided_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default='')


# ─────────────────────────────────────────────────────────────────
# CH3 — Reconciliation exceptions
# ─────────────────────────────────────────────────────────────────

RECON_EXCEPTION_KIND_CHOICES = (
    ('missing_in_bank',  'Present in MICHA, missing in bank file'),
    ('missing_in_micha', 'Present in bank file, missing in MICHA'),
    ('amount_mismatch',  'Amount mismatch'),
    ('currency_mismatch','Currency mismatch'),
    ('date_mismatch',    'Settlement date mismatch'),
    ('duplicate',        'Duplicate transaction'),
    ('unknown_reference','Unknown reference'),
)


class ReconciliationException(models.Model):
    """Per-row exception emitted by the daily reconciliation job.
    Ops works the queue via the admin."""

    id = models.BigAutoField(primary_key=True)
    settlement_date = models.DateField(db_index=True)
    psp_reference = models.CharField(max_length=120, blank=True, default='', db_index=True)
    order_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    kind = models.CharField(max_length=24, choices=RECON_EXCEPTION_KIND_CHOICES)
    expected_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    actual_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='')
    raw_row = models.JSONField(default=dict, blank=True)
    resolved = models.BooleanField(default=False)
    resolution = models.CharField(max_length=120, blank=True, default='')
    resolved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='resolved_recon_exceptions',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    detected_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-detected_at']
        indexes = [models.Index(fields=['resolved', 'kind'])]


# ─────────────────────────────────────────────────────────────────
# CH4 — FX hedging
# ─────────────────────────────────────────────────────────────────

HEDGE_STATUS_CHOICES = (
    ('open',     'Open'),
    ('settled',  'Settled'),
    ('cancelled','Cancelled'),
    ('rolled',   'Rolled forward'),
)


class FxHedgePosition(models.Model):
    """Open / closed hedge positions. Treasury team books rows; the
    P&L computation looks at delta between booked rate and spot at
    settle date."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pair = models.CharField(max_length=8, db_index=True)  # "USD/AOA"
    side = models.CharField(
        max_length=8, choices=(('buy', 'Buy'), ('sell', 'Sell')),
    )
    notional = models.DecimalField(max_digits=14, decimal_places=2)
    notional_currency = models.CharField(max_length=3)
    booked_rate = models.DecimalField(max_digits=18, decimal_places=8)
    settle_rate = models.DecimalField(
        max_digits=18, decimal_places=8, null=True, blank=True,
    )
    counterparty = models.CharField(max_length=80, blank=True, default='')
    booked_at = models.DateTimeField(auto_now_add=True)
    settle_at = models.DateTimeField()
    settled_at = models.DateTimeField(null=True, blank=True)
    pnl = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=HEDGE_STATUS_CHOICES, default='open')


# ─────────────────────────────────────────────────────────────────
# CH5 — Multi-currency display
# ─────────────────────────────────────────────────────────────────

class MultiCurrencyDisplay(models.Model):
    """Snapshot of a converted display price for a product in a buyer
    currency at a moment in time. Keyed on
    (product_id, buyer_currency, rounded_to_minute) so the same
    minute returns the same display rate."""

    id = models.BigAutoField(primary_key=True)
    product_id = models.CharField(max_length=64, db_index=True)
    base_currency = models.CharField(max_length=3)
    base_amount = models.DecimalField(max_digits=12, decimal_places=2)
    buyer_currency = models.CharField(max_length=3, db_index=True)
    display_amount = models.DecimalField(max_digits=12, decimal_places=2)
    fx_rate = models.DecimalField(max_digits=18, decimal_places=8)
    fx_markup_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    computed_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ─────────────────────────────────────────────────────────────────
# CH7 — Tax invoices
# ─────────────────────────────────────────────────────────────────

TAX_INVOICE_KIND_CHOICES = (
    ('buyer_b2c',    'Buyer B2C tax invoice'),
    ('buyer_b2b',    'Buyer B2B tax invoice'),
    ('seller_comm',  'Seller commission invoice'),
    ('credit_note',  'Credit note (refund)'),
)


class TaxInvoice(models.Model):
    """Metadata + storage key for a generated invoice PDF. The PDF
    body itself is stored at `file_key` and is immutable — re-issues
    create a credit note + new invoice."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice_number = models.CharField(max_length=40, unique=True, db_index=True)
    kind = models.CharField(max_length=14, choices=TAX_INVOICE_KIND_CHOICES)
    order_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    buyer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tax_invoices_received',
    )
    seller = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tax_invoices_issued',
    )
    country = models.CharField(max_length=2)
    currency = models.CharField(max_length=3)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    tax_breakdown = models.JSONField(default=list, blank=True)
    file_key = models.CharField(max_length=255, blank=True, default='')
    voided = models.BooleanField(default=False)
    voided_reason = models.CharField(max_length=120, blank=True, default='')
    issued_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH9 — AML / SAR
# ─────────────────────────────────────────────────────────────────

AML_ALERT_KIND_CHOICES = (
    ('structuring',         'Structuring — multiple sub-threshold'),
    ('high_value_single',   'High-value single transaction'),
    ('velocity_anomaly',    'Velocity anomaly'),
    ('geo_high_risk',       'High-risk geography'),
    ('sanctioned_party',    'Sanctioned-party hit'),
    ('rapid_pass_through',  'Rapid pass-through (mule)'),
    ('cash_intensive',      'Cash-intensive seller'),
    ('chargeback_pattern',  'Repeated chargebacks'),
)


class AmlAlert(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    subject_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='payment_ops_aml_alerts',
    )
    kind = models.CharField(max_length=24, choices=AML_ALERT_KIND_CHOICES, db_index=True)
    severity = models.PositiveSmallIntegerField(default=50)
    detection_window_days = models.PositiveSmallIntegerField(default=7)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='AOA')
    transaction_ids = models.JSONField(default=list, blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16, default='open',
        choices=(('open', 'Open'), ('in_review', 'In review'),
                 ('escalated', 'Escalated to SAR'),
                 ('dismissed', 'Dismissed'), ('closed', 'Closed')),
    )
    assigned_to = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_aml_alerts',
    )
    closed_notes = models.TextField(blank=True, default='')
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)


SAR_STATUS_CHOICES = (
    ('drafting',  'Drafting'),
    ('approved',  'Approved internally'),
    ('filed',     'Filed with FIU'),
    ('rejected',  'Rejected by FIU'),
    ('amended',   'Amended'),
)


class SarFiling(models.Model):
    """Suspicious Activity Report. One per AmlAlert that escalates.
    `fiu_reference` is the regulator's acknowledgement id."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    alert = models.OneToOneField(AmlAlert, on_delete=models.CASCADE, related_name='sar_filing')
    sar_reference = models.CharField(max_length=40, unique=True)
    fiu_reference = models.CharField(max_length=120, blank=True, default='')
    narrative = models.TextField()
    filer = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sar_filings',
    )
    status = models.CharField(max_length=12, choices=SAR_STATUS_CHOICES, default='drafting')
    filed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH10 — Annual seller tax export
# ─────────────────────────────────────────────────────────────────

class SellerAnnualTaxExport(models.Model):
    """Yearly summary export (1099-K equivalent). One row per
    (seller, tax_year)."""

    id = models.BigAutoField(primary_key=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='annual_tax_exports')
    tax_year = models.PositiveSmallIntegerField()
    gross_sales = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    refunds_issued = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    commissions_paid = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    chargebacks_lost = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    net_payouts = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='USD')
    report_file_key = models.CharField(max_length=255, blank=True, default='')
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('seller', 'tax_year')]


# ─────────────────────────────────────────────────────────────────
# CH11 — Payment method eligibility
# ─────────────────────────────────────────────────────────────────

class PaymentMethodEligibilityRule(models.Model):
    """Allow / deny rule. The eligibility resolver walks rules in
    `priority` order; first match wins."""

    id = models.BigAutoField(primary_key=True)
    method_code = models.CharField(max_length=40, db_index=True)
    country = models.CharField(max_length=2, blank=True, default='', db_index=True)
    currency = models.CharField(max_length=3, blank=True, default='')
    min_order_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    max_order_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    buyer_segment = models.CharField(max_length=40, blank=True, default='')
    allow = models.BooleanField(default=True)
    priority = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True)
    reason = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH12 — BNPL
# ─────────────────────────────────────────────────────────────────

class BnplProvider(models.Model):
    code = models.CharField(max_length=24, primary_key=True)
    name = models.CharField(max_length=80)
    countries = models.JSONField(default=list, blank=True)
    max_order_value = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    merchant_fee_pct = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('3.0'))
    is_active = models.BooleanField(default=True)


BNPL_PLAN_STATUS_CHOICES = (
    ('approved',    'Approved'),
    ('active',      'Active'),
    ('completed',   'Completed'),
    ('defaulted',   'Defaulted'),
    ('cancelled',   'Cancelled'),
)


class BnplInstalmentPlan(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    provider = models.ForeignKey(BnplProvider, on_delete=models.PROTECT, related_name='plans')
    order_id = models.CharField(max_length=64, db_index=True)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='bnpl_plans')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    instalments = models.PositiveSmallIntegerField()
    instalment_amount = models.DecimalField(max_digits=10, decimal_places=2)
    next_due_at = models.DateTimeField()
    instalments_paid = models.PositiveSmallIntegerField(default=0)
    instalments_late = models.PositiveSmallIntegerField(default=0)
    provider_plan_id = models.CharField(max_length=120, blank=True, default='')
    status = models.CharField(max_length=12, choices=BNPL_PLAN_STATUS_CHOICES, default='approved')
    created_at = models.DateTimeField(auto_now_add=True)


class BnplInstalment(models.Model):
    """Per-instalment payment record."""

    id = models.BigAutoField(primary_key=True)
    plan = models.ForeignKey(BnplInstalmentPlan, on_delete=models.CASCADE, related_name='payments')
    sequence_number = models.PositiveSmallIntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    due_at = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    days_late = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(
        max_length=12, default='due',
        choices=(('due', 'Due'), ('paid', 'Paid'),
                 ('late', 'Late'), ('defaulted', 'Defaulted')),
    )

    class Meta:
        unique_together = [('plan', 'sequence_number')]


# ─────────────────────────────────────────────────────────────────
# CH13 — Store credit (buyer-side)
# ─────────────────────────────────────────────────────────────────

STORE_CREDIT_REASON_CHOICES = (
    ('apology',           'Apology / goodwill'),
    ('partial_refund',    'Partial refund'),
    ('promotion',         'Promotion'),
    ('referral',          'Referral reward'),
    ('cancellation',      'Order cancellation credit'),
    ('shipping_credit',   'Shipping credit'),
    ('manual_admin',      'Manual admin grant'),
)


class StoreCredit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='store_credits')
    initial_amount = models.DecimalField(max_digits=12, decimal_places=2)
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='AOA')
    reason = models.CharField(max_length=20, choices=STORE_CREDIT_REASON_CHOICES)
    related_order_id = models.CharField(max_length=64, blank=True, default='')
    granted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='granted_store_credits',
    )
    expires_at = models.DateTimeField()
    status = models.CharField(
        max_length=12, default='active',
        choices=(('active', 'Active'), ('depleted', 'Depleted'),
                 ('expired', 'Expired'), ('revoked', 'Revoked')),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'status'])]


class StoreCreditTransaction(models.Model):
    id = models.BigAutoField(primary_key=True)
    credit = models.ForeignKey(StoreCredit, on_delete=models.CASCADE, related_name='transactions')
    kind = models.CharField(
        max_length=12,
        choices=(('debit', 'Debit (spend)'),
                 ('refund', 'Refund returned'),
                 ('expire', 'Expired'),
                 ('revoke', 'Revoked')),
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    related_order_id = models.CharField(max_length=64, blank=True, default='')
    occurred_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH15 — B2B accounts + Net30
# ─────────────────────────────────────────────────────────────────

B2B_STATUS_CHOICES = (
    ('pending',   'Pending — under review'),
    ('approved',  'Approved'),
    ('rejected',  'Rejected'),
    ('suspended', 'Suspended — overdue'),
    ('closed',    'Closed'),
)


class B2BAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organisation = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='b2b_account',
    )
    legal_name = models.CharField(max_length=200)
    tax_id = models.CharField(max_length=80, blank=True, default='')
    country = models.CharField(max_length=2)
    credit_limit = models.DecimalField(max_digits=14, decimal_places=2)
    available_credit = models.DecimalField(max_digits=14, decimal_places=2)
    payment_terms_days = models.PositiveSmallIntegerField(default=30)
    credit_score = models.PositiveSmallIntegerField(default=0)
    currency = models.CharField(max_length=3, default='USD')
    status = models.CharField(max_length=12, choices=B2B_STATUS_CHOICES, default='pending')
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_b2b_accounts',
    )
    created_at = models.DateTimeField(auto_now_add=True)


B2B_INVOICE_STATUS_CHOICES = (
    ('issued',    'Issued — awaiting payment'),
    ('paid',      'Paid'),
    ('overdue',   'Overdue'),
    ('written_off','Written off'),
    ('disputed',  'Disputed'),
)


class B2BInvoice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(B2BAccount, on_delete=models.CASCADE, related_name='invoices')
    order_id = models.CharField(max_length=64, db_index=True)
    invoice_number = models.CharField(max_length=40, unique=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    due_at = models.DateTimeField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=3, default='USD')
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=12, choices=B2B_INVOICE_STATUS_CHOICES, default='issued')
    paid_at = models.DateTimeField(null=True, blank=True)
    days_overdue = models.PositiveSmallIntegerField(default=0)


# ─────────────────────────────────────────────────────────────────
# CH16 — Split payment
# ─────────────────────────────────────────────────────────────────

class SplitPaymentAllocation(models.Model):
    """One row per (order, payment_method) split. The sum of
    allocations for an order equals the order total. We pessimistically
    lock the order_id row to prevent double-charge."""

    id = models.BigAutoField(primary_key=True)
    order_id = models.CharField(max_length=64, db_index=True)
    method_code = models.CharField(max_length=40)
    intent_id = models.CharField(max_length=80, blank=True, default='')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    sequence_number = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=12, default='pending',
        choices=(('pending', 'Pending'), ('authorised', 'Authorised'),
                 ('captured', 'Captured'), ('failed', 'Failed'),
                 ('voided', 'Voided'), ('refunded', 'Refunded')),
    )
    failure_code = models.CharField(max_length=40, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('order_id', 'sequence_number')]


# ─────────────────────────────────────────────────────────────────
# CH18 — Buyer wallet
# ─────────────────────────────────────────────────────────────────

class BuyerWallet(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='buyer_wallet')
    available_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pending_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='AOA')
    daily_spend_limit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('500000'))
    monthly_spend_limit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('5000000'))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


WALLET_TX_KIND_CHOICES = (
    ('top_up',   'Top-up'),
    ('spend',    'Spend'),
    ('refund',   'Refund'),
    ('payout',   'Payout to bank'),
    ('adjustment','Adjustment'),
)


class BuyerWalletTransaction(models.Model):
    id = models.BigAutoField(primary_key=True)
    wallet = models.ForeignKey(BuyerWallet, on_delete=models.CASCADE, related_name='transactions')
    kind = models.CharField(max_length=12, choices=WALLET_TX_KIND_CHOICES, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    reference = models.CharField(max_length=120, blank=True, default='')
    related_order_id = models.CharField(max_length=64, blank=True, default='')
    intent_id = models.CharField(max_length=80, blank=True, default='')
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)


class WalletTopUp(models.Model):
    """Pending / completed wallet top-up via gateway."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wallet = models.ForeignKey(BuyerWallet, on_delete=models.CASCADE, related_name='top_ups')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    gateway = models.CharField(max_length=24)
    intent_id = models.CharField(max_length=80, blank=True, default='')
    status = models.CharField(
        max_length=12, default='pending',
        choices=(('pending', 'Pending'), ('succeeded', 'Succeeded'),
                 ('failed', 'Failed'), ('refunded', 'Refunded')),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)


# ─────────────────────────────────────────────────────────────────
# CH19 — Payment failure + recovery
# ─────────────────────────────────────────────────────────────────

FAILURE_CATEGORY_CHOICES = (
    ('insufficient_funds', 'Insufficient funds'),
    ('card_declined',      'Card declined by issuer'),
    ('do_not_honour',      'Do not honour'),
    ('expired_card',       'Expired card'),
    ('fraud_suspected',    'Fraud suspected'),
    ('3ds_failed',         '3DS authentication failed'),
    ('network_error',      'Network / gateway error'),
    ('limit_exceeded',     'Daily / monthly limit exceeded'),
    ('country_blocked',    'Country not supported'),
    ('other',              'Other'),
)

RECOVERY_STRATEGY_CHOICES = (
    ('retry_same_method',  'Retry same method'),
    ('retry_other_method', 'Suggest alternative method'),
    ('split_payment',      'Suggest split payment'),
    ('email_nudge',        'Email nudge'),
    ('soft_decline_retry', 'Soft decline — auto retry'),
    ('manual_intervention','Manual intervention'),
)


class PaymentFailureLog(models.Model):
    """One row per failed attempt. Drives the recovery worker which
    schedules retries / nudges per category."""

    id = models.BigAutoField(primary_key=True)
    order_id = models.CharField(max_length=64, db_index=True)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='payment_failures')
    intent_id = models.CharField(max_length=80, blank=True, default='')
    gateway = models.CharField(max_length=24, blank=True, default='')
    method_code = models.CharField(max_length=40, blank=True, default='')
    category = models.CharField(max_length=24, choices=FAILURE_CATEGORY_CHOICES, db_index=True)
    failure_code = models.CharField(max_length=40, blank=True, default='')
    failure_message = models.CharField(max_length=255, blank=True, default='')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)


class PaymentRecoveryAttempt(models.Model):
    id = models.BigAutoField(primary_key=True)
    failure = models.ForeignKey(PaymentFailureLog, on_delete=models.CASCADE, related_name='recovery_attempts')
    strategy = models.CharField(max_length=24, choices=RECOVERY_STRATEGY_CHOICES)
    attempt_number = models.PositiveSmallIntegerField(default=1)
    scheduled_at = models.DateTimeField()
    executed_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(
        max_length=12, default='pending',
        choices=(('pending', 'Pending'), ('succeeded', 'Succeeded'),
                 ('failed', 'Failed'), ('skipped', 'Skipped')),
    )
    new_intent_id = models.CharField(max_length=80, blank=True, default='')
    notes = models.TextField(blank=True, default='')


# ─────────────────────────────────────────────────────────────────
# CH20 — Currency conversion dispute
# ─────────────────────────────────────────────────────────────────

class CurrencyConversionDispute(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_id = models.CharField(max_length=64, db_index=True)
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='fx_disputes')
    displayed_amount = models.DecimalField(max_digits=12, decimal_places=2)
    displayed_currency = models.CharField(max_length=3)
    charged_amount = models.DecimalField(max_digits=12, decimal_places=2)
    charged_currency = models.CharField(max_length=3)
    booked_fx_rate = models.DecimalField(max_digits=18, decimal_places=8)
    expected_fx_rate = models.DecimalField(max_digits=18, decimal_places=8)
    difference = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=16, default='filed',
        choices=(('filed', 'Filed'), ('investigating', 'Investigating'),
                 ('refunded', 'Difference refunded'),
                 ('rejected', 'Rejected'),
                 ('explained', 'Explained — no refund')),
    )
    resolution_notes = models.TextField(blank=True, default='')
    filed_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)


# ─────────────────────────────────────────────────────────────────
# CH21 — Financial report snapshot
# ─────────────────────────────────────────────────────────────────

class FinancialReportSnapshot(models.Model):
    """Daily P&L roll-up. Production runs the SQL queries from CH21.1
    and persists the result so dashboards read O(1)."""

    snapshot_date = models.DateField(primary_key=True)
    gmv = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    net_revenue = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    commission_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    payment_processing_costs = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    refund_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    refund_rate = models.FloatField(default=0)
    chargeback_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    chargeback_rate = models.FloatField(default=0)
    cogs_estimate = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    gross_profit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='USD')
    by_country = models.JSONField(default=dict, blank=True)
    by_payment_method = models.JSONField(default=dict, blank=True)
    by_category = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH22 — Sanctions screening
# ─────────────────────────────────────────────────────────────────

class SanctionsScreen(models.Model):
    """Sanctions hit log. Every checkout / payout runs a screen; we
    record only positive matches + manual reviews."""

    id = models.BigAutoField(primary_key=True)
    subject_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sanctions_screens',
    )
    context = models.CharField(
        max_length=24,
        choices=(('checkout', 'Checkout'), ('payout', 'Payout'),
                 ('signup', 'Signup'), ('manual', 'Manual')),
    )
    name_hash = models.CharField(max_length=64, db_index=True)
    country = models.CharField(max_length=2, blank=True, default='')
    list_source = models.CharField(
        max_length=20,
        choices=(('ofac', 'OFAC'), ('eu', 'EU'), ('un', 'UN'),
                 ('uk_hmt', 'UK HMT'), ('internal', 'Internal')),
    )
    match_confidence = models.FloatField(default=0.0)
    match_details = models.JSONField(default=dict, blank=True)
    action_taken = models.CharField(
        max_length=20, default='blocked',
        choices=(('blocked', 'Blocked'),
                 ('escalated', 'Escalated for review'),
                 ('cleared', 'Cleared — false positive')),
    )
    cleared_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cleared_sanctions',
    )
    cleared_at = models.DateTimeField(null=True, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ─────────────────────────────────────────────────────────────────
# CH23 — Tokenisation
# ─────────────────────────────────────────────────────────────────

class TokenisedPaymentMethod(models.Model):
    """PCI-safe token register. We NEVER store PAN; the gateway
    holds the vault, we just hold the opaque token + last-4 + brand
    for UI."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tokenised_methods')
    gateway = models.CharField(max_length=24)
    method_type = models.CharField(
        max_length=20,
        choices=(('card', 'Card'), ('bank_account', 'Bank account'),
                 ('digital_wallet', 'Digital wallet'),
                 ('multicaixa', 'Multicaixa Express')),
    )
    brand = models.CharField(max_length=20, blank=True, default='')
    last_four = models.CharField(max_length=4, blank=True, default='')
    expiry_month = models.PositiveSmallIntegerField(null=True, blank=True)
    expiry_year = models.PositiveSmallIntegerField(null=True, blank=True)
    gateway_token = models.CharField(max_length=120)
    fingerprint = models.CharField(
        max_length=64, blank=True, default='', db_index=True,
        help_text='SHA-256 of gateway_token so we can detect re-tokenisation.',
    )
    is_default = models.BooleanField(default=False)
    requires_cvv = models.BooleanField(default=False)
    three_ds_supported = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH24 — KPI snapshot
# ─────────────────────────────────────────────────────────────────

class PaymentOpsKpiSnapshot(models.Model):
    snapshot_date = models.DateField(primary_key=True)
    transaction_count = models.PositiveIntegerField(default=0)
    transaction_value = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    auth_rate_pct = models.FloatField(default=0)
    failure_rate_pct = models.FloatField(default=0)
    avg_settle_seconds = models.FloatField(default=0)
    chargeback_rate_pct = models.FloatField(default=0)
    chargeback_win_rate_pct = models.FloatField(default=0)
    refund_rate_pct = models.FloatField(default=0)
    fx_pnl = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    bnpl_default_rate_pct = models.FloatField(default=0)
    wallet_topups_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    sanctions_blocks = models.PositiveIntegerField(default=0)
    aml_alerts_open = models.PositiveIntegerField(default=0)
    sar_filings = models.PositiveIntegerField(default=0)
    recon_exceptions_open = models.PositiveIntegerField(default=0)
    b2b_overdue_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    by_gateway = models.JSONField(default=dict, blank=True)
    by_method = models.JSONField(default=dict, blank=True)
    by_country = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# Audit
# ─────────────────────────────────────────────────────────────────

class PaymentOpsEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    kind = models.CharField(max_length=64, db_index=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='payment_ops_events',
    )
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='emitted_payment_ops_events',
    )
    order_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    @staticmethod
    def log(*, kind, user=None, actor=None, order_id='', payload=None):
        try:
            return PaymentOpsEvent.objects.create(
                kind=kind, user=user, actor=actor,
                order_id=order_id[:64], payload=payload or {},
            )
        except Exception:
            return None
