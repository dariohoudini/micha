"""
apps/payments/settlement.py
────────────────────────────

PSP settlement reconciliation (R2).

What AppyPay (and most PSPs) actually send
───────────────────────────────────────────
Every business day around 03:00 WAT, AppyPay produces a settlement
file. Each row is one settled transaction:

  date            2026-05-23
  gateway_ref     PAY-ABC123
  type            sale | refund | chargeback | adjustment
  gross_amount    1000.00
  fee             18.50          (~1.85% of gross)
  net_amount      981.50
  currency        AOA

The platform's PaymentEvent log records the SAME transactions from
our side. Drift between the two sides = either:
  (a) money missing in the gateway
  (b) money missing in our ledger
  (c) a fee miscount
  (d) a chargeback we haven't ingested yet

We MUST reconcile daily because:
  • The treasury team owes the SUM of seller wallets vs. PSP balance.
    Drift compounds. If we under-recognise revenue by 50 AOA per day,
    a year in we owe the IRS ~18k AOA of unreconciled receipts.
  • PSP fee changes silently (AppyPay has bumped 1.5% → 1.85% twice
    without an email). The first you know is when the fees column on
    every row doesn't match what you booked.
  • Some sales never make it to the settlement file — usually because
    the webhook never landed. Reconciliation is the safety net.

What this module does
─────────────────────

  reconcile_settlement_rows(rows, *, run_date) -> SettlementReconRun
      Idempotent: re-running the same date is a no-op for already-
      matched rows. New mismatches re-emit alerts.

      Each row is matched against PaymentEvent (event_type IN
      'paid'/'refunded'/'chargeback') by gateway reference. Three
      outcomes per row:

        matched         amounts agree (drift < 1 AOA)
        drift           same ref, amounts differ → SettlementDrift row
        unknown         no PaymentEvent at all → SettlementDrift row

      Drifts trigger an outbox event ``payments.settlement.drift``
      with the row count + total drift AOA. The DLQ severity gate
      promotes this to CRITICAL when total drift exceeds threshold.

  parse_settlement_csv(file_obj) -> list[dict]
      Lenient CSV parser — handles AppyPay's column variations.
"""
from __future__ import annotations

import csv
import io
import logging
from datetime import date as _date
from decimal import Decimal, InvalidOperation
from typing import Iterable

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


log = logging.getLogger('micha.settlement')


# ─── Models ───────────────────────────────────────────────────────────


class SettlementReconRun(models.Model):
    """One reconciliation run — one settlement-day pass through the file."""

    settlement_date = models.DateField(db_index=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    row_count   = models.PositiveIntegerField(default=0)
    matched     = models.PositiveIntegerField(default=0)
    drift_rows  = models.PositiveIntegerField(default=0)
    unknown_rows = models.PositiveIntegerField(default=0)

    total_gross = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_fees  = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_net   = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_drift = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    notes = models.TextField(blank=True, default='')

    class Meta:
        db_table = 'payments_settlement_recon_run'
        ordering = ['-settlement_date']
        indexes = [models.Index(fields=['-settlement_date'])]

    def __str__(self):
        return f'SettlementReconRun({self.settlement_date}, drift={self.total_drift})'


class SettlementDrift(models.Model):
    """One drift / unknown row from a reconciliation run.

    Append-only. Resolving a drift means writing a follow-up row
    (e.g., a manual journal entry) that closes the gap — not
    editing or deleting this audit trail.
    """

    KIND_CHOICES = [
        ('drift',   'Amount drift (same ref, different amounts)'),
        ('unknown', 'Unknown reference (no PaymentEvent)'),
    ]

    run = models.ForeignKey(
        SettlementReconRun, on_delete=models.CASCADE,
        related_name='drifts',
    )
    kind = models.CharField(max_length=10, choices=KIND_CHOICES)
    gateway_reference = models.CharField(max_length=200, db_index=True)
    type = models.CharField(max_length=20, default='sale',
                            help_text='sale|refund|chargeback|adjustment')
    psp_amount = models.DecimalField(max_digits=14, decimal_places=2)
    ledger_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    drift_amount = models.DecimalField(max_digits=14, decimal_places=2)
    raw_row = models.JSONField(default=dict)

    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'payments_settlement_drift'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['gateway_reference']),
            models.Index(fields=['resolved', '-created_at']),
        ]

    def __str__(self):
        return f'SettlementDrift({self.kind}, ref={self.gateway_reference}, drift={self.drift_amount})'


