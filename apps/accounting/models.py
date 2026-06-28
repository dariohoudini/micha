"""
MICHA Finance & Accounting — IFRS-aligned general ledger.

Source: MICHA_Finance_Accounting.docx (24 chapters). All amounts are
integer AOA cents (BIGINT). The GL is the single source of financial truth.

Chapters that live HERE (genuinely new — the existing apps.ledger is a
narrow store-credit/loyalty sub-ledger, NOT an IFRS GL):
  CH1   GLAccount (chart of accounts), AccountingPeriod (period lock)
  CH2/23 JournalEntry / JournalLine — immutable, balanced, reversible
  CH3   EscrowLedger (per-order sub-ledger)
  CH5   SellerPayableLedger (per-seller/order sub-ledger)
  CH11  DisputeReserveLedger
  CH14  DeferredRevenue
  CH19  CapitalisedDevelopment + AmortisationEntry (IAS 38)
  CH20  AccountReceivable (+ ageing)
  CH9   FxRevaluation
  CH3/4/5/7  SubLedgerReconciliation
  CH21  ManualEntryApproval (segregation of duties)
  CH24  FinancialStatementSnapshot (P&L + balance sheet)

Bridged (reconciliation sources, not duplicated):
  apps.ledger                       store-credit/loyalty sub-ledger
  apps.payments_angola              escrow/wallet/COD/settlement state
  apps.payment_ops                  FinancialReportSnapshot (metrics)
  apps.tax                          IVA rates
"""
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from .chart_of_accounts import (
    ASSET, COST_OF_REVENUE, CREDIT, DEBIT, EQUITY, LIABILITY,
    OPERATING_EXPENSE, OTHER, REVENUE,
)

User = settings.AUTH_USER_MODEL

ACCOUNT_TYPE_CHOICES = [
    (ASSET, 'Asset'), (LIABILITY, 'Liability'), (EQUITY, 'Equity'),
    (REVENUE, 'Revenue'), (COST_OF_REVENUE, 'Cost of revenue'),
    (OPERATING_EXPENSE, 'Operating expense'), (OTHER, 'Other income/expense'),
]


# ──────────────────────────────────────────────────────────────────────
# CH1 — Chart of accounts + period lock
# ──────────────────────────────────────────────────────────────────────

class GLAccount(models.Model):
    code = models.CharField(max_length=10, primary_key=True)
    name = models.CharField(max_length=120)
    account_type = models.CharField(max_length=20, choices=ACCOUNT_TYPE_CHOICES)
    normal_balance = models.CharField(
        max_length=6, choices=[(DEBIT, 'Debit'), (CREDIT, 'Credit')])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code} {self.name}'


class AccountingPeriod(models.Model):
    """Period lock prevents backdating into closed months (doc CH23)."""
    period = models.CharField(max_length=7, primary_key=True)  # 'YYYY-MM'
    is_locked = models.BooleanField(default=False, db_index=True)
    locked_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                  blank=True, related_name='+')
    locked_at = models.DateTimeField(null=True, blank=True)
    unlocked_reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period']


# ──────────────────────────────────────────────────────────────────────
# CH2 / CH23 — Immutable journal
# ──────────────────────────────────────────────────────────────────────

SOURCE_TYPE_CHOICES = [
    ('system_auto', 'System auto'), ('manual', 'Manual'),
    ('reversal', 'Reversal'), ('correction', 'Correction'),
    ('accrual', 'Accrual'), ('payroll', 'Payroll'),
]


