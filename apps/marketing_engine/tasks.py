"""
Celery beat jobs for the marketing engine.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import FlashSaleReservation, PixelEvent

log = logging.getLogger(__name__)


@shared_task(name='marketing_engine.sweep_expired_flash_reservations')
def sweep_expired_flash_reservations():
    """CH5 — release stale reservations every 5 minutes. Without this
    a buyer who abandons checkout would leak flash-sale stock forever."""
    from . import services
    qs = FlashSaleReservation.objects.filter(
        status='active', expires_at__lt=timezone.now(),
    )
    n = 0
    for res in qs[:500]:
        try:
            services.release_flash_reservation(res, reason='expired')
            n += 1
        except Exception:
            pass
    return {'released': n}


@shared_task(name='marketing_engine.pace_ad_campaigns')
def pace_ad_campaigns():
    """CH15 — adjust pacing_multiplier + auto-pause on budget cap."""
    from . import services
    return services.pace_ad_campaigns()


@shared_task(name='marketing_engine.reset_daily_ad_spend')
def reset_daily_ad_spend():
    """Midnight UTC: zero daily_spend, restore paused-by-budget."""
    from . import services
    n = services.reset_daily_ad_spend()
    return {'reset': n}


@shared_task(name='marketing_engine.forward_pixel_events')
def forward_pixel_events():
    """CH16 — process queued pixel events. In dev we mark them sent
    without actually posting to providers."""
    qs = PixelEvent.objects.filter(status='queued')[:500]
    n = 0
    for ev in qs:
        ev.status = 'sent'
        ev.sent_at = timezone.now()
        ev.attempt_count = (ev.attempt_count or 0) + 1
        ev.save(update_fields=['status', 'sent_at', 'attempt_count'])
        n += 1
    return {'forwarded': n}


@shared_task(name='marketing_engine.detect_promo_abuse')
def detect_promo_abuse():
    """CH23 — hourly sweep over recent redemptions."""
    from . import services
    return {'flagged': services.detect_promotion_abuse_window(window_hours=24)}


@shared_task(name='marketing_engine.snapshot_marketing_kpis')
def snapshot_marketing_kpis():
    from . import services
    snap = services.snapshot_marketing_kpis()
    return {'date': str(snap.snapshot_date)}


@shared_task(name='marketing_engine.compute_active_promotion_lift')
def compute_active_promotion_lift():
    """Daily lift compute for promotions that ended yesterday."""
    from . import services
    from .models import MePromotion
    today = timezone.now().date()
    yesterday = today - timedelta(days=1)
    qs = MePromotion.objects.filter(
        status__in=('active', 'ended'),
        valid_until__date__gte=today - timedelta(days=30),
    )
    n = 0
    for p in qs[:200]:
        try:
            services.compute_promotion_lift(
                promotion=p,
                window_start=max(p.valid_from.date(), today - timedelta(days=30)),
                window_end=min(p.valid_until.date(), today),
            )
            n += 1
        except Exception as e:
            log.exception('lift compute failed promo=%s err=%s', p.pk, e)
    return {'computed': n}
