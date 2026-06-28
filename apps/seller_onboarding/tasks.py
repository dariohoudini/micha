"""
Celery tasks for the recurring jobs called out by the doc:

  CH15.1  monthly tier recalculation (1st of each month, 02:00 UTC)
  CH16    daily health-score snapshot for every active seller
  CH18    auto-deactivate holiday mode after `holiday_ends_at`
  CH17    annual-fee renewal reminders at D-60, D-30, D-14, D-0
  CH4.3   agreement re-sign campaign when a template flips
          requires_re_sign=True

We don't depend on celery_app being importable at module load — the
@shared_task decorator handles the lazy bind, which keeps the
test/dev environment from blowing up when Celery isn't installed.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import (
    AgreementTemplate, SellerAgreement, SellerApplication,
    SellerFeeInvoice, SellerHolidayLog, SellerOnboardingEvent,
)

User = get_user_model()
log = logging.getLogger(__name__)


@shared_task(name='seller_onboarding.recalculate_tier_all')
def recalculate_tier_all():
    """CH15.1 — recompute tier for every active seller. Bulk-safe via
    chunks of 200 so memory stays flat even with 10k+ sellers."""
    from . import services
    qs = User.objects.filter(is_active=True).only('id')
    if hasattr(User, 'is_seller'):
        qs = qs.filter(is_seller=True)
    total = 0
    changed = 0
    for u in qs.iterator(chunk_size=200):
        try:
            r = services.recalculate_tier(u)
            total += 1
            if r.get('changed'):
                changed += 1
        except Exception as e:
            log.exception('tier recalc failed for user=%s err=%s', u.pk, e)
    SellerOnboardingEvent.log(
        kind='tier.recalc_batch_complete',
        payload={'total': total, 'changed': changed},
    )
    return {'total': total, 'changed': changed}


@shared_task(name='seller_onboarding.snapshot_health_all')
def snapshot_health_all():
    """CH16 — daily health score for every active seller."""
    from . import services
    qs = User.objects.filter(is_active=True).only('id')
    if hasattr(User, 'is_seller'):
        qs = qs.filter(is_seller=True)
    n = 0
    for u in qs.iterator(chunk_size=200):
        try:
            services.snapshot_health_score(u)
            n += 1
        except Exception as e:
            log.exception('health snapshot failed for user=%s err=%s', u.pk, e)
    return {'snapshots_written': n}


@shared_task(name='seller_onboarding.auto_deactivate_holiday')
def auto_deactivate_holiday():
    """CH18 — daily cron: if holiday_ends_at < now, deactivate."""
    today = timezone.now().date()
    expired = SellerHolidayLog.objects.filter(
        deactivated_at__isnull=True, end_date__lt=today,
    )
    n = 0
    for log_row in expired:
        log_row.deactivated_at = timezone.now()
        log_row.save(update_fields=['deactivated_at'])
        SellerOnboardingEvent.log(
            seller=log_row.seller, kind='holiday.auto_deactivated',
            payload={'log_id': log_row.pk},
        )
        n += 1
    return {'auto_deactivated': n}


@shared_task(name='seller_onboarding.fee_renewal_reminders')
def fee_renewal_reminders():
    """CH17 — D-60 / D-30 / D-14 / D-0 reminders on annual fee.

    For dev/preview we just write a SellerOnboardingEvent so the
    timeline shows the reminder. Production attaches an email sender
    to the `fee_invoice.renewal_reminder` event."""
    now = timezone.now()
    n = 0
    for offset in (60, 30, 14, 0):
        target_day = now.date() + timedelta(days=offset) if offset > 0 \
                    else now.date()
        candidates = SellerFeeInvoice.objects.filter(
            status='pending', due_at__date=target_day,
        )
        for inv in candidates:
            SellerOnboardingEvent.log(
                application=inv.application,
                kind='fee_invoice.renewal_reminder',
                payload={'invoice_id': str(inv.id), 'days_to_due': offset},
            )
            n += 1
    return {'reminders_sent': n}


@shared_task(name='seller_onboarding.abandoned_application_sweep')
def abandoned_application_sweep():
    """Mark applications abandoned after 30 days of no activity, per
    CH2.2 enum."""
    cutoff = timezone.now() - timedelta(days=30)
    qs = SellerApplication.objects.filter(
        updated_at__lt=cutoff,
        status__in=('draft', 'kyc_pending', 'more_info', 'agreement_sent',
                    'fee_pending'),
    )
    n = 0
    for app in qs:
        try:
            app.apply_transition('abandoned')
            n += 1
        except Exception:
            pass
    return {'abandoned': n}


@shared_task(name='seller_onboarding.expire_agreements')
def expire_agreements():
    """Move pending-signature agreements past their 30-day window to
    'expired' so the seller is forced to request a fresh one."""
    qs = SellerAgreement.objects.filter(
        status='pending_signature', expires_at__lt=timezone.now(),
    )
    n = qs.update(status='expired')
    return {'expired': n}


@shared_task(name='seller_onboarding.drive_drip_all')
def drive_drip_all():
    """CH6 — walk the drip sequence for every active seller. Idempotent
    via per-(seller, sequence_key) ledger so re-runs don't double-send."""
    from . import services
    qs = User.objects.filter(is_active=True)
    if hasattr(User, 'is_seller'):
        qs = qs.filter(is_seller=True)
    total_queued = 0; total_suppressed = 0
    for u in qs.iterator(chunk_size=200):
        try:
            r = services.drive_drip_for_seller(u)
            total_queued += r.get('queued', 0)
            total_suppressed += r.get('suppressed', 0)
        except Exception as e:
            log.exception('drip failed seller=%s err=%s', u.pk, e)
    return {'queued': total_queued, 'suppressed': total_suppressed}