# ─── Public API ───────────────────────────────────────────────────────


def _drift_threshold() -> Decimal:
    """Below this absolute AOA, treat as matched (rounding noise)."""
    raw = getattr(settings, 'SETTLEMENT_DRIFT_THRESHOLD_AOA', '1.00')
    try:
        return Decimal(str(raw))
    except InvalidOperation:
        return Decimal('1.00')


def reconcile_settlement_rows(rows: Iterable[dict], *,
                              settlement_date: _date) -> SettlementReconRun:
    """Run a reconciliation pass over ``rows``.

    Idempotent: re-running for the same settlement_date creates a new
    run row but rewrites no historical PaymentEvent data — drifts are
    re-detected, but the resolution status of past drift rows is
    untouched.
    """
    from apps.payments.models import PaymentEvent

    threshold = _drift_threshold()

    with transaction.atomic():
        run = SettlementReconRun.objects.create(
            settlement_date=settlement_date,
        )

    matched = drift_count = unknown = 0
    total_gross = total_fees = total_net = total_drift = Decimal('0')

    for raw in rows:
        ref = (raw.get('gateway_reference') or '').strip()
        if not ref:
            continue

        gross = _money(raw.get('gross_amount'))
        fee = _money(raw.get('fee'))
        net = _money(raw.get('net_amount')) or (gross - fee)
        type_ = (raw.get('type') or 'sale').lower()

        total_gross += gross
        total_fees += fee
        total_net += net

        # Look up by gateway_reference on PaymentEvent.details.gateway_ref
        # OR Payment.gateway_reference. The dual-key search handles both
        # storage conventions across the codebase.
        ledger_amount = _ledger_amount_for_ref(ref, type_)

        if ledger_amount is None:
            unknown += 1
            drift = gross
            total_drift += abs(drift)
            SettlementDrift.objects.create(
                run=run, kind='unknown',
                gateway_reference=ref, type=type_,
                psp_amount=gross, ledger_amount=Decimal('0'),
                drift_amount=drift, raw_row=raw,
            )
            continue

        delta = (gross - ledger_amount)
        if abs(delta) < threshold:
            matched += 1
        else:
            drift_count += 1
            total_drift += abs(delta)
            SettlementDrift.objects.create(
                run=run, kind='drift',
                gateway_reference=ref, type=type_,
                psp_amount=gross, ledger_amount=ledger_amount,
                drift_amount=delta, raw_row=raw,
            )

    with transaction.atomic():
        run.row_count = matched + drift_count + unknown
        run.matched = matched
        run.drift_rows = drift_count
        run.unknown_rows = unknown
        run.total_gross = total_gross
        run.total_fees = total_fees
        run.total_net = total_net
        run.total_drift = total_drift
        run.finished_at = timezone.now()
        run.save(update_fields=[
            'row_count', 'matched', 'drift_rows', 'unknown_rows',
            'total_gross', 'total_fees', 'total_net', 'total_drift',
            'finished_at',
        ])

    _publish_summary(run)

    log.info(
        'settlement reconciliation complete',
        extra={
            'settlement_date': str(settlement_date),
            'row_count': run.row_count,
            'matched': matched, 'drift_rows': drift_count,
            'unknown_rows': unknown,
            'total_drift': str(total_drift),
        },
    )
    return run


def parse_settlement_csv(file_obj) -> list:
    """Lenient CSV → list[dict].

    Accepts AppyPay's documented columns + a few synonyms:
      date | settlement_date | settled_at      → date
      gateway_ref | gateway_reference | psp_ref → gateway_reference
      type | transaction_type | kind            → type
      gross | gross_amount | amount             → gross_amount
      fee | fees | psp_fee                       → fee
      net | net_amount                           → net_amount
      currency | ccy                             → currency
    """
    if isinstance(file_obj, (bytes, bytearray)):
        text = file_obj.decode('utf-8', errors='replace')
    elif isinstance(file_obj, str):
        text = file_obj
    else:
        text = file_obj.read()
        if isinstance(text, (bytes, bytearray)):
            text = text.decode('utf-8', errors='replace')

    reader = csv.DictReader(io.StringIO(text))
    out = []
    for row in reader:
        out.append(_normalise_row({k.lower().strip(): (v or '').strip()
                                   for k, v in row.items()}))
    return out


