"""
/metrics endpoint — Prometheus text format scrape target.

Refreshes the gauges that need a "current value" snapshot
(outbox queue depth, ledger imbalance) before responding, so each
scrape sees fresh values.
"""
from django.http import HttpResponse
from django.views.decorators.http import require_GET

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from . import metrics as m


def _refresh_snapshots():
    """Compute gauge values that aren't event-driven."""
    # Outbox queue depth
    try:
        from apps.outbox.models import OutboxEvent, EventStatus
        pending = OutboxEvent.objects.filter(
            status__in=(EventStatus.PENDING, EventStatus.RETRYING)
        ).count()
        dead = OutboxEvent.objects.filter(status=EventStatus.DEAD).count()
        m.outbox_pending.set(pending)
        m.outbox_dead.set(dead)
    except Exception:
        pass

    # Ledger imbalance per currency (must be 0; non-zero → alert)
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
            m.ledger_imbalance_cents.labels(currency=cur).set(
                totals['c'] - totals['d']
            )
    except Exception:
        pass


@require_GET
def metrics_view(request):
    _refresh_snapshots()
    return HttpResponse(generate_latest(), content_type=CONTENT_TYPE_LATEST)