@shared_task(name='seller_onboarding.recompute_store_types')
def recompute_store_types():
    """CH13 — daily recompute of every seller's store type so a tier
    upgrade or new certificate flips the badge without manual action."""
    from . import services
    qs = User.objects.filter(is_active=True)
    if hasattr(User, 'is_seller'):
        qs = qs.filter(is_seller=True)
    n = 0
    for u in qs.iterator(chunk_size=200):
        try:
            services.recompute_store_type(u)
            n += 1
        except Exception:
            pass
    return {'recomputed': n}


@shared_task(name='seller_onboarding.finalise_deregistrations')
def finalise_deregistrations():
    """CH21 — cron sweep: pick up cooling-off requests whose 30 days
    have elapsed and complete the offboarding."""
    from . import services
    from .models import SellerDeregistrationRequest
    qs = SellerDeregistrationRequest.objects.filter(
        status='cooling_off', effective_at__lte=timezone.now(),
    )
    n = 0
    for req in qs:
        try:
            services.finalise_deregistration(req)
            n += 1
        except Exception as e:
            log.exception('dereg finalise failed req=%s err=%s', req.id, e)
    return {'finalised': n}


@shared_task(name='seller_onboarding.snapshot_funnel')
def snapshot_funnel():
    """CH24 — daily KPI roll-up. Runs at 01:00 UTC so the next-day's
    dashboard has yesterday's complete numbers."""
    from . import services
    return services.compute_funnel_snapshot()


@shared_task(name='seller_onboarding.compute_gmv_rebates_yearly')
def compute_gmv_rebates_yearly():
    """CH17 — annual GMV rebate compute. Targets sellers whose fee
    period (annual) closed in the last 7 days so we sweep around the
    anniversary without strict day-of-year coupling."""
    from . import services
    from .models import SellerApplication
    today = timezone.now().date()
    window_start = today - timedelta(days=372)  # ~ a year ago + grace
    window_end = today - timedelta(days=358)
    eligible_apps = SellerApplication.objects.filter(
        approved_at__date__gte=window_start,
        approved_at__date__lte=window_end,
        seller__isnull=False,
    ).distinct()
    n = 0
    for app in eligible_apps:
        try:
            services.compute_gmv_rebate(
                app.seller,
                period_start=window_start,
                period_end=today,
            )
            n += 1
        except Exception as e:
            log.exception('gmv rebate compute failed seller=%s err=%s',
                          app.seller_id, e)
    return {'computed': n}
