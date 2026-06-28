"""
MICHA Payments — Angola-specific & deeper.

Source: MICHA_Payments_Angola_Deep_1.docx (24 chapters).

Everything is integer cents (AOA minor units) — never float (doc CH13).

Chapters that live HERE (genuinely new / strengthened):
  CH2   PaymentFlow             enforced state machine (see state_machine.py)
  CH23  PaymentAuditEvent       immutable event log w/ correlation id
  CH3   CodEligibilityConfig, BuyerCodProfile, CodCollection
  CH4   CourierCashPosition, CodCashRemittance  (cash chain of custody)
  CH5   MulticaixaReference     reference lifecycle + expiry + regen lineage
  CH7   BankTransferProof       comprovativo hash dedup + verification queue
  CH9   WalletLedgerEntry       double-entry, per-entry idempotency, balance_after
  CH10  WalletTransfer          P2P atomic two-sided
  CH11  SettlementRecord        APPYPAY settlement file three-way match
  CH12  DunningState            per-flow dunning step tracking
  CH24  PaymentsAngolaKpiSnapshot

Bridged (not duplicated):
  payment_gateways.PaymentIntent / MulticaixaGateway  (PSP wire calls)
  payment_ops.BuyerWallet (cached balance) / ReconciliationException
  logistics_ops.CodTransaction (per-label COD flag)
  ledger.Account/Journal/LedgerEntry (GL postings)
  idempotency.IdempotencyKey (HTTP idempotency)
"""
from django.conf import settings
from django.db import models

from .state_machine import STATE_CHOICES, CREATED

User = settings.AUTH_USER_MODEL

METHOD_CHOICES = [
    ('cod', 'Cash on delivery'),
    ('mcx_reference', 'Multicaixa reference'),
    ('mcx_push', 'Multicaixa Express push'),
    ('bank_transfer', 'Bank transfer'),
    ('wallet', 'MICHA wallet'),
    ('split', 'Split payment'),
]


# ──────────────────────────────────────────────────────────────────────
# CH2 — Payment flow (the enforced state machine instance)
# ──────────────────────────────────────────────────────────────────────

class PaymentFlow(models.Model):
    """One per order payment attempt. The authoritative Angola payment
    record; links to a payment_gateways.PaymentIntent for the PSP leg.
    """
    import uuid as _uuid
    id = models.UUIDField(primary_key=True, default=_uuid.uuid4,
                          editable=False)
    order_id = models.CharField(max_length=64, db_index=True)
    buyer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name='payment_flows')
    method = models.CharField(max_length=16, choices=METHOD_CHOICES,
                              db_index=True)
    amount_cents = models.BigIntegerField()
    currency = models.CharField(max_length=3, default='AOA')
    status = models.CharField(max_length=20, choices=STATE_CHOICES,
                              default=CREATED, db_index=True)
    # Caller-supplied idempotency key — same key = same flow (doc CH14).
    idempotency_key = models.CharField(max_length=80, unique=True)
    correlation_id = models.CharField(max_length=64, db_index=True)
    # Link to the PSP intent (payment_gateways) for prepaid legs.
    gateway_intent_id = models.CharField(max_length=80, blank=True)
    psp_reference = models.CharField(max_length=128, blank=True)
    refunded_cents = models.BigIntegerField(default=0)
    settled = models.BooleanField(default=False)  # APPYPAY settlement match
    fee_cents = models.BigIntegerField(default=0)
    net_cents = models.BigIntegerField(default=0)
    expires_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['status', 'method']),
            models.Index(fields=['method', 'settled', 'status']),
        ]

    def __str__(self):
        return f'flow:{self.id} {self.method}:{self.status}'


