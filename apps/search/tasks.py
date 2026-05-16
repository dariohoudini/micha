"""
apps/search/tasks.py — periodic search-related Celery tasks.
"""
import logging
from celery import shared_task

log = logging.getLogger(__name__)


@shared_task(name='search.recompute_query_boosts')
def recompute_query_boosts():
    """Rebuild QueryProductBoost from recent SearchEvent rows.

    Scheduled hourly. Cheap enough at our current scale; we'll add per-query
    incremental updates if/when this becomes the hot spot.
    """
    try:
        from apps.search.feedback import recompute_query_boosts as _do
        out = _do()
        log.info('search.recompute_query_boosts: %s', out)
        return out
    except Exception as e:
        log.exception('recompute_query_boosts failed: %s', e)
        return {'error': str(e)}
