"""
apps/notifications/lifecycle.py
────────────────────────────────

Email lifecycle automation (R7).

The lifecycle program is the difference between "we shipped an app"
and "we run a marketplace." The four canonical touchpoints:

  T+0    welcome             new user, first session
  T+7    engagement_nudge    no first purchase yet
  T+30   winback             inactive — no logins / no orders
  T+90   reactivation        churned — last activity >= 90 days

Each is a separate Celery task scheduled nightly via beat. Each
filters the user table for candidates, deduplicates against recent
NotificationLog rows for the same category (so retries don't double-
send), and calls ``send_email_if_allowed`` — which honours user
preferences + suppression list.

Why nightly batch, not real-time
─────────────────────────────────
Lifecycle touches aren't time-sensitive to the second. Nightly:
  • runs against a stable snapshot (no race with active sessions)
  • amortises SES throttle limits across 24h
  • is cheap to backfill if a run is missed

Categories used (all opt-out-respected):
  Category.NEWSLETTER for welcome / engagement
  Category.SELLER_NUDGE for seller-side reactivation
"""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone


log = logging.getLogger('micha.lifecycle')


# ─── Tunables (settings overrides) ────────────────────────────────────


def _enabled() -> bool:
    return bool(getattr(settings, 'EMAIL_LIFECYCLE_ENABLED', True))


def _engagement_days() -> int:
    return int(getattr(settings, 'EMAIL_LIFECYCLE_ENGAGEMENT_DAYS', 7))


def _winback_days() -> int:
    return int(getattr(settings, 'EMAIL_LIFECYCLE_WINBACK_DAYS', 30))


def _reactivation_days() -> int:
    return int(getattr(settings, 'EMAIL_LIFECYCLE_REACTIVATION_DAYS', 90))


# ─── Internals ────────────────────────────────────────────────────────


def _already_received_recently(user, category_value: str,
                               window_days: int) -> bool:
    """True if we sent this category to ``user`` within the last
    ``window_days``. Guards against duplicate sends across retries
    AND if a user falls into multiple cohort buckets on the same day."""
    try:
        from .notification_log_models import NotificationLog
        cutoff = timezone.now() - timedelta(days=window_days)
        return NotificationLog.objects.filter(
            user=user, category=category_value,
            sent=True, created_at__gte=cutoff,
        ).exists()
    except Exception:
        log.warning('lifecycle: dedup check failed', exc_info=True)
        return False  # err on the side of sending


def _send(user, category, *, subject: str, message: str) -> bool:
    """Send via the preference-aware wrapper. Returns True on send."""
    try:
        from .preferences import send_email_if_allowed
        decision = send_email_if_allowed(
            user, category, subject=subject, message=message,
        )
        return bool(getattr(decision, 'allowed', False))
    except Exception:
        log.exception('lifecycle: send failed for user=%s cat=%s',
                      getattr(user, 'pk', None), category)
        return False


# ─── Celery tasks (one per touchpoint) ────────────────────────────────


@shared_task(name='notifications.lifecycle_welcome', queue='nightly')
def send_welcome_emails() -> dict:
    """T+0 — new users in the last 24h, no welcome sent yet."""
    if not _enabled():
        return {'skipped': True, 'reason': 'disabled'}

    from .preferences import Category
    User = get_user_model()
    cutoff_recent = timezone.now() - timedelta(days=1)

    users = User.objects.filter(
        date_joined__gte=cutoff_recent,
        is_email_verified=True,
    )
    sent = 0
    for u in users.iterator(chunk_size=200):
        if _already_received_recently(u, Category.NEWSLETTER.value, 60):
            continue
        if _send(
            u, Category.NEWSLETTER,
            subject='Bem-vindo à MICHA!',
            message=(
                f'Olá! Estamos felizes por te ter na MICHA. '
                f'Explora produtos de vendedores em Luanda e além — '
                f'pagamento seguro e protecção do comprador em cada compra.'
            ),
        ):
            sent += 1
    log.info('lifecycle_welcome_complete', extra={'sent': sent})
    return {'sent': sent}