class PaymentComponent(models.Model):
    """One funding source of a split payment (doc CH8). Parent PAID only
    when ALL components PAID.
    """
    flow = models.ForeignKey(PaymentFlow, on_delete=models.CASCADE,
                             related_name='components')
    method = models.CharField(max_length=16, choices=METHOD_CHOICES)
    amount_cents = models.BigIntegerField()
    status = models.CharField(max_length=20, choices=STATE_CHOICES,
                              default=CREATED)
    psp_reference = models.CharField(max_length=128, blank=True)
    wallet_hold_idempotency_key = models.CharField(max_length=80, blank=True)
    hold_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


# ──────────────────────────────────────────────────────────────────────
# CH23 — Immutable payment event log
# ──────────────────────────────────────────────────────────────────────

class PaymentAuditEvent(models.Model):
    """INSERT-only. Every state transition + money movement lands here.
    Correlation id ties order ↔ flow ↔ components ↔ ledger ↔ webhooks.
    """
    flow = models.ForeignKey(PaymentFlow, on_delete=models.CASCADE,
                             null=True, blank=True, related_name='events')
    correlation_id = models.CharField(max_length=64, db_index=True)
    event_type = models.CharField(max_length=48, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    actor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                              blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['created_at']
        indexes = [models.Index(fields=['event_type', '-created_at'])]


# ──────────────────────────────────────────────────────────────────────
# CH3 — COD eligibility + buyer profile + collection
# ──────────────────────────────────────────────────────────────────────

class CodEligibilityConfig(models.Model):
    """Singleton admin-tunable COD config (doc CH3.1). Row id 1."""
    enabled_provinces = models.JSONField(default=list)  # ['Luanda', ...]
    max_order_cents = models.BigIntegerField(default=15_000_000)     # 150k Kz
    min_order_cents = models.BigIntegerField(default=100_000)        # 1k Kz
    new_user_cap_cents = models.BigIntegerField(default=3_000_000)   # 30k Kz
    max_concurrent_exposure_cents = models.BigIntegerField(
        default=30_000_000)                                          # 300k Kz
    cod_fee_cents = models.BigIntegerField(default=50_000)           # 500 Kz
    restricted_categories = models.JSONField(default=list)
    courier_cash_limit_cents = models.BigIntegerField(default=20_000_000)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def current(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class BuyerCodProfile(models.Model):
    """Per-buyer COD risk state (doc CH3/CH18)."""
    buyer = models.OneToOneField(User, on_delete=models.CASCADE,
                                 related_name='cod_profile')
    refusal_count_90d = models.PositiveIntegerField(default=0)
    total_refusals = models.PositiveIntegerField(default=0)
    open_exposure_cents = models.BigIntegerField(default=0)
    cod_disabled = models.BooleanField(default=False)
    cod_disabled_reason = models.CharField(max_length=120, blank=True)
    last_refusal_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


COD_COLLECTION_STATUS = [
    ('pending', 'Pending (shipped, awaiting collection)'),
    ('collected', 'Collected'),
    ('refused', 'Refused'),
    ('not_present', 'Buyer not present'),
    ('failed', 'Failed (max attempts)'),
]


class CodCollection(models.Model):
    """The per-order COD cash event. Bridges logistics_ops.CodTransaction
    for the per-label flag; this is the payment-side record.
    """
    flow = models.OneToOneField(PaymentFlow, on_delete=models.CASCADE,
                                related_name='cod_collection')
    order_id = models.CharField(max_length=64, db_index=True)
    courier = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                blank=True, related_name='cod_collections')
    amount_cents = models.BigIntegerField()
    status = models.CharField(max_length=12, choices=COD_COLLECTION_STATUS,
                              default='pending', db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    proof_of_delivery_key = models.CharField(max_length=300, blank=True)
    collected_at = models.DateTimeField(null=True, blank=True)
    remittance = models.ForeignKey(
        'CodCashRemittance', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='collections')
    reconciled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


# ──────────────────────────────────────────────────────────────────────
# CH4 — Cash chain of custody
# ──────────────────────────────────────────────────────────────────────

class CourierCashPosition(models.Model):
    """Real-time view of a courier's cash-on-hand + shortfall exposure."""
    courier = models.OneToOneField(User, on_delete=models.CASCADE,
                                   related_name='cash_position')
    cash_on_hand_cents = models.BigIntegerField(default=0)
    cash_shortfall_cents = models.BigIntegerField(default=0)
    cod_privilege_suspended = models.BooleanField(default=False)
    last_collection_at = models.DateTimeField(null=True, blank=True)
    last_remittance_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


REMITTANCE_STATUS = [
    ('collected', 'Collected (liability on courier)'),
    ('in_transit', 'In transit'),
    ('deposited', 'Deposited'),
    ('bank_confirmed', 'Bank confirmed'),
    ('reconciled', 'Reconciled (settlement unlocked)'),
    ('short', 'Short (deposited < expected)'),
    ('over', 'Over (deposited > expected)'),
]


class CodCashRemittance(models.Model):
    """A courier's cash handover batch moving through the custody chain."""
    courier = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                blank=True, related_name='cash_remittances')
    expected_cents = models.BigIntegerField(default=0)   # sum of collections
    deposited_cents = models.BigIntegerField(default=0)
    status = models.CharField(max_length=14, choices=REMITTANCE_STATUS,
                              default='collected', db_index=True)
    deposit_reference = models.CharField(max_length=120, blank=True)
    deposited_to = models.CharField(max_length=40, blank=True)  # BAI / hub
    discrepancy_cents = models.BigIntegerField(default=0)
    collected_at = models.DateTimeField(auto_now_add=True, db_index=True)
    deposited_at = models.DateTimeField(null=True, blank=True)
    bank_confirmed_at = models.DateTimeField(null=True, blank=True)
    reconciled_at = models.DateTimeField(null=True, blank=True)


class CodReconciliationException(models.Model):
    """Daily three-way COD match exception (EXPECTED==COLLECTED==BANKED)."""
    courier = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                blank=True, related_name='+')
    recon_date = models.DateField(db_index=True)
    expected_cents = models.BigIntegerField(default=0)
    collected_cents = models.BigIntegerField(default=0)
    banked_cents = models.BigIntegerField(default=0)
    resolved = models.BooleanField(default=False)
    note = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ──────────────────────────────────────────────────────────────────────
