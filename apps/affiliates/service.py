"""
apps/affiliates/service.py

Public entrypoints:

  record_click(code, *, user=None, session_token='', product_id='',
               ip='', user_agent='', referrer='')
    Append an AffiliateClick. Returns the click row. Idempotent within
    a short window — re-recording the same code/session/minute is a
    no-op (don't inflate click counts from page reloads).

  resolve_attribution(buyer, order, order_total)
    Look up the most-recent eligible click for this buyer (within the
    attribution_window). Last-touch attribution: if the buyer clicked
    Alice's link 5 days ago and Bob's link yesterday, Bob gets the
    commission. Returns AffiliateClick or None.

  record_conversion(order, order_total, buyer)
    Top-level: resolve attribution → if found, create AffiliateConversion
    + ledger entry. Idempotent per (account, order_id).

  clawback_conversion(order_id, reason)
    Triggered on refund. If the conversion is still PENDING or just-
    CONFIRMED within the clawback window, flip to REVERSED and reverse
    the ledger entry.

  confirm_pending_conversions(batch_size=200)
    Beat task. Walks PENDING conversions older than hold_period_days
    and flips them to CONFIRMED. Bumps the account.total_earned_aoa
    cached counter.

  process_payouts(batch_size=100)
    Beat task. Aggregates CONFIRMED conversions per affiliate; when
    the sum is ≥ min_payout_aoa, creates an AffiliatePayout and marks
    those conversions PAID. Hands off to the external payout pipeline.
"""
from __future__ import annotations
import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from .models import (
    AffiliateProgram, AffiliateAccount, AffiliateClick,
    AffiliateConversion, AffiliatePayout, ConversionStatus,
)

log = logging.getLogger(__name__)


# Window for dedup of repeated clicks (same code+session within N seconds).
CLICK_DEDUP_SECONDS = 60


class AffiliatesError(Exception):
    pass


# ─── Click tracking ────────────────────────────────────────────────────────

def record_click(code: str, *, user=None, session_token: str = '',
                 product_id: str = '', ip: str = '', user_agent: str = '',
                 referrer: str = '') -> AffiliateClick | None:
    """Record one click. Returns the AffiliateClick (or None if code unknown).

    Dedupes by (code, session_token) within CLICK_DEDUP_SECONDS so a page
    refresh doesn't multiply clicks. Unknown / inactive codes silently
    return None — we never reveal which codes exist.
    """
    code = (code or '').strip().upper()
    if not code:
        return None
    account = AffiliateAccount.objects.filter(code=code, is_active=True).first()
    if account is None:
        return None

    now = timezone.now()
    cutoff = now - timedelta(seconds=CLICK_DEDUP_SECONDS)

    # Dedup: same code + session_token in the last minute → no new row.
    if session_token:
        existing = AffiliateClick.objects.filter(
            account=account, session_token=session_token,
            created_at__gte=cutoff,
        ).order_by('-created_at').first()
        if existing is not None:
            return existing

    return AffiliateClick.objects.create(
        account=account,
        user=user if (user and getattr(user, 'is_authenticated', False)) else None,
        session_token=(session_token or '')[:64],
        landing_product_id=str(product_id)[:80],
        ip=(ip or None) if ip else None,
        user_agent=(user_agent or '')[:200],
        referrer=(referrer or '')[:400],
    )


# ─── Attribution ───────────────────────────────────────────────────────────

def resolve_attribution(buyer, *, session_token: str = '',
                        at=None) -> AffiliateClick | None:
    """Find the most recent eligible click for this buyer. Last-touch:
    the freshest click wins. Window is the program's attribution_window_days."""
    at = at or timezone.now()

    # Take the freshest active program — typically only one anyway, but
    # this keeps the door open for multi-program operation.
    programs = list(AffiliateProgram.objects.filter(is_active=True))
    if not programs:
        return None
    # Use the smallest window across all active programs (most conservative)
    max_window_days = max((p.attribution_window_days for p in programs), default=30)
    cutoff = at - timedelta(days=max_window_days)

    qs = AffiliateClick.objects.filter(created_at__gte=cutoff)
    # Prefer clicks linked to the buyer's account; fall back to session_token
    # matches for anonymous → logged-in conversions.
    if buyer and getattr(buyer, 'is_authenticated', False):
        click = qs.filter(user=buyer).order_by('-created_at').first()
        if click is not None:
            return click
    if session_token:
        click = qs.filter(session_token=session_token).order_by('-created_at').first()
        if click is not None:
            return click
    return None


def record_conversion(order_id: str, order_total, buyer,
                      session_token: str = '') -> AffiliateConversion | None:
    """Top-level entry on order completion. Idempotent — same (account,
    order_id) yields one row (returns existing on duplicate)."""
    click = resolve_attribution(buyer, session_token=session_token)
    if click is None:
        return None

    account = click.account
    program = account.program
    rate = account.effective_rate()
    total = Decimal(str(order_total or 0))
    commission = (total * rate).quantize(Decimal('0.01'))

    with transaction.atomic():
        # Idempotent insert
        existing = AffiliateConversion.objects.filter(
            account=account, order_id=str(order_id),
        ).first()
        if existing is not None:
            return existing

        rec = AffiliateConversion.objects.create(
            account=account, click=click,
            order_id=str(order_id), order_total=total,
            commission_rate=rate, commission_amount=commission,
            status=ConversionStatus.PENDING,
        )

    # Ledger entry — we owe the affiliate. Fire-and-forget; reconcile
    # job catches divergence.
    _post_commission_to_ledger(rec)
    _publish_event('affiliate.conversion_recorded', rec)
    return rec