class JournalEntry(models.Model):
    """INSERT-ONLY. Corrections are done via a reversal + a new correcting
    entry; the original is preserved forever (doc CH23).
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4,
                          editable=False)
    entry_date = models.DateField(db_index=True)
    period = models.CharField(max_length=7, db_index=True)  # 'YYYY-MM'
    description = models.CharField(max_length=300)
    source_type = models.CharField(max_length=16, choices=SOURCE_TYPE_CHOICES,
                                   default='system_auto', db_index=True)
    source_id = models.CharField(max_length=80, blank=True, db_index=True)
    posted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                  blank=True, related_name='journal_entries')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                    blank=True, related_name='+')
    is_auto = models.BooleanField(default=True)
    is_reversal = models.BooleanField(default=False)
    reversed_entry = models.ForeignKey('self', on_delete=models.SET_NULL,
                                       null=True, blank=True,
                                       related_name='reversals')
    total_cents = models.BigIntegerField(default=0)  # sum of debits (=credits)
    posted_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-posted_at']
        indexes = [
            models.Index(fields=['period', 'entry_date']),
            models.Index(fields=['source_type', 'source_id']),
        ]

    def __str__(self):
        return f'JE {self.id} {self.period} {self.description[:40]}'


class JournalLine(models.Model):
    """One side of a balanced posting. Exactly one of debit/credit > 0."""
    entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT,
                              related_name='lines')
    account = models.ForeignKey(GLAccount, on_delete=models.PROTECT,
                                related_name='lines')
    debit_cents = models.BigIntegerField(default=0)
    credit_cents = models.BigIntegerField(default=0)
    description = models.CharField(max_length=300, blank=True)
    currency = models.CharField(max_length=3, default='AOA')
    # Optional sub-entity for per-user reporting (seller/buyer/courier).
    party = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(debit_cents__gte=0) & Q(credit_cents__gte=0)
                    & ~Q(debit_cents=0, credit_cents=0)
                    & (Q(debit_cents=0) | Q(credit_cents=0))
                ),
                name='accounting_line_exactly_one_direction',
            ),
        ]
        indexes = [
            models.Index(fields=['account', '-created_at']),
        ]


# ──────────────────────────────────────────────────────────────────────
# CH3 — Escrow sub-ledger
# ──────────────────────────────────────────────────────────────────────

class EscrowLedger(models.Model):
    STATUS_CHOICES = [
        ('held', 'Held'), ('releasable', 'Releasable'),
        ('released', 'Released'), ('clawed_back', 'Clawed back'),
        ('partially_clawed', 'Partially clawed'),
    ]
    order_id = models.CharField(max_length=64, unique=True, db_index=True)
    seller = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                               blank=True, related_name='escrow_records')
    gross_amount_cents = models.BigIntegerField()
    commission_cents = models.BigIntegerField(default=0)
    net_seller_cents = models.BigIntegerField(default=0)
    refunded_cents = models.BigIntegerField(default=0)
    status = models.CharField(max_length=18, choices=STATUS_CHOICES,
                              default='held', db_index=True)
    payment_method = models.CharField(max_length=16, blank=True)
    release_trigger = models.CharField(max_length=20, blank=True)
    funds_received_at = models.DateTimeField(null=True, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


# ──────────────────────────────────────────────────────────────────────
# CH5 — Seller payable sub-ledger
# ──────────────────────────────────────────────────────────────────────

class SellerPayableLedger(models.Model):
    STATUS_CHOICES = [
        ('accrued', 'Accrued'), ('adjusting', 'Adjusting'),
        ('paid', 'Paid'), ('disputed', 'Disputed'),
    ]
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='payable_records')
    order_id = models.CharField(max_length=64, db_index=True)
    gross_cents = models.BigIntegerField()
    commission_cents = models.BigIntegerField()
    net_cents = models.BigIntegerField()
    adjustments_cents = models.BigIntegerField(default=0)
    payout_batch_id = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default='accrued', db_index=True)
    accrued_at = models.DateTimeField(auto_now_add=True, db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=['seller', 'status'])]


# ──────────────────────────────────────────────────────────────────────
# CH11 — Dispute reserve
# ──────────────────────────────────────────────────────────────────────

class DisputeReserveLedger(models.Model):
    snapshot_date = models.DateField(unique=True)
    open_dispute_value_cents = models.BigIntegerField(default=0)
    expected_loss_cents = models.BigIntegerField(default=0)
    prior_reserve_cents = models.BigIntegerField(default=0)
    adjustment_cents = models.BigIntegerField(default=0)  # + increase / - release
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)


# ──────────────────────────────────────────────────────────────────────
# CH14 — Deferred revenue
# ──────────────────────────────────────────────────────────────────────

class DeferredRevenue(models.Model):
    KIND_CHOICES = [('annual_fee', 'Annual fee'), ('ad_credits', 'Ad credits')]
    seller = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='deferred_revenue')
    kind = models.CharField(max_length=12, choices=KIND_CHOICES)
    total_cents = models.BigIntegerField()
    recognised_cents = models.BigIntegerField(default=0)
    months_total = models.PositiveSmallIntegerField(default=12)
    months_recognised = models.PositiveSmallIntegerField(default=0)
    revenue_account_code = models.CharField(max_length=10, default='4010')
    is_active = models.BooleanField(default=True)
    started_at = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)


# ──────────────────────────────────────────────────────────────────────
# CH19 — Capitalised development (IAS 38)
# ──────────────────────────────────────────────────────────────────────

class CapitalisedDevelopment(models.Model):
    STATUS_CHOICES = [
        ('capitalising', 'Capitalising'), ('live', 'Live (amortising)'),
        ('impaired', 'Impaired'), ('fully_amortised', 'Fully amortised'),
    ]
    feature_name = models.CharField(max_length=160)
    capitalised_cents = models.BigIntegerField(default=0)
    amortised_cents = models.BigIntegerField(default=0)
    useful_life_months = models.PositiveSmallIntegerField(default=36)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES,
                              default='capitalising')
    went_live_at = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def net_book_value_cents(self):
        return self.capitalised_cents - self.amortised_cents


# ──────────────────────────────────────────────────────────────────────
# CH20 — Accounts receivable + ageing
# ──────────────────────────────────────────────────────────────────────

class AccountReceivable(models.Model):
    KIND_CHOICES = [
        ('seller_chargeback', 'Seller chargeback recovery'),
        ('courier_shortfall', 'Courier cash shortfall'),
        ('partner_fee', 'Partner fee'),
        ('insurance_claim', 'Insurance claim'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'), ('partially_recovered', 'Partially recovered'),
        ('recovered', 'Recovered'), ('written_off', 'Written off'),
    ]
    debtor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                               blank=True, related_name='receivables')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    amount_cents = models.BigIntegerField()
    recovered_cents = models.BigIntegerField(default=0)
    account_code = models.CharField(max_length=10, default='1100')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES,
                              default='open', db_index=True)
    note = models.CharField(max_length=300, blank=True)
    raised_at = models.DateField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def outstanding_cents(self):
        return self.amount_cents - self.recovered_cents


# ──────────────────────────────────────────────────────────────────────
# CH9 — FX revaluation
# ──────────────────────────────────────────────────────────────────────

class FxRevaluation(models.Model):
    snapshot_date = models.DateField()
    currency = models.CharField(max_length=3)
    foreign_amount = models.DecimalField(max_digits=16, decimal_places=2)
    opening_rate = models.DecimalField(max_digits=12, decimal_places=4)
    closing_rate = models.DecimalField(max_digits=12, decimal_places=4)
    gain_loss_cents = models.BigIntegerField(default=0)  # + gain / - loss
    rate_source = models.CharField(max_length=24, default='BNA')
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL,
                                      null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)


# ──────────────────────────────────────────────────────────────────────
# CH3/4/5/7 — Sub-ledger reconciliation
# ──────────────────────────────────────────────────────────────────────

class SubLedgerReconciliation(models.Model):
    LEDGER_CHOICES = [
        ('escrow', 'Escrow (2000)'), ('wallet', 'Wallet (2010)'),
        ('seller_payable', 'Seller payable (2020)'),
        ('cod_clearing', 'COD clearing (2060)'),
    ]
    recon_date = models.DateField(db_index=True)
    ledger = models.CharField(max_length=16, choices=LEDGER_CHOICES)
    gl_account_code = models.CharField(max_length=10)
    sub_ledger_total_cents = models.BigIntegerField(default=0)
    gl_balance_cents = models.BigIntegerField(default=0)
    difference_cents = models.BigIntegerField(default=0)
    balanced = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('recon_date', 'ledger')]


# ──────────────────────────────────────────────────────────────────────
# CH21 — Manual entry approval (segregation of duties)
# ──────────────────────────────────────────────────────────────────────

class ManualEntryApproval(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'), ('approved', 'Approved'),
        ('rejected', 'Rejected'), ('posted', 'Posted'),
    ]
    description = models.CharField(max_length=300)
    period = models.CharField(max_length=7)
    entry_date = models.DateField()
    # [{'account_code','debit_cents','credit_cents','description'}, ...]
    lines = models.JSONField(default=list)
    requested_by = models.ForeignKey(User, on_delete=models.PROTECT,
                                     related_name='manual_entries_requested')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                    blank=True, related_name='+')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES,
                              default='pending', db_index=True)
    posted_entry = models.ForeignKey(JournalEntry, on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)


# ──────────────────────────────────────────────────────────────────────
# CH24 — Financial statement snapshot
# ──────────────────────────────────────────────────────────────────────

class FinancialStatementSnapshot(models.Model):
    period = models.CharField(max_length=7, unique=True)  # 'YYYY-MM'
    # P&L (cents)
    total_revenue_cents = models.BigIntegerField(default=0)
    total_cor_cents = models.BigIntegerField(default=0)
    gross_profit_cents = models.BigIntegerField(default=0)
    total_opex_cents = models.BigIntegerField(default=0)
    ebitda_cents = models.BigIntegerField(default=0)
    other_income_cents = models.BigIntegerField(default=0)
    pbt_cents = models.BigIntegerField(default=0)
    income_tax_cents = models.BigIntegerField(default=0)
    net_profit_cents = models.BigIntegerField(default=0)
    # Balance sheet (cents)
    total_assets_cents = models.BigIntegerField(default=0)
    total_liabilities_cents = models.BigIntegerField(default=0)
    total_equity_cents = models.BigIntegerField(default=0)
    balance_sheet_balanced = models.BooleanField(default=True)
    trial_balance_balanced = models.BooleanField(default=True)
    # KPIs
    take_rate_pct = models.DecimalField(max_digits=6, decimal_places=2,
                                        default=0)
    gross_margin_pct = models.DecimalField(max_digits=6, decimal_places=2,
                                           default=0)
    detail = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(auto_now=True)


# ──────────────────────────────────────────────────────────────────────
# Append-only accounting event log
# ──────────────────────────────────────────────────────────────────────

class AccountingEvent(models.Model):
    kind = models.CharField(max_length=48, db_index=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name='accounting_events')
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    @staticmethod
    def log(kind, actor=None, **payload):
        try:
            AccountingEvent.objects.create(
                kind=kind,
                actor=actor if getattr(actor, 'pk', None) else None,
                payload=payload)
        except Exception:
            pass
