"""
apps/loyalty/service.py

Public entrypoints. All mutating ops go through here so the points ledger
stays the single source of truth and the cached User.loyalty_points stays
in sync.

  earn(user, points, reason, ref_type='', ref_id='', dedupe_key=None,
       note='', actor=None)
    Append a positive transaction. Dedupe-keyed by default for earn-from-
    order events: the dedupe_key is auto-derived from (reason, ref_type,
    ref_id) so a duplicate webhook fire produces zero side effects.

  redeem(user, points, reason, ...)
    Append a negative transaction. Refuses if balance would go negative.

  recompute_tier(user)
    Walks the user's last 365 days of earn-order transactions, sums spend,
    flips them to the matching tier. Designed to be called from a beat task
    nightly and from order completion synchronously for instant tier-up.

  get_benefits(user) -> dict
    Returns the user's current tier benefits as a flat dict, cached so
    every checkout page render isn't a DB hit.
"""
from __future__ import annotations
import logging
from decimal import Decimal
from datetime import timedelta

from django.db import transaction, IntegrityError
from django.utils import timezone
from django.db.models import Sum

from .models import (
    Tier, TierBenefit, UserTier, PointsTransaction, PointsReason, TierCode,
)

log = logging.getLogger(__name__)

# Rolling window for qualifying spend
TIER_WINDOW_DAYS = 365
# Grace period — once you've earned a tier, you keep it for N days even if
# spend drops below the threshold. Prevents jerky downgrades.
TIER_DOWNGRADE_GRACE_DAYS = 30


class LoyaltyError(Exception):
    pass


class InsufficientPoints(LoyaltyError):
    pass


class DuplicateTransaction(LoyaltyError):
    pass


# ─── Earn / redeem ─────────────────────────────────────────────────────────

def earn(user, *, points: int, reason: str,
         ref_type: str = '', ref_id: str = '',
         dedupe_key: str | None = None, note: str = '',
         actor=None) -> PointsTransaction:
    """Add positive points to the user's balance. Idempotent via dedupe_key.

    If the same (reason, ref_type, ref_id) was already credited (auto-derived
    dedupe), this is a no-op and returns the existing row.
    """
    if points <= 0:
        raise LoyaltyError('earn() points must be positive')
    if reason not in {r.value for r in PointsReason} or reason.startswith('redeem'):
        raise LoyaltyError(f'invalid earn reason: {reason}')

    # Auto-derive dedupe_key from ref if not supplied. Leave as None when
    # there's no ref — NULL bypasses uniqueness in SQL.
    if dedupe_key is None and ref_type and ref_id:
        dedupe_key = f'{reason}:{ref_type}:{ref_id}'

    return _write_transaction(
        user=user, delta=int(points), reason=reason,
        ref_type=ref_type, ref_id=ref_id, dedupe_key=dedupe_key,
        note=note, actor=actor,
    )


def redeem(user, *, points: int, reason: str,
           ref_type: str = '', ref_id: str = '',
           dedupe_key: str | None = None, note: str = '',
           actor=None) -> PointsTransaction:
    """Subtract points from the user's balance. Refuses if balance would
    go negative (atomically — SELECT FOR UPDATE on the user row)."""
    if points <= 0:
        raise LoyaltyError('redeem() points must be positive')
    if not reason.startswith('redeem'):
        raise LoyaltyError(f'invalid redeem reason: {reason}')

    if dedupe_key is None and ref_type and ref_id:
        dedupe_key = f'{reason}:{ref_type}:{ref_id}'

    return _write_transaction(
        user=user, delta=-int(points), reason=reason,
        ref_type=ref_type, ref_id=ref_id, dedupe_key=dedupe_key,
        note=note, actor=actor, check_balance=True,
    )


def adjust(user, *, delta: int, note: str = '', actor=None) -> PointsTransaction:
    """Admin adjustment — can be positive OR negative. Always allowed by
    sign (admins can take a user negative for fraud clawback). Bypasses
    dedupe (admins may issue multiple) — dedupe_key=None means NULL in SQL,
    which is exempt from the uniqueness constraint."""
    if delta == 0:
        raise LoyaltyError('adjust() delta must be non-zero')
    return _write_transaction(
        user=user, delta=int(delta), reason=PointsReason.ADJUST_ADMIN,
        ref_type='', ref_id='', dedupe_key=None, note=note, actor=actor,
        check_balance=False,
    )


def _write_transaction(*, user, delta, reason, ref_type, ref_id,
                       dedupe_key, note, actor, check_balance=False):
    """The single chokepoint for mutating the points ledger. Holds a row
    lock on User so balance reads + writes can't race."""
    from django.contrib.auth import get_user_model
    User = get_user_model()

    try:
        with transaction.atomic():
            # Lock the user row first — serialises concurrent earn/redeem
            locked = User.objects.select_for_update().get(pk=user.pk)
            current = int(locked.loyalty_points or 0)
            new_balance = current + delta
            if check_balance and new_balance < 0:
                raise InsufficientPoints(
                    f'insufficient points: have {current}, would need {-delta}'
                )

            tx = PointsTransaction.objects.create(
                user=locked, delta=delta, reason=reason,
                ref_type=ref_type[:40], ref_id=str(ref_id)[:80],
                dedupe_key=dedupe_key[:120] if dedupe_key else None,
                balance_after=max(new_balance, 0),  # cached counter clamps at 0
                note=note[:200], actor=actor,
            )
            # Update cached counter (clamped at 0 — User.loyalty_points is
            # PositiveIntegerField. Admin clawback to negative still records
            # the audit row; the counter projects to 0).
            User.objects.filter(pk=locked.pk).update(
                loyalty_points=max(new_balance, 0),
            )
            return tx
    except IntegrityError as e:
        # uniq_user_points_dedupe collision — caller asked to re-credit
        # an already-credited (reason, ref). Treat as idempotent success.
        # Constraint-name vs column-list detection because Postgres reports
        # the constraint name; SQLite reports the column list.
        msg = str(e)
        is_dedupe_collision = (
            'uniq_user_points_dedupe' in msg
            or ('dedupe_key' in msg and 'UNIQUE' in msg.upper())
        )
        if is_dedupe_collision and dedupe_key:
            existing = PointsTransaction.objects.filter(
                user=user, dedupe_key=dedupe_key,
            ).first()
            if existing is not None:
                return existing
        raise


