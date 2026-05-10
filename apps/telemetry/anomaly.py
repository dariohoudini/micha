"""
Lightweight anomaly detection over our own DB.

We don't try to be Prometheus + Alertmanager here — that's the long-term
home for alerting. This is a "while-you-build" safety net that runs every
hour, checks 4 of the most important business invariants against rolling
baselines, and emits an `ops.alert` outbox event when something drifts.

Rules
-----
1. refund_rate    — refunded orders in last 1h / orders created in last 1h.
                    Alert if > 3× the rate over the prior 7 days.
2. block_rate     — risk-blocked checkouts in last 1h / risk assessments in 1h.
                    Alert if absolute rate > 30% AND > 3× baseline.
3. ledger_drift   — Σ credits − Σ debits per currency in the ledger; must be 0.
                    Any non-zero is an immediate alert.
4. outbox_dead    — outbox events in `dead` status (max attempts reached).
                    Alert if count > 0 (operator must triage).

Each alert is dedupe-keyed with the date-hour bucket so we don't spam.
"""
import logging
from datetime import timedelta
from django.utils import timezone

logger = logging.getLogger('telemetry.anomaly')


def _emit_alert(metric: str, severity: str, message: str, details: dict):
    """Publish an outbox alert. Idempotent by hour-bucket."""
    try:
        from apps.outbox.service import publish
        bucket = timezone.now().strftime('%Y-%m-%d-%H')
        publish(
            topic='ops.alert',
            payload={
                'metric': metric,
                'severity': severity,
                'message': message,
                'details': details,
            },
            dedupe_key=f'ops.alert:{metric}:{bucket}',
            ref_type='anomaly', ref_id=metric,
            max_attempts=3,
        )
    except Exception:
        logger.exception(f'Failed to publish ops alert for {metric}')


def check_refund_rate():
    from apps.orders.models import Order
    now = timezone.now()
    last_hour = (now - timedelta(hours=1), now)
    last_week = (now - timedelta(days=7), now - timedelta(hours=1))

    h_orders = Order.objects.filter(created_at__range=last_hour).count()
    h_refunded = Order.objects.filter(
        created_at__range=last_hour, status__in=['cancelled', 'refunded'],
    ).count()
    if h_orders < 10:  # not enough volume to be meaningful
        return

    w_orders = Order.objects.filter(created_at__range=last_week).count()
    w_refunded = Order.objects.filter(
        created_at__range=last_week, status__in=['cancelled', 'refunded'],
    ).count()

    h_rate = h_refunded / h_orders
    w_rate = (w_refunded / w_orders) if w_orders else 0.0
    if w_rate > 0 and h_rate > 3 * w_rate:
        _emit_alert(
            'refund_rate', 'high',
            f'Refund rate jumped to {h_rate:.1%} (baseline {w_rate:.1%})',
            {'last_hour_orders': h_orders, 'last_hour_refunded': h_refunded,
             'baseline_orders': w_orders, 'baseline_refunded': w_refunded},
        )


def check_block_rate():
    try:
        from apps.risk.models import RiskAssessment, RiskAction
    except Exception:
        return
    now = timezone.now()
    last_hour = (now - timedelta(hours=1), now)
    last_week = (now - timedelta(days=7), now - timedelta(hours=1))

    h_total = RiskAssessment.objects.filter(created_at__range=last_hour).count()
    h_blocked = RiskAssessment.objects.filter(
        created_at__range=last_hour, action=RiskAction.BLOCK,
    ).count()
    if h_total < 20:
        return

    w_total = RiskAssessment.objects.filter(created_at__range=last_week).count()
    w_blocked = RiskAssessment.objects.filter(
        created_at__range=last_week, action=RiskAction.BLOCK,
    ).count()

    h_rate = h_blocked / h_total
    w_rate = (w_blocked / w_total) if w_total else 0.0
    if h_rate > 0.30 and (w_rate == 0 or h_rate > 3 * w_rate):
        _emit_alert(
            'block_rate', 'high',
            f'Risk block rate spiked to {h_rate:.1%} (baseline {w_rate:.1%})',
            {'last_hour_total': h_total, 'last_hour_blocked': h_blocked,
             'baseline_total': w_total, 'baseline_blocked': w_blocked},
        )


def check_ledger_drift():
    try:
        from apps.ledger.models import LedgerEntry
        from collections import defaultdict
        from django.db.models import Sum
        per_currency = defaultdict(lambda: {'d': 0, 'c': 0})
        rows = (
            LedgerEntry.objects
            .values('account__currency')
            .annotate(d=Sum('debit_cents'), c=Sum('credit_cents'))
        )
        for row in rows:
            cur = row['account__currency'] or 'AOA'
            per_currency[cur]['d'] = row['d'] or 0
            per_currency[cur]['c'] = row['c'] or 0
        for cur, totals in per_currency.items():
            diff = totals['c'] - totals['d']
            if diff != 0:
                _emit_alert(
                    'ledger_drift', 'critical',
                    f'Ledger imbalance in {cur}: {diff} cents',
                    {'currency': cur, 'credits': totals['c'], 'debits': totals['d']},
                )
    except Exception:
        logger.exception('check_ledger_drift failed')


def check_outbox_dead():
    try:
        from apps.outbox.models import OutboxEvent, EventStatus
        dead = OutboxEvent.objects.filter(status=EventStatus.DEAD).count()
        if dead > 0:
            _emit_alert(
                'outbox_dead', 'high',
                f'{dead} outbox event(s) in dead state — manual triage required',
                {'count': dead},
            )
    except Exception:
        logger.exception('check_outbox_dead failed')


def run_all():
    check_refund_rate()
    check_block_rate()
    check_ledger_drift()
    check_outbox_dead()
