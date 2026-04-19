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
    """Recalculate seller scores every 6 hours."""
    try:
        from apps.analytics.models import SellerPerformance
        from django.contrib.auth import get_user_model
        from apps.orders.models import Order
        from decimal import Decimal

        User = get_user_model()
        sellers = User.objects.filter(is_seller=True, is_active=True)
        updated = 0
        for seller in sellers:
            orders = Order.objects.filter(seller=seller)
            total = orders.count()
            if total == 0:
                continue
            delivered = orders.filter(status__in=["delivered","completed"]).count()
            cancelled = orders.filter(status="cancelled").count()
            perf, _ = SellerPerformance.objects.get_or_create(seller=seller)
            perf.completion_rate = Decimal(str(round(delivered / total, 4)))
            perf.on_time_delivery_rate = Decimal(str(round(delivered / total, 4)))
            perf.return_rate = Decimal(str(round(cancelled / total, 4)))
            perf.recalculate()
            updated += 1
        return f"Updated {updated} seller scores"
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