# CH5 — Multicaixa reference payment
# ──────────────────────────────────────────────────────────────────────

class MulticaixaReference(models.Model):
    """A reference the buyer pays at any ATM / MCX app / internet banking.
    Expires; a new one is a new row (old never reused → full audit).
    """
    flow = models.ForeignKey(PaymentFlow, on_delete=models.CASCADE,
                             related_name='mcx_references')
    entity = models.CharField(max_length=12, blank=True)   # entidade
    reference = models.CharField(max_length=40, db_index=True)
    amount_cents = models.BigIntegerField()
    psp_reference = models.CharField(max_length=128, blank=True)
    is_active = models.BooleanField(default=True)
    paid = models.BooleanField(default=False)
    # Lineage: a regenerated reference points at the one it replaced.
    supersedes = models.ForeignKey('self', on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='+')
    expires_at = models.DateTimeField(db_index=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ──────────────────────────────────────────────────────────────────────
# CH7 — Bank transfer proof verification
# ──────────────────────────────────────────────────────────────────────

PROOF_STATUS = [
    ('pending', 'Pending review'),
    ('auto_verified', 'Auto-verified (statement match)'),
    ('verified', 'Verified (manual)'),
    ('rejected', 'Rejected'),
    ('clarification', 'Clarification requested'),
    ('duplicate', 'Duplicate comprovativo'),
]


class BankTransferProof(models.Model):
    """Buyer-uploaded comprovativo. file_hash dedups reuse across orders."""
    flow = models.ForeignKey(PaymentFlow, on_delete=models.CASCADE,
                             related_name='bank_proofs')
    bank = models.CharField(max_length=24, blank=True)  # BAI / Atlantico
    declared_amount_cents = models.BigIntegerField()
    declared_date = models.DateField(null=True, blank=True)
    reference_code = models.CharField(max_length=64, blank=True)  # MICHA-{id}
    file_key = models.CharField(max_length=300, blank=True)
    file_hash = models.CharField(max_length=64, db_index=True)  # sha256 dedup
    status = models.CharField(max_length=14, choices=PROOF_STATUS,
                              default='pending', db_index=True)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True,
                                    blank=True, related_name='+')
    review_note = models.CharField(max_length=300, blank=True)
    statement_matched = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)


