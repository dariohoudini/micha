"""
apps/forecasting/tasks.py — beat-fired recompute across all active products.
"""
import logging
from celery import shared_task

from apps.core.task_locks import singleton_task

log = logging.getLogger(__name__)


@shared_task(name='forecasting.run_all',
             soft_time_limit=900, time_limit=1080)  # catalog sweep: 15/18 min
@singleton_task('beat:forecasting.run_all')
def run_forecasting_all(batch_size: int = 500, lead_time_days: int = 7):
    """Daily forecast pass for every active product. Bounded to ``batch_size``
    per invocation so a 100k-catalog seller doesn't block a worker for
    minutes; beat fires this regularly and we make incremental progress."""
    from apps.products.models import Product
    from apps.forecasting import service as forecasting

    products = Product.objects.filter(
        is_active=True, is_archived=False,
    ).select_related('store').order_by('id')[:batch_size]

    summary = {'processed': 0, 'recommendations': 0, 'errors': 0}
    for p in products:
        try:
            r = forecasting.generate_recommendation(p, lead_time_days=lead_time_days)
            summary['processed'] += 1
            if r.get('needs_reorder'):
                summary['recommendations'] += 1
        except Exception:
            summary['errors'] += 1
            log.exception('forecast failed for product %s', p.pk)
    return summary
