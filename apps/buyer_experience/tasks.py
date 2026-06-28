"""Buyer experience automation (doc CH3/CH7/CH14/CH24)."""
from celery import shared_task


@shared_task(name='buyer_experience.process_due_subscriptions')
def process_due_subscriptions():
    """CH3 — place orders for subscriptions due today (daily)."""
    from . import services
    return services.process_due_subscriptions()


@shared_task(name='buyer_experience.check_price_drops')
def check_price_drops():
    """CH14 — wishlist price-drop alerts (every 4h)."""
    from . import services
    return services.check_price_drops()


@shared_task(name='buyer_experience.expire_questions')
def expire_questions():
    """CH7 — expire unanswered pre-purchase questions (daily)."""
    from . import services
    return services.expire_questions()


@shared_task(name='buyer_experience.snapshot_kpis')
def snapshot_kpis():
    from . import services
    snap = services.snapshot_kpis()
    return {'date': str(snap.snapshot_date)}