# ──────────────────────────────────────────────────────────────────────
# CH9 / CH10 — Wallet double-entry ledger + P2P
# ──────────────────────────────────────────────────────────────────────

class WalletLedgerEntry(models.Model):
    """Double-entry, idempotent wallet movement (doc CH9). The UNIQUE
    idempotency_key is the core safety property: a redelivered webhook
    cannot credit twice (INSERT fails on duplicate). balance_after is the
    running snapshot; the ledger is the source of truth, the cached
    BuyerWallet balance is a convenience kept in sync inside the same txn.
    """
    DIRECTION_CHOICES = [('credit', 'Credit'), ('debit', 'Debit')]
    REFERENCE_CHOICES = [
        ('topup', 'Top-up'), ('order_payment', 'Order payment'),
        ('refund', 'Refund'), ('p2p_in', 'P2P in'), ('p2p_out', 'P2P out'),
        ('split_hold', 'Split hold'), ('split_release', 'Split release'),
        ('promo', 'Promo credit'), ('dispute_payout', 'Dispute payout'),
        ('adjustment', 'Adjustment'),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE,
                             related_name='wallet_ledger')
    direction = models.CharField(max_length=6, choices=DIRECTION_CHOICES)
    amount_cents = models.BigIntegerField()
    balance_after_cents = models.BigIntegerField()
    reference_type = models.CharField(max_length=20, choices=REFERENCE_CHOICES)
    reference_id = models.CharField(max_length=80, blank=True)
    idempotency_key = models.CharField(max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=['user', '-created_at'])]