# ─── Tier computation ─────────────────────────────────────────────────────

def _qualifying_spend(user) -> Decimal:
    """Sum the user's order totals over the rolling window. We use Orders
    directly rather than the points ledger because (a) it's the canonical
    money source and (b) points earnings may have non-1:1 multipliers."""
    try:
        from apps.orders.models import Order
    except Exception:
        return Decimal('0')
    cutoff = timezone.now() - timedelta(days=TIER_WINDOW_DAYS)
    total = (
        Order.objects
        .filter(buyer=user, payment_status='paid', created_at__gte=cutoff)
        .aggregate(t=Sum('total'))['t']
    )
    return Decimal(total or 0)


def recompute_tier(user) -> UserTier:
    """Recompute the user's tier from the rolling spend window. Honors
    downgrade grace — a Gold user doesn't drop to Silver the instant
    their qualifying spend dips below the Gold threshold; they stay Gold
    for TIER_DOWNGRADE_GRACE_DAYS more.
    """
    spend = _qualifying_spend(user)

    # Pick the highest tier whose threshold the user has cleared
    tiers = list(Tier.objects.filter(is_active=True).order_by('-rank'))
    matched = next((t for t in tiers if spend >= t.spend_threshold), None)
    if matched is None:
        # No active tier? Pick the lowest-rank tier as default.
        matched = list(Tier.objects.filter(is_active=True).order_by('rank'))[:1]
        matched = matched[0] if matched else None
    if matched is None:
        # No tiers defined at all — nothing to write.
        return None

    existing = UserTier.objects.filter(user=user).select_related('tier').first()

    if existing and existing.tier.rank > matched.rank:
        # Would be a downgrade — apply grace period
        age = (timezone.now() - existing.achieved_at).days
        if age < TIER_DOWNGRADE_GRACE_DAYS:
            # Skip the downgrade; just refresh the spend snapshot
            UserTier.objects.filter(user=user).update(qualifying_spend=spend)
            existing.refresh_from_db()
            return existing

    if existing is None:
        row = UserTier.objects.create(user=user, tier=matched, qualifying_spend=spend)
        _publish_tier_change(user, old_tier=None, new_tier=matched)
        return row

    if existing.tier_id != matched.id:
        old_tier = existing.tier
        existing.tier = matched
        existing.qualifying_spend = spend
        existing.achieved_at = timezone.now()  # reset grace clock
        existing.save(update_fields=['tier', 'qualifying_spend', 'achieved_at',
                                      'last_recomputed_at'])
        _publish_tier_change(user, old_tier=old_tier, new_tier=matched)
    else:
        # Same tier, just refresh spend snapshot
        UserTier.objects.filter(user=user).update(qualifying_spend=spend)

    existing.refresh_from_db()
    return existing


def _publish_tier_change(user, *, old_tier, new_tier):
    try:
        from apps.outbox.service import publish
        # Dedupe per-transition — same user moving same direction within a
        # short window gets one event. Tier names included so back-to-back
        # Bronze→Silver→Gold all produce distinct events.
        old_code = old_tier.code if old_tier else 'none'
        publish(
            topic='loyalty.tier_changed',
            payload={
                'user_id': user.id,
                'from_tier': old_tier.code if old_tier else None,
                'to_tier': new_tier.code,
                'at': timezone.now().isoformat(),
            },
            dedupe_key=f'loyalty.tier_changed:{user.id}:{old_code}->{new_tier.code}:{int(timezone.now().timestamp())}',
            ref_type='user', ref_id=str(user.id),
        )
    except Exception:
        # Tier change notification is nice-to-have — never break the tier
        # promotion over a missing outbox.
        log.debug('tier_changed publish failed', exc_info=True)
    # Invalidate the per-user benefits cache
    try:
        from apps.core.cache_kit import bump_tag
        bump_tag(f'loyalty:user:{user.id}')
    except Exception:
        pass


# ─── Benefit lookup ───────────────────────────────────────────────────────

def get_tier(user):
    """Return UserTier or None."""
    return UserTier.objects.select_related('tier').filter(user=user).first()


def get_benefits(user) -> dict:
    """Return flat {kind: value} dict of the user's current tier benefits.
    Cached per user so checkout pages don't fan out to DB."""
    try:
        from apps.core.cache_kit import cached_call, build_key
        key = build_key('loyalty_benefits', [f'loyalty:user:{user.id}'], user.id)
        return cached_call(key, lambda: _load_benefits(user),
                           ttl=300, swr_ttl=60)
    except Exception:
        return _load_benefits(user)


def _load_benefits(user) -> dict:
    ut = get_tier(user)
    if ut is None:
        return {'tier': None, 'benefits': {}}
    perks = {
        b.kind: str(b.value)
        for b in TierBenefit.objects.filter(tier=ut.tier, is_active=True)
    }
    return {
        'tier': ut.tier.code,
        'tier_name': ut.tier.name,
        'tier_rank': ut.tier.rank,
        'qualifying_spend': str(ut.qualifying_spend),
        'achieved_at': ut.achieved_at.isoformat(),
        'benefits': perks,
    }
