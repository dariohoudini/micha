"""
Analytics Tasks
FIX: Data retention cleanup — FunnelEvent and ActivityLog grow unbounded without this.
"""
from celery import shared_task
from django.utils import timezone
import logging

logger = logging.getLogger("micha")


@shared_task(name="analytics.update_seller_performance_scores")
def update_seller_performance_scores():
    """
    Recalculate all seller performance scores using the validated engine.
    Runs every 6 hours. Computes 5 dimensions: delivery speed, completion
    rate, response rate, review quality, dispute rate.
    """
    try:
        from apps.analytics.performance_engine import update_all_seller_scores
        result = update_all_seller_scores()
        return f"Updated {result['updated']} sellers. Errors: {result['errors']}. Tiers: {result['tiers']}"
    except Exception as e:
        logger.exception(f"Seller performance update failed: {e}")
        return f"Error: {e}"


@shared_task(name="analytics.cleanup_old_funnel_events")
def cleanup_old_funnel_events():
    """
    FIX: FunnelEvent grows 20M+ rows/day at scale.
    Delete events older than DATA_RETENTION[funnel_events] days (default 365).
    """
    from apps.analytics.models import FunnelEvent
    from django.conf import settings
    from datetime import timedelta

    days = getattr(settings, "DATA_RETENTION", {}).get("funnel_events", 365)
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = FunnelEvent.objects.filter(created_at__lte=cutoff).delete()
    logger.info(f"Cleaned {deleted} old funnel events")
    return f"Deleted {deleted} old funnel events"


@shared_task(name="analytics.track_funnel_event")
def track_funnel_event_async(user_id, event, product_id=None, session_id=""):
    """Non-blocking funnel event tracking."""
    try:
        from apps.analytics.models import FunnelEvent
        FunnelEvent.objects.create(
            user_id=user_id, event=event,
            product_id=product_id, session_id=session_id,
        )
    except Exception as e:
        logger.error(f"Funnel event tracking failed: {e}")