class WalletIntegrityBreach(models.Model):
    """Recorded when ledger sum != cached balance (doc CH9 daily check)."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='+')
    ledger_balance_cents = models.BigIntegerField()
    cached_balance_cents = models.BigIntegerField()
    resolved = models.BooleanField(default=False)
    detected_at = models.DateTimeField(auto_now_add=True)


class WalletTransfer(models.Model):
    """P2P wallet-to-wallet (doc CH10). Two balanced ledger entries."""
    STATUS_CHOICES = [
        ('pending', 'Pending'), ('completed', 'Completed'),
        ('held_for_review', 'Held for review'), ('rejected', 'Rejected'),
        ('reversed', 'Reversed'),
    ]
    import uuid as _uuid
    id = models.UUIDField(primary_key=True, default=_uuid.uuid4,
                          editable=False)
    sender = models.ForeignKey(User, on_delete=models.CASCADE,
                               related_name='transfers_sent')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE,
                                  related_name='transfers_received')
    amount_cents = models.BigIntegerField()
    note = models.CharField(max_length=140, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES,
                              default='pending', db_index=True)
    hold_reason = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)


# ──────────────────────────────────────────────────────────────────────
# CH11 — APPYPAY settlement file three-way match
# ──────────────────────────────────────────────────────────────────────

class SettlementRecord(models.Model):
    """One line of the APPYPAY settlement file (per transaction)."""
    MATCH_CHOICES = [
        ('unmatched', 'Unmatched'),
        ('matched', 'Matched'),
        ('amount_mismatch', 'Amount mismatch'),
        ('unknown_settlement', 'Unknown settlement'),
    ]
    settlement_date = models.DateField(db_index=True)
    psp_reference = models.CharField(max_length=128, db_index=True)
    merchant_order_id = models.CharField(max_length=80, blank=True)
    gross_cents = models.BigIntegerField()
    fee_cents = models.BigIntegerField(default=0)
    net_cents = models.BigIntegerField(default=0)
    psp_status = models.CharField(max_length=24, blank=True)
    match_status = models.CharField(max_length=20, choices=MATCH_CHOICES,
                                    default='unmatched', db_index=True)
    flow = models.ForeignKey(PaymentFlow, on_delete=models.SET_NULL,
                             null=True, blank=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('settlement_date', 'psp_reference')]


class SettlementRun(models.Model):
    """Per-day reconciliation run summary (doc CH11 state)."""
    STATUS_CHOICES = [
        ('pending', 'Pending'), ('in_progress', 'In progress'),
        ('reconciled', 'Reconciled'), ('has_exceptions', 'Has exceptions'),
    ]
    run_date = models.DateField(unique=True)
    total_internal_paid = models.PositiveIntegerField(default=0)
    matched = models.PositiveIntegerField(default=0)
    exceptions = models.PositiveIntegerField(default=0)
    match_rate_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                         default=0)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES,
                              default='pending')
    created_at = models.DateTimeField(auto_now_add=True)


# ──────────────────────────────────────────────────────────────────────
# CH12 — Dunning
# ──────────────────────────────────────────────────────────────────────

class DunningState(models.Model):
    """Tracks which reminder steps have fired for a pending flow."""
    flow = models.OneToOneField(PaymentFlow, on_delete=models.CASCADE,
                                related_name='dunning')
    steps_sent = models.JSONField(default=list, blank=True)  # ['T+1h', ...]
    reminders_sent = models.PositiveSmallIntegerField(default=0)
    last_reminder_at = models.DateTimeField(null=True, blank=True)
    recovered = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)


# ──────────────────────────────────────────────────────────────────────
# CH24 — KPI snapshot
# ──────────────────────────────────────────────────────────────────────

class PaymentsAngolaKpiSnapshot(models.Model):
    snapshot_date = models.DateField(unique=True)
    payment_success_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                              default=0)   # >95
    cod_acceptance_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                             default=0)    # >90
    cod_refusal_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                          default=0)       # <8
    cash_in_transit_cents = models.BigIntegerField(default=0)
    reference_conversion_pct = models.DecimalField(max_digits=5,
                                                   decimal_places=2,
                                                   default=0)  # >60
    dunning_recovery_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                               default=0)   # >30
    settlement_match_pct = models.DecimalField(max_digits=5, decimal_places=2,
                                               default=0)   # 100
    open_recon_exceptions = models.PositiveIntegerField(default=0)
    wallet_integrity_ok = models.BooleanField(default=True)
    chargeback_rate_pct = models.DecimalField(max_digits=6, decimal_places=3,
                                              default=0)    # <0.3
    method_mix = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(auto_now=True)


class ProcessedWebhookEvent(models.Model):
    """Receive-time replay protection for inbound PSP webhooks (API doc Part 2
    CH33). A webhook is an AUTHORITATIVE money signal, so a captured-and-
    replayed signed request must be a fast no-op: the unique ``event_key``
    makes re-processing impossible (DB rejects the duplicate), and the view
    returns 200 ack without moving money again.

    INSERT-ONLY. ``event_key`` is the provider event id when supplied, else a
    deterministic hash of the identifying fields (merchant_order_id + psp_ref
    + status) so even providers that omit an explicit id are de-duplicated.
    """
    id = models.BigAutoField(primary_key=True)
    provider = models.CharField(max_length=40, default='appypay', db_index=True)
    event_key = models.CharField(max_length=128, unique=True, db_index=True)
    merchant_order_id = models.CharField(max_length=120, blank=True)
    psp_status = models.CharField(max_length=40, blank=True)
    received_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=['provider', '-received_at'])]