# ─── Internals ────────────────────────────────────────────────────────


_DATE_KEYS = ('date', 'settlement_date', 'settled_at')
_REF_KEYS = ('gateway_reference', 'gateway_ref', 'psp_ref', 'reference')
_TYPE_KEYS = ('type', 'transaction_type', 'kind')
_GROSS_KEYS = ('gross_amount', 'gross', 'amount')
_FEE_KEYS = ('fee', 'fees', 'psp_fee')
_NET_KEYS = ('net_amount', 'net')
_CCY_KEYS = ('currency', 'ccy')


def _normalise_row(row: dict) -> dict:
    def _pick(keys):
        for k in keys:
            if row.get(k):
                return row.get(k)
        return ''
    return {
        'date': _pick(_DATE_KEYS),
        'gateway_reference': _pick(_REF_KEYS),
        'type': (_pick(_TYPE_KEYS) or 'sale').lower(),
        'gross_amount': _pick(_GROSS_KEYS),
        'fee': _pick(_FEE_KEYS),
        'net_amount': _pick(_NET_KEYS),
        'currency': _pick(_CCY_KEYS) or 'AOA',
    }


def _money(raw) -> Decimal:
    if raw in (None, ''):
        return Decimal('0')
    try:
        return Decimal(str(raw).replace(',', ''))
    except InvalidOperation:
        return Decimal('0')


def _ledger_amount_for_ref(ref: str, type_: str):
    """Find our side's amount for a given gateway reference.

    For 'sale' we sum 'paid' PaymentEvents. For 'refund' we look at
    refund events. For 'chargeback' we look at the Chargeback model.

    Returns None when no record found at all (→ unknown), else a
    Decimal that may be 0.
    """
    try:
        from apps.orders.models import Payment
        from apps.payments.models import PaymentEvent

        if type_ in ('sale', 'capture', 'paid'):
            payment = Payment.objects.filter(gateway_reference=ref).first()
            if payment is None:
                return None
            return Decimal(str(payment.amount))

        if type_ in ('refund',):
            # Look at PaymentEvent.details.gateway_refund_id matching ref.
            ev = (
                PaymentEvent.objects
                .filter(event_type__in=('refunded', 'refund_replay'))
                .filter(details__gateway_refund_id=ref)
                .first()
            )
            if ev is None:
                return None
            return Decimal(str((ev.details or {}).get('amount', '0') or '0'))

        if type_ in ('chargeback',):
            from .chargebacks import Chargeback
            cb = Chargeback.objects.filter(external_case_id=ref).first()
            if cb is None:
                return None
            return Decimal(str(cb.amount))

        # Fallback: try Payment.
        payment = Payment.objects.filter(gateway_reference=ref).first()
        return Decimal(str(payment.amount)) if payment else None

    except Exception:
        log.exception('settlement: ledger lookup failed for ref=%s', ref)
        return None


def _publish_summary(run: SettlementReconRun) -> None:
    """Emit an outbox event so the DLQ severity gate alerts ops on
    significant drift. Critical topics route to PagerDuty-equivalent."""
    try:
        from apps.outbox.service import publish
        topic = (
            'payments.settlement.drift'
            if run.total_drift > Decimal('0')
            else 'payments.settlement.matched'
        )
        publish(
            topic=topic,
            payload={
                'settlement_date': run.settlement_date.isoformat(),
                'row_count': run.row_count,
                'matched': run.matched,
                'drift_rows': run.drift_rows,
                'unknown_rows': run.unknown_rows,
                'total_gross': str(run.total_gross),
                'total_fees': str(run.total_fees),
                'total_net': str(run.total_net),
                'total_drift': str(run.total_drift),
            },
            dedupe_key=f'{topic}:{run.pk}',
            ref_type='settlement_run',
            ref_id=str(run.pk),
        )
    except Exception:
        log.warning('settlement: outbox publish failed', exc_info=True)
