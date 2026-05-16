"""
apps/alerts/service.py

Public entrypoints:

  save_search(user, *, name, query, filters=None)
    Persist a SavedSearch + record the baseline product set that matches it
    NOW. Future re-runs notify only on additions to that set.

  run_saved_search(saved_search)
    Re-run the query, diff against baseline_product_ids → list of new
    product IDs. If non-empty AND past min_notify_interval, write an
    AlertDelivery + publish 'alert.saved_search_match' outbox event.
    Update baseline to the new union (so we don't re-notify on these
    same IDs next time).

  run_all_saved_searches(batch_size=100)
    Beat-task entrypoint. Pulls up to ``batch_size`` active rows whose
    last_run_at is stale, runs each.

The query path uses apps.products.search.search_products so the
relevance-feedback boost (built earlier) carries through — saved searches
benefit from learned ranking just like interactive searches.
"""
from __future__ import annotations
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import SavedSearch, AlertDelivery, AlertKind, DeliveryChannel

log = logging.getLogger(__name__)


class AlertsError(Exception):
    pass


# ─── Save ─────────────────────────────────────────────────────────────────

def save_search(user, *, name: str, query: str,
                filters: dict | None = None) -> SavedSearch:
    """Create a SavedSearch row + snapshot the current matches as baseline."""
    name = (name or '').strip()[:120]
    if not name:
        raise AlertsError('name required')

    # Normalise the query — must match what apps.search.feedback uses so
    # downstream analysis can join cleanly.
    from apps.search.feedback import normalize_query
    q = normalize_query(query)
    if not q:
        raise AlertsError('query required')

    baseline = _match_products(q, filters or {})

    sr = SavedSearch.objects.create(
        user=user, name=name, query_normalized=q,
        filters=filters or {},
        baseline_product_ids=baseline[:SavedSearch.MAX_BASELINE_SIZE],
        last_run_at=timezone.now(),
    )
    return sr


# ─── Run ──────────────────────────────────────────────────────────────────

def run_saved_search(sr: SavedSearch) -> dict:
    """Re-run the search, find new matches, fire alert if any. Returns
    summary dict for logging / tests."""
    if not sr.is_active:
        return {'skipped': 'inactive'}

    matches = _match_products(sr.query_normalized, sr.filters or {})
    baseline = set(sr.baseline_product_ids or [])
    new_ids = [pid for pid in matches if pid not in baseline][:50]

    now = timezone.now()

    if not new_ids:
        SavedSearch.objects.filter(pk=sr.pk).update(last_run_at=now)
        return {'matches': len(matches), 'new': 0}

    # Throttle by min_notify_interval — buyers don't want a flood.
    if sr.last_notified_at is not None:
        elapsed = (now - sr.last_notified_at).total_seconds()
        if elapsed < (sr.min_notify_interval_seconds or 0):
            SavedSearch.objects.filter(pk=sr.pk).update(last_run_at=now)
            return {'matches': len(matches), 'new': len(new_ids),
                    'skipped': 'rate_limited',
                    'cooldown_remaining_s': int(sr.min_notify_interval_seconds - elapsed)}

    # Fire — write delivery audit + outbox event in one transaction so we
    # never end up with one without the other.
    with transaction.atomic():
        AlertDelivery.objects.create(
            user=sr.user, kind=AlertKind.SAVED_SEARCH,
            channel=DeliveryChannel.OUTBOX,
            saved_search=sr,
            product_ids=new_ids,
            payload={'query': sr.query_normalized,
                     'name': sr.name,
                     'match_count': len(new_ids)},
        )
        # Update baseline = union so we don't re-fire on same items
        new_baseline = list({*baseline, *matches})[:SavedSearch.MAX_BASELINE_SIZE]
        SavedSearch.objects.filter(pk=sr.pk).update(
            last_run_at=now,
            last_notified_at=now,
            baseline_product_ids=new_baseline,
        )

    # Publish outbox AFTER commit so downstream (in-app notifs / push /
    # email) consumes a consistent view. Failure here doesn't roll back
    # the audit row — better to have the audit and miss the notification
    # than lose both.
    try:
        from apps.outbox.service import publish
        publish(
            topic='alert.saved_search_match',
            payload={
                'user_id': sr.user_id,
                'saved_search_id': sr.id,
                'name': sr.name,
                'query': sr.query_normalized,
                'new_product_ids': new_ids,
                'fired_at': now.isoformat(),
            },
            dedupe_key=f'alert.saved_search:{sr.id}:{int(now.timestamp())}',
            ref_type='saved_search', ref_id=str(sr.id),
        )
    except Exception:
        log.warning('outbox publish failed for alert', exc_info=True)

    return {'matches': len(matches), 'new': len(new_ids),
            'notified': True}


def run_all_saved_searches(batch_size: int = 100,
                            min_age_seconds: int = 3600) -> dict:
    """Beat task entrypoint. Picks up to ``batch_size`` saved searches
    whose last_run_at is older than ``min_age_seconds`` (or never run)
    and runs each."""
    cutoff = timezone.now() - timedelta(seconds=min_age_seconds)
    from django.db.models import Q
    qs = (
        SavedSearch.objects
        .filter(is_active=True)
        .filter(Q(last_run_at__isnull=True) | Q(last_run_at__lte=cutoff))
        .order_by('last_run_at')[:batch_size]
    )

    summary = {'processed': 0, 'notified': 0, 'rate_limited': 0, 'errors': 0}
    for sr in qs:
        try:
            res = run_saved_search(sr)
            summary['processed'] += 1
            if res.get('notified'):
                summary['notified'] += 1
            if res.get('skipped') == 'rate_limited':
                summary['rate_limited'] += 1
        except Exception:
            summary['errors'] += 1
            log.exception('run_saved_search failed for %s', sr.id)
    return summary


# ─── Internals ────────────────────────────────────────────────────────────

def _match_products(query_normalized: str, filters: dict) -> list[str]:
    """Run the search query + apply filters. Returns a list of product IDs
    (strings) up to a reasonable cap. Reuses the same code path as the
    interactive search endpoint so behaviour stays consistent."""
    try:
        from apps.products.models import Product
        from apps.products.search import search_products
    except Exception:
        return []

    qs = Product.objects.filter(is_active=True, is_archived=False)

    # Apply structured filters BEFORE FTS so the search runs over a smaller set
    pmin = filters.get('price_min')
    pmax = filters.get('price_max')
    category = filters.get('category')
    brand = filters.get('brand')
    if pmin is not None:
        try: qs = qs.filter(price__gte=pmin)
        except Exception: pass
    if pmax is not None:
        try: qs = qs.filter(price__lte=pmax)
        except Exception: pass
    if category:
        try: qs = qs.filter(category__slug=category)
        except Exception: pass
    if brand:
        try: qs = qs.filter(brand__iexact=brand)
        except Exception: pass

    try:
        qs = search_products(qs, query_normalized)
    except Exception:
        # Degraded mode: search engine unavailable. Return current filtered
        # set so we don't false-alert (better to under-notify than spam).
        return []

    # Cap at MAX_BASELINE_SIZE * 2 — we'll trim to that for storage; the
    # extra is for diff accuracy on the current run.
    return [str(p.id) for p in qs[:SavedSearch.MAX_BASELINE_SIZE * 2]]
