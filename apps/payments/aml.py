"""
apps/payments/aml.py
─────────────────────

Anti-Money-Laundering transaction monitoring (R2).

Angola regulatory frame
───────────────────────
Lei n.º 5/20 (Law on Prevention and Combat of Money Laundering) and
Aviso n.º 14/2020 do BNA require:

  • Identification of any transaction ≥ USD 10,000 equivalent (the
    "threshold transaction"). For Angola the BNA peg moves; using
    USD 10k ≈ 9,000,000 AOA as a conservative trigger.

  • Pattern detection for "structuring" — multiple sub-threshold
    transactions in a short window aggregating to above threshold,
    typical of evasion.

  • Rapid wallet drain — large inbound payments followed by immediate
    full payout = classic layering.

  • Suspicious Transaction Reports (STR) submitted to the FIU
    (Unidade de Informação Financeira). MICHA's role: detect + queue
    for the AML Officer to file. Submission itself is a manual /
    secure-portal job out of scope for this code.

This module produces the QUEUE that the AML Officer reviews. No
auto-blocking — false positives have business cost and the
regulator expects human review, not automated refusal.

Detectors
─────────
  threshold_check(tx_amount, currency) -> bool
      Single transaction ≥ AML_SINGLE_TX_THRESHOLD_AOA?

  structuring_check(user, *, days=14) -> dict
      Are there N sub-threshold transactions summing to above
      AML_STRUCTURING_THRESHOLD_AOA in the last N days?

  rapid_drain_check(user, *, window_hours=24) -> dict
      Big inbound (sale) followed by big outbound (payout) within
      window_hours?

  evaluate_payment(payment) -> list[AMLAlert]
      Run all detectors against a fresh Payment. Returns the rows
      created (zero or more).

  evaluate_payout(payout) -> list[AMLAlert]
      Same, against a PayoutRequest.

Model
─────
AMLAlert is the queue row. Append-only. AML Officer transitions:
  open → under_review → reported (filed STR) / dismissed (cleared)
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone


log = logging.getLogger('micha.aml')


# ─── Model ────────────────────────────────────────────────────────────


class AMLAlert(models.Model):
    """A flagged transaction (or pattern) awaiting AML-Officer review.

    Append-only on purpose: regulators expect us to retain the full
    chain of detections + decisions. ``decision`` records the officer's
    call; reopening an alert means filing a new alert row referencing
    the original.
    """

    KIND_CHOICES = [
        ('threshold',   'Single transaction at/above threshold'),
        ('structuring', 'Structuring pattern (multi-tx aggregate)'),
        ('rapid_drain', 'Rapid wallet drain (inbound → immediate payout)'),
        ('manual',      'Manual flag by ops/admin'),
    ]

    STATUS_CHOICES = [
        ('open',          'Open — pending review'),
        ('under_review',  'Under review by AML Officer'),
        ('reported',      'STR filed with FIU'),
        ('dismissed',     'Dismissed — cleared'),
    ]

    SEVERITY_CHOICES = [
        ('low',    'Low'),
        ('medium', 'Medium'),
        ('high',   'High'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='aml_alerts',
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, db_index=True)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES,
                              default='open', db_index=True)

    # Refs to the triggering record(s). Optional — manual flags may
    # not have either.
    payment = models.ForeignKey(
        'orders.Payment', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='aml_alerts',
    )
    payout = models.ForeignKey(
        'payments.PayoutRequest', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='aml_alerts',
    )

    aggregate_amount = models.DecimalField(max_digits=14, decimal_places=2,
                                           default=0)
    detector_payload = models.JSONField(default=dict,
                                        help_text='Detector raw output')
    reason = models.TextField(blank=True, default='')

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='aml_alerts_reviewed',
    )
    review_note = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'payments_aml_alert'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['user', 'kind']),
        ]

    def __str__(self):
        return f'AMLAlert({self.kind}, {self.severity}, {self.status})'


# ─── Settings hooks ───────────────────────────────────────────────────


def _single_threshold() -> Decimal:
    """Single-transaction AML threshold in AOA. Default 9,000,000 ≈ USD 10k."""
    raw = getattr(settings, 'AML_SINGLE_TX_THRESHOLD_AOA', '9000000')
    return Decimal(str(raw))


def _structuring_threshold() -> Decimal:
    raw = getattr(settings, 'AML_STRUCTURING_THRESHOLD_AOA', '9000000')
    return Decimal(str(raw))


def _structuring_window_days() -> int:
    return int(getattr(settings, 'AML_STRUCTURING_WINDOW_DAYS', 14))


def _rapid_drain_window_hours() -> int:
    return int(getattr(settings, 'AML_RAPID_DRAIN_WINDOW_HOURS', 24))


def _rapid_drain_min_amount() -> Decimal:
    raw = getattr(settings, 'AML_RAPID_DRAIN_MIN_AOA', '500000')
    return Decimal(str(raw))


def _enabled() -> bool:
    return bool(getattr(settings, 'AML_MONITORING_ENABLED', True))


# ─── Detectors ────────────────────────────────────────────────────────


def threshold_check(tx_amount: Decimal, currency: str = 'AOA') -> bool:
    """True iff a single transaction meets/exceeds the AML threshold.

    Non-AOA currencies: we don't FX-convert here (treasury team handles
    conversions out-of-band). Future expansion: lookup FXRate for an
    authoritative AOA equivalent before threshold compare.
    """
    if (currency or 'AOA').upper() != 'AOA':
        return False
    try:
        return Decimal(str(tx_amount)) >= _single_threshold()
    except Exception:
        return False


def structuring_check(user, *, days: int = None) -> dict:
    """Detect structuring: multiple sub-threshold txns aggregating
    over a window."""
    days = days or _structuring_window_days()
    threshold = _structuring_threshold()
    single_thresh = _single_threshold()
    since = timezone.now() - timedelta(days=days)

    try:
        from apps.orders.models import Order
        total = (
            Order.objects
            .filter(buyer=user, created_at__gte=since,
                    payment_status='paid')
            # Exclude already-threshold-flagged single txns.
            .filter(total__lt=single_thresh)
            .aggregate(t=Sum('total'))['t']
            or Decimal('0')
        )
    except Exception:
        log.exception('aml: structuring query failed')
        return {'aggregate': '0', 'triggered': False}

    return {
        'window_days': days,
        'threshold': str(threshold),
        'aggregate': str(total),
        'triggered': total >= threshold,
    }


def rapid_drain_check(user, *, window_hours: int = None) -> dict:
    """Detect rapid drain: big inbound payment → immediate big payout
    within window_hours.

    Heuristic: in the window, sum 'paid' Order.total for orders where
    the SELLER is ``user`` (income side) + sum recent PayoutRequest
    amounts for the same user. If both > AML_RAPID_DRAIN_MIN_AOA, flag.
    """
    hours = window_hours or _rapid_drain_window_hours()
    min_amount = _rapid_drain_min_amount()
    since = timezone.now() - timedelta(hours=hours)

    try:
        from apps.orders.models import Order
        from apps.payments.models import PayoutRequest

        inbound = (
            Order.objects
            .filter(seller=user, created_at__gte=since,
                    payment_status='paid')
            .aggregate(t=Sum('total'))['t']
            or Decimal('0')
        )
        outbound = (
            PayoutRequest.objects
            .filter(seller=user, created_at__gte=since)
            .exclude(status__in=('rejected', 'cancelled', 'failed'))
            .aggregate(t=Sum('amount'))['t']
            or Decimal('0')
        )
    except Exception:
        log.exception('aml: rapid_drain query failed')
        return {'inbound': '0', 'outbound': '0', 'triggered': False}

    return {
        'window_hours': hours,
        'inbound': str(inbound),
        'outbound': str(outbound),
        'min_amount': str(min_amount),
        'triggered': inbound >= min_amount and outbound >= min_amount,
    }


# ─── Evaluators (the public surface) ─────────────────────────────────


def evaluate_payment(payment) -> list:
    """Run AML detectors against a fresh Payment + return any alerts
    created. Called from the payment-creation path (webhook handler).
    Always returns a list — empty when nothing flagged."""
    if not _enabled():
        return []

    out = []
    amount = Decimal(str(payment.amount))
    user = getattr(payment.order, 'buyer', None) if hasattr(payment, 'order') else None

    if threshold_check(amount, getattr(payment, 'currency', 'AOA')):
        out.append(_create_alert(
            kind='threshold', severity='high',
            user=user, payment=payment,
            aggregate_amount=amount,
            payload={'amount': str(amount), 'threshold': str(_single_threshold())},
            reason=f'Single transaction {amount} AOA >= AML threshold',
        ))

    if user is not None:
        st = structuring_check(user)
        if st.get('triggered'):
            out.append(_create_alert(
                kind='structuring', severity='medium',
                user=user, payment=payment,
                aggregate_amount=Decimal(st['aggregate']),
                payload=st,
                reason='Sub-threshold transactions aggregate above AML threshold',
            ))

    return out


def evaluate_payout(payout) -> list:
    """Run AML detectors against a PayoutRequest."""
    if not _enabled():
        return []
    out = []
    user = getattr(payout, 'seller', None)
    amount = Decimal(str(payout.amount))

    if threshold_check(amount):
        out.append(_create_alert(
            kind='threshold', severity='high',
            user=user, payout=payout,
            aggregate_amount=amount,
            payload={'amount': str(amount)},
            reason=f'Payout {amount} AOA >= AML threshold',
        ))

    if user is not None:
        rd = rapid_drain_check(user)
        if rd.get('triggered'):
            out.append(_create_alert(
                kind='rapid_drain', severity='high',
                user=user, payout=payout,
                aggregate_amount=Decimal(rd['outbound']),
                payload=rd,
                reason='Rapid wallet drain pattern detected',
            ))

    return out


def _create_alert(**kw) -> AMLAlert:
    payload = kw.pop('payload', {})
    alert = AMLAlert.objects.create(
        detector_payload=payload,
        **kw,
    )
    log.warning(
        'aml_alert_created',
        extra={
            'alert_id': alert.pk,
            'kind': alert.kind,
            'severity': alert.severity,
            'user_id': getattr(kw.get('user'), 'pk', None),
            'amount': str(alert.aggregate_amount),
        },
    )
    _publish_outbox(alert)
    return alert


def _publish_outbox(alert: AMLAlert) -> None:
    try:
        from apps.outbox.service import publish
        publish(
            topic='payments.aml.alert',
            payload={
                'alert_id': alert.pk,
                'kind': alert.kind,
                'severity': alert.severity,
                'user_id': alert.user_id,
                'amount': str(alert.aggregate_amount),
                'reason': alert.reason,
            },
            dedupe_key=f'aml.alert:{alert.pk}',
            ref_type='aml_alert', ref_id=str(alert.pk),
        )
    except Exception:
        log.warning('aml: outbox publish failed', exc_info=True)
