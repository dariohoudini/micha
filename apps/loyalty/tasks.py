"""
apps/loyalty/tasks.py — periodic tier recomputation.
"""
import logging
from celery import shared_task

from apps.core.task_locks import singleton_task

log = logging.getLogger(__name__)


@shared_task(name='loyalty.recompute_all_tiers')
@singleton_task('beat:loyalty.recompute_all_tiers')
def recompute_all_tiers(batch_size: int = 500):
    """Walk every user that has made a paid order in the last window and
    recompute their tier. Nightly. Pages over users in batches so this
    bounded even at 1M users."""
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    from datetime import timedelta
    from apps.loyalty.service import recompute_tier, TIER_WINDOW_DAYS

    User = get_user_model()
    cutoff = timezone.now() - timedelta(days=TIER_WINDOW_DAYS)
    # Only users with paid orders in the window need recomputation
    user_ids = list(
        User.objects.filter(
            orders__payment_status='paid', orders__created_at__gte=cutoff,
        ).distinct().values_list('id', flat=True)[:batch_size]
    )
    processed = 0
    for uid in user_ids:
        try:
            u = User.objects.filter(pk=uid).first()
            if u:
                recompute_tier(u)
                processed += 1
        except Exception:
            log.exception('recompute_tier failed for user %s', uid)
    return {'processed': processed}