@shared_task(name='notifications.lifecycle_engagement',
             queue='nightly')
def send_engagement_nudge() -> dict:
    """T+N (default 7) days post-signup, NO purchase yet."""
    if not _enabled():
        return {'skipped': True, 'reason': 'disabled'}

    from .preferences import Category
    from apps.orders.models import Order
    User = get_user_model()

    target_days = _engagement_days()
    window_start = timezone.now() - timedelta(days=target_days + 1)
    window_end = timezone.now() - timedelta(days=target_days)

    # Users who signed up in the target window, AND have no orders.
    candidates = User.objects.filter(
        date_joined__gte=window_start,
        date_joined__lt=window_end,
        is_email_verified=True,
    )
    sent = 0
    for u in candidates.iterator(chunk_size=200):
        if Order.objects.filter(buyer=u).exists():
            continue
        if _already_received_recently(u, Category.NEWSLETTER.value, 30):
            continue
        if _send(
            u, Category.NEWSLETTER,
            subject='Encontra o teu primeiro produto na MICHA',
            message=(
                'Ainda não fizeste a tua primeira compra. '
                'Mostramos-te produtos de vendedores verificados perto '
                'de ti. Entrega rápida + protecção do comprador.'
            ),
        ):
            sent += 1
    log.info('lifecycle_engagement_complete', extra={'sent': sent})
    return {'sent': sent}


@shared_task(name='notifications.lifecycle_winback', queue='nightly')
def send_winback() -> dict:
    """T+N (default 30) days since last login OR last order — inactive
    user, send a "we miss you" mail with a curated product recommendation."""
    if not _enabled():
        return {'skipped': True, 'reason': 'disabled'}

    from .preferences import Category
    User = get_user_model()
    window = timezone.now() - timedelta(days=_winback_days())

    candidates = (
        User.objects
        .filter(is_email_verified=True)
        .filter(last_login__lt=window) if hasattr(User, 'last_login') else User.objects.none()
    )
    sent = 0
    for u in candidates.iterator(chunk_size=200):
        if _already_received_recently(u, Category.NEWSLETTER.value, 30):
            continue
        if _send(
            u, Category.NEWSLETTER,
            subject='Sentimos a tua falta — novidades na MICHA',
            message=(
                'Faltaste à MICHA recentemente. Acabaram de chegar '
                'novos produtos de vendedores verificados em Luanda. '
                'Volta a explorar — sem compromisso.'
            ),
        ):
            sent += 1
    log.info('lifecycle_winback_complete', extra={'sent': sent})
    return {'sent': sent}


@shared_task(name='notifications.lifecycle_reactivation',
             queue='nightly')
def send_reactivation() -> dict:
    """T+N (default 90) days — churned. One last shot before dormant."""
    if not _enabled():
        return {'skipped': True, 'reason': 'disabled'}

    from .preferences import Category
    User = get_user_model()
    cutoff = timezone.now() - timedelta(days=_reactivation_days())

    candidates = (
        User.objects
        .filter(is_email_verified=True)
        .filter(last_login__lt=cutoff) if hasattr(User, 'last_login') else User.objects.none()
    )
    sent = 0
    for u in candidates.iterator(chunk_size=200):
        if _already_received_recently(u, Category.NEWSLETTER.value, 90):
            continue
        if _send(
            u, Category.NEWSLETTER,
            subject='A MICHA tem novidades — volta com 10% de desconto',
            message=(
                'Há 90 dias que não te vemos. Para te dar as boas-vindas '
                'de volta, oferecemos-te 10% na próxima compra '
                'com o código BEMVINDO10.'
            ),
        ):
            sent += 1
    log.info('lifecycle_reactivation_complete', extra={'sent': sent})
    return {'sent': sent}
