"""
Celery tasks for buyer engagement.

Recurring jobs:
  - Hourly recovery-sequence dispatcher
  - Hourly browse-abandonment dispatcher
  - Daily dormancy recompute
  - Daily win-back send sweep
  - Daily LTV recompute (for active sellers in the cohort)
  - Daily buyer KPI snapshot
  - Daily birthday reward grant
  - Monthly membership billing sweep
"""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import (
    BrowseAbandonmentSignal, EngagementEvent, PremiumMembership,
    RecoverySequenceState, WinBackCampaignRun,
)

User = get_user_model()
log = logging.getLogger(__name__)


@shared_task(name='buyer_engagement.dispatch_recovery_sequences')
def dispatch_recovery_sequences():
    """CH11/12 — pick up active sequences whose next_message_at has
    passed and dispatch the next message. Production hooks the
    in-app push + email send here; for now we just advance the state
    and write the audit event."""
    from . import services
    qs = RecoverySequenceState.objects.filter(
        status='active', next_message_at__lte=timezone.now(),
    )
    n = 0
    for seq in qs.iterator():
        try:
            services.advance_recovery(seq)
            n += 1
        except Exception as e:
            log.exception('recovery dispatch failed seq=%s err=%s',
                          seq.pk, e)
    return {'dispatched': n}


@shared_task(name='buyer_engagement.dispatch_browse_remarketing')
def dispatch_browse_remarketing():
    """CH13 — convert high-intent unnotified browse signals into a
    push/email."""
    qs = BrowseAbandonmentSignal.objects.filter(
        notified=False, high_intent=True,
        created_at__lt=timezone.now() - timedelta(hours=1),
        created_at__gte=timezone.now() - timedelta(hours=48),
    )
    n = 0
    for sig in qs:
        sig.notified = True
        sig.save(update_fields=['notified'])
        EngagementEvent.log(
            user=sig.user, kind='browse.remarketed',
            payload={'signal_id': sig.pk,
                     'products': sig.products_viewed_ids[:5]},
        )
        n += 1
    return {'remarketed': n}


@shared_task(name='buyer_engagement.recompute_dormancy_all')
def recompute_dormancy_all():
    """CH16 — nightly walk over the buyer base to bucket each user
    into a dormancy band."""
    from . import services
    qs = User.objects.filter(is_active=True)
    if hasattr(User, 'is_seller'):
        qs = qs.exclude(is_seller=True)
    n = 0
    for u in qs.iterator(chunk_size=200):
        try:
            services.update_dormancy_state(u)
            n += 1
        except Exception:
            pass
    return {'updated': n}


@shared_task(name='buyer_engagement.dispatch_winback_campaigns')
def dispatch_winback_campaigns():
    """CH16 — for every dormant user, queue the right win-back run.
    Idempotency lives in queue_winback()."""
    from . import services
    from .models import DormancyState
    qs = DormancyState.objects.filter(
        band__in=('lapsing', 'dormant_60', 'dormant_90',
                  'dormant_180', 'dormant_365_plus'),
    )
    n = 0
    for d in qs.iterator(chunk_size=200):
        try:
            run = services.queue_winback(d.user, d.band)
            if run:
                n += 1
        except Exception:
            pass
    return {'queued': n}


@shared_task(name='buyer_engagement.recompute_ltv_all')
def recompute_ltv_all():
    """CH23 — nightly LTV recompute for the active buyer base."""
    from . import services
    qs = User.objects.filter(is_active=True)
    if hasattr(User, 'is_seller'):
        qs = qs.exclude(is_seller=True)
    n = 0
    for u in qs.iterator(chunk_size=200):
        try:
            services.compute_ltv(u); n += 1
        except Exception:
            pass
    return {'updated': n}


@shared_task(name='buyer_engagement.snapshot_buyer_kpis')
def snapshot_buyer_kpis():
    """CH24 — daily roll-up."""
    from . import services
    snap = services.compute_buyer_kpi_snapshot()
    return {'date': str(snap.snapshot_date),
            'new_users': snap.new_users, 'new_buyers': snap.new_buyers}


@shared_task(name='buyer_engagement.grant_birthday_rewards')
def grant_birthday_rewards():
    """CH20 — scan users whose birthday lands today (within the next
    7 days actually per CH18) and grant their reward.  Best-effort
    over a `birthday` field if the User model exposes one."""
    from . import services
    today = timezone.now().date()
    if not hasattr(User, 'birthday') and not hasattr(User, 'date_of_birth'):
        return {'skipped': 'no_birthday_field'}
    field = 'birthday' if hasattr(User, 'birthday') else 'date_of_birth'
    qs = User.objects.filter(is_active=True)
    n = 0
    for u in qs.iterator(chunk_size=200):
        b = getattr(u, field, None)
        if not b:
            continue
        if b.month == today.month and b.day == today.day:
            try:
                services.grant_birthday_reward(u); n += 1
            except Exception:
                pass
    return {'granted': n}


@shared_task(name='buyer_engagement.recompute_affinity_all')
def recompute_affinity_all():
    """CH19 — nightly affinity vector + home feed snapshot for the
    active buyer base. Idempotent (each run inserts a fresh
    HomeFeedPersonalisation snapshot; reads use the latest)."""
    from . import services
    qs = User.objects.filter(is_active=True)
    if hasattr(User, 'is_seller'):
        qs = qs.exclude(is_seller=True)
    n = 0
    for u in qs.iterator(chunk_size=200):
        try:
            services.snapshot_home_feed_for(u); n += 1
        except Exception as e:
            log.exception('affinity recompute failed user=%s err=%s',
                          u.pk, e)
    return {'snapshots': n}


@shared_task(name='buyer_engagement.process_membership_billing')
def process_membership_billing():
    """CH10.2 — monthly billing sweep. For each membership whose
    current_period_end < now, attempt a charge.  In production this
    posts to the PSP API; here we just record the attempt (succeeded)
    via charge_premium so the lifecycle persists honestly."""
    from . import services
    now = timezone.now()
    qs = PremiumMembership.objects.filter(
        status__in=('trial', 'active', 'grace'),
        current_period_end__lte=now, auto_renew=True,
    )
    n = 0
    for m in qs.iterator():
        try:
            # Dev-mode auto-succeed. Production swaps in a PSP call.
            services.charge_premium(
                user=m.user, psp_reference='dev-auto',
                succeeded=True,
            )
            n += 1
        except Exception as e:
            log.exception('membership billing failed user=%s err=%s',
                          m.user_id, e)
    return {'billed': n}
