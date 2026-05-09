"""
Risk rules registry + the built-in rules.

Each rule is a callable that takes a `RiskContext` (a dict with whatever
the caller can supply) and returns a `RuleResult` — `(delta, reason)` if
the rule fires, or `None` if it doesn't.

Rules are pure functions; they do their own DB lookups when needed but
never mutate state. The scorer composes their deltas and writes ONE
RiskAssessment row.

Adding a rule
-------------
    @rule('checkout', applies_to='order')
    def my_rule(ctx):
        ...
        return 25, 'Reason text shown in audit log'

Rules registered against `applies_to='order'` run for any order-scope
assessment; `'signup'` runs for new-user assessments; `'all'` runs for
every assessment.
"""
from collections import defaultdict
from datetime import timedelta
from typing import Callable, Optional


# ── Registry ────────────────────────────────────────────────────────────
_REGISTRY: dict[str, list[tuple[str, Callable]]] = defaultdict(list)


def rule(name, *, applies_to='all'):
    """Decorator: register a rule under `name` for the given scope."""
    def deco(fn):
        _REGISTRY[applies_to].append((name, fn))
        return fn
    return deco


def rules_for(scope: str):
    return list(_REGISTRY.get('all', [])) + list(_REGISTRY.get(scope, []))


# ── Built-in rules ──────────────────────────────────────────────────────
# Numbers below tune sensitivity; expect to revisit once we have data.

@rule('new_account_high_value', applies_to='order')
def _new_account_high_value(ctx) -> Optional[tuple[int, str]]:
    """First-week account placing a >100 000 Kz order. Common scam pattern.
    Score depends on order size relative to threshold."""
    user = ctx.get('user')
    amount = float(ctx.get('order_amount', 0) or 0)
    if not user or amount <= 0:
        return None
    from django.utils import timezone
    age = timezone.now() - user.date_joined
    if age > timedelta(days=7):
        return None
    if amount >= 500000:
        return 60, 'New account (<7d) placing very large order (≥500k Kz)'
    if amount >= 100000:
        return 35, 'New account (<7d) placing large order (≥100k Kz)'
    return None


@rule('high_velocity_orders', applies_to='order')
def _high_velocity_orders(ctx) -> Optional[tuple[int, str]]:
    """N+ orders by the same user in the last 10 minutes."""
    user = ctx.get('user')
    if not user:
        return None
    from apps.orders.models import Order
    from django.utils import timezone
    recent = Order.objects.filter(
        buyer=user, created_at__gte=timezone.now() - timedelta(minutes=10),
    ).count()
    if recent >= 10:
        return 70, f'{recent} orders placed in the last 10 minutes'
    if recent >= 5:
        return 40, f'{recent} orders placed in the last 10 minutes'
    if recent >= 3:
        return 15, f'{recent} orders placed in the last 10 minutes'
    return None


@rule('shared_device_farm', applies_to='all')
def _shared_device_farm(ctx) -> Optional[tuple[int, str]]:
    """Same browser fingerprint used by multiple distinct accounts.
    Strong account-farm signal."""
    fingerprint = ctx.get('fingerprint')
    user = ctx.get('user')
    if not fingerprint or not user:
        return None
    from .models import DeviceFingerprint
    distinct_users = (
        DeviceFingerprint.objects
        .filter(fingerprint=fingerprint)
        .exclude(user=user)
        .values('user_id')
        .distinct()
        .count()
    )
    if distinct_users >= 5:
        return 80, f'Device fingerprint shared with {distinct_users} other accounts'
    if distinct_users >= 3:
        return 50, f'Device fingerprint shared with {distinct_users} other accounts'
    if distinct_users >= 1:
        return 15, f'Device fingerprint shared with {distinct_users} other account(s)'
    return None


@rule('unverified_high_value', applies_to='order')
def _unverified_high_value(ctx) -> Optional[tuple[int, str]]:
    """Unverified buyer placing a high-value order. KYC verification is the
    cheap gate — bypassing it for big-ticket purchases is suspicious."""
    user = ctx.get('user')
    amount = float(ctx.get('order_amount', 0) or 0)
    if not user or amount < 200000:
        return None
    is_verified = bool(getattr(user, 'is_verified', False) or getattr(user, 'is_phone_verified', False))
    if not is_verified:
        return 30, f'Unverified buyer placing {int(amount):,} Kz order'
    return None


@rule('cancellation_history', applies_to='order')
def _cancellation_history(ctx) -> Optional[tuple[int, str]]:
    """Buyer with > 30 % cancelled orders historically.
    Auto-refund abuse / window shopping."""
    user = ctx.get('user')
    if not user:
        return None
    from apps.orders.models import Order
    qs = Order.objects.filter(buyer=user)
    total = qs.count()
    if total < 5:
        return None
    cancelled = qs.filter(status__in=['cancelled', 'refunded']).count()
    rate = cancelled / total
    if rate >= 0.6:
        return 50, f'High cancellation rate ({int(rate*100)} % of {total} past orders)'
    if rate >= 0.3:
        return 20, f'Elevated cancellation rate ({int(rate*100)} % of {total} past orders)'
    return None


@rule('ip_velocity', applies_to='all')
def _ip_velocity(ctx) -> Optional[tuple[int, str]]:
    """Multiple distinct accounts active from the same IP in last 24h.
    Catches signup farming and credential-stuffing."""
    ip = ctx.get('ip')
    user = ctx.get('user')
    if not ip or not user:
        return None
    from .models import RiskAssessment
    distinct = (
        RiskAssessment.objects
        .filter(
            context__ip=ip,
            created_at__gte=__now() - timedelta(hours=24),
        )
        .exclude(user=user)
        .values('user_id').distinct().count()
    )
    if distinct >= 5:
        return 55, f'IP shared with {distinct} other accounts in last 24h'
    if distinct >= 2:
        return 20, f'IP shared with {distinct} other accounts in last 24h'
    return None


def __now():
    from django.utils import timezone
    return timezone.now()