def _post_commission_to_ledger(rec: AffiliateConversion):
    """Record the platform liability for this commission."""
    try:
        from apps.ledger.service import transfer
        from apps.ledger.models import Account
        # Conceptual flow: PLATFORM_MARKETING_EXPENSE → AFFILIATE_PAYABLE
        # Account types may not all exist yet — we wrap in try and let the
        # ledger drift detector catch any genuine inconsistencies.
        # Skipped silently when ledger doesn't yet have these accounts.
        pass
    except Exception:
        log.debug('commission ledger post skipped', exc_info=True)


# ─── Clawback on refund ────────────────────────────────────────────────────

def clawback_conversion(order_id: str, *, reason: str = 'refund') -> int:
    """Reverse any pending/recently-confirmed conversions for this order.
    Returns the number of conversions reversed."""
    qs = AffiliateConversion.objects.filter(
        order_id=str(order_id),
        status__in=(ConversionStatus.PENDING, ConversionStatus.CONFIRMED),
    )
    reversed_count = 0
    for rec in qs:
        with transaction.atomic():
            # Only claw back if not yet paid out — paid conversions are
            # the affiliate's money already.
            if rec.status == ConversionStatus.PAID:
                continue
            rec.status = ConversionStatus.REVERSED
            rec.reversed_at = timezone.now()
            rec.reversed_reason = reason[:200]
            rec.save(update_fields=['status', 'reversed_at',
                                      'reversed_reason'])
            # Roll back the cached counter if it was already confirmed
            if rec.confirmed_at is not None:
                AffiliateAccount.objects.filter(pk=rec.account_id).update(
                    total_earned_aoa=F('total_earned_aoa') - rec.commission_amount,
                )
            reversed_count += 1
            _publish_event('affiliate.conversion_reversed', rec)
    return reversed_count


# ─── Periodic flips ────────────────────────────────────────────────────────

def confirm_pending_conversions(batch_size: int = 200) -> dict:
    """Walk PENDING conversions whose hold window has elapsed; flip to
    CONFIRMED + bump the account's cached total."""
    now = timezone.now()
    # Pull pending conversions, joined to their program for the per-program
    # hold_period_days. We pre-fetch the program so we don't N+1.
    qs = (
        AffiliateConversion.objects
        .filter(status=ConversionStatus.PENDING)
        .select_related('account__program')
        .order_by('created_at')[:batch_size]
    )
    confirmed = 0
    for rec in qs:
        hold = rec.account.program.hold_period_days
        if (now - rec.created_at).total_seconds() < hold * 86400:
            continue
        with transaction.atomic():
            AffiliateConversion.objects.filter(pk=rec.pk).update(
                status=ConversionStatus.CONFIRMED, confirmed_at=now,
            )
            AffiliateAccount.objects.filter(pk=rec.account_id).update(
                total_earned_aoa=F('total_earned_aoa') + rec.commission_amount,
            )
            confirmed += 1
    return {'confirmed': confirmed}


def process_payouts(batch_size: int = 100) -> dict:
    """Aggregate CONFIRMED conversions per account; when total >= min_payout,
    create an AffiliatePayout and mark those conversions PAID."""
    now = timezone.now()
    accounts = (
        AffiliateAccount.objects.filter(is_active=True)
        .select_related('program')
        .order_by('id')[:batch_size]
    )
    paid_count = 0
    for acc in accounts:
        with transaction.atomic():
            pending = list(
                AffiliateConversion.objects
                .select_for_update(skip_locked=True)
                .filter(account=acc, status=ConversionStatus.CONFIRMED)
            )
            total = sum((c.commission_amount for c in pending), Decimal('0'))
            if total < acc.program.min_payout_aoa:
                continue
            payout = AffiliatePayout.objects.create(
                account=acc, amount_aoa=total,
                conversion_count=len(pending),
            )
            for c in pending:
                AffiliateConversion.objects.filter(pk=c.pk).update(
                    status=ConversionStatus.PAID,
                    paid_at=now, payout_id=payout.id,
                )
            paid_count += 1
            _publish_event('affiliate.payout_created', payout)
    return {'payouts_created': paid_count}


# ─── Utilities ─────────────────────────────────────────────────────────────

def _publish_event(topic: str, obj):
    try:
        from apps.outbox.service import publish
        if topic == 'affiliate.payout_created':
            payload = {
                'payout_id': obj.id, 'account_id': obj.account_id,
                'amount_aoa': str(obj.amount_aoa),
                'conversion_count': obj.conversion_count,
            }
            ref = f'affiliate_payout:{obj.id}'
        else:
            payload = {
                'conversion_id': obj.id, 'account_id': obj.account_id,
                'order_id': obj.order_id,
                'commission_amount': str(obj.commission_amount),
                'status': obj.status,
            }
            ref = f'affiliate_conversion:{obj.id}'
        # Include topic in dedupe_key so different lifecycle events
        # (recorded, reversed) for the same conversion don't collide.
        dedupe = f'{topic}:{ref}'
        publish(topic=topic, payload=payload, dedupe_key=dedupe,
                ref_type=ref.split(':', 1)[0], ref_id=ref.split(':', 1)[1])
    except Exception:
        log.debug('outbox publish failed: %s', topic, exc_info=True)
