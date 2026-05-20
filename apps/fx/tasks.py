"""
apps/fx/tasks.py
─────────────────

Celery tasks for FX rate freshness.

  • refresh_fx_rates() — fetches latest rates from configured feeds
    and calls update_rate() with the drift guard active. Drift events
    are LOGGED but not auto-overridden — operators decide whether to
    force a large move (real devaluation) or investigate (broken feed).

  • check_fx_staleness() — emits a warning + metric for every current
    rate older than FX_MAX_AGE_HOURS. Without this nobody notices when
    the refresh worker has been silently broken for two weeks.

Beat schedule (add to CELERY_BEAT_SCHEDULE):

    'fx-refresh-rates': {
        'task': 'fx.refresh_rates',
        'schedule': 3600,                      # hourly
        'options': {'queue': 'default'},
    },
    'fx-check-staleness': {
        'task': 'fx.check_staleness',
        'schedule': 1800,                      # every 30 minutes
        'options': {'queue': 'low'},
    },

Which pairs to refresh
───────────────────────
Pulled from settings.FX_REFRESH_PAIRS (a list of (src, tgt) tuples).
Default covers the AOA pairs most relevant to MICHA: USD↔AOA, EUR↔AOA,
BRL↔AOA. Operators add others (ZAR, GBP, CNY) as the marketplace
expands cross-border.
"""
from __future__ import annotations

import logging
from celery import shared_task


log = logging.getLogger(__name__)


def _refresh_pairs() -> list:
    try:
        from django.conf import settings
        pairs = getattr(settings, 'FX_REFRESH_PAIRS', None)
        if pairs:
            return [(s.upper(), t.upper()) for (s, t) in pairs]
    except Exception:
        pass
    # Sensible default: USD/EUR/BRL ↔ AOA (and inverses).
    return [
        ('USD', 'AOA'), ('AOA', 'USD'),
        ('EUR', 'AOA'), ('AOA', 'EUR'),
        ('BRL', 'AOA'), ('AOA', 'BRL'),
    ]


@shared_task(name='fx.refresh_rates')
def refresh_fx_rates_task() -> dict:
    """Pull latest rates from configured feeds, update via the
    drift-guarded service layer.

    Returns a summary: {updated, skipped, drift_blocked, errors, feeds_used}.
    """
    from apps.fx.feeds import get_default_feeds, FeedNotConfigured, FeedError
    from apps.fx.service import update_rate, FXDriftError, FXError, FXRateSource

    pairs = _refresh_pairs()
    feeds = get_default_feeds()

    # Walk feeds in priority order; later feeds only fill pairs the
    # earlier ones didn't cover.
    seen = {}
    feeds_used = []
    for feed in feeds:
        outstanding = [p for p in pairs if p not in seen]
        if not outstanding:
            break
        try:
            results = feed.fetch(outstanding)
        except FeedNotConfigured:
            log.info('fx.refresh_rates: feed %s not configured — skipping',
                     feed.name)
            continue
        except FeedError as e:
            log.warning('fx.refresh_rates: feed %s failed: %s', feed.name, e)
            continue
        except Exception:
            log.exception('fx.refresh_rates: feed %s raised', feed.name)
            continue

        if results:
            feeds_used.append(feed.name)
        for k, v in results.items():
            if k not in seen:
                seen[k] = (feed.name, v)

    summary = {
        'updated': 0,
        'skipped': 0,
        'drift_blocked': 0,
        'errors': 0,
        'feeds_used': feeds_used,
    }

    # Map feed.name → FXRateSource enum value (best-effort).
    _source_for = {
        'bna_api': FXRateSource.BNA_API,
        'external': FXRateSource.EXTERNAL,
    }

    for (src, tgt), (feed_name, rate) in seen.items():
        try:
            update_rate(
                source_currency=src,
                target_currency=tgt,
                rate=rate,
                source=_source_for.get(feed_name, FXRateSource.MANUAL),
                note=f'auto-refresh via {feed_name}',
            )
            summary['updated'] += 1
        except FXDriftError as e:
            summary['drift_blocked'] += 1
            log.warning(
                'fx.refresh_rates: drift blocked',
                extra={
                    'pair': f'{src}->{tgt}',
                    'current': str(e.current),
                    'proposed': str(e.proposed),
                    'drift_pct': str(round(e.drift_pct, 2)),
                    'feed': feed_name,
                },
            )
        except FXError as e:
            summary['errors'] += 1
            log.warning('fx.refresh_rates: %s->%s rejected: %s', src, tgt, e)
        except Exception:
            summary['errors'] += 1
            log.exception('fx.refresh_rates: %s->%s exploded', src, tgt)

    log.info('fx.refresh_rates complete', extra=summary)
    return summary


@shared_task(name='fx.check_staleness')
def check_fx_staleness_task() -> dict:
    """Emit warnings + metric for any current rate older than the
    staleness cap. Without this, a broken refresh worker is silent.

    Returns {stale_pairs: [{pair, age_hours, ...}, ...], count: N}.
    """
    from apps.fx.service import stale_pairs
    stale = stale_pairs()
    if stale:
        log.warning(
            'fx.staleness: %d pair(s) past max age',
            len(stale),
            extra={'stale_pairs': stale},
        )
    else:
        log.info('fx.staleness: all pairs fresh')
    return {'stale_pairs': stale, 'count': len(stale)}
