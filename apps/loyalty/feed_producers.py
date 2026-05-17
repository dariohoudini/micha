"""
apps/loyalty/feed_producers.py

Tier-perk banner — surfaces "you're X away from the next tier" for
authenticated users. Drives engagement toward more spending.
"""
from decimal import Decimal
from apps.feed.registry import register, Producer, Tile


def _tier_perk_tiles(ctx):
    user = ctx.user
    if not (user and getattr(user, 'is_authenticated', False)):
        return []
    try:
        from apps.loyalty import service as loyalty
        from apps.loyalty.models import Tier
    except Exception:
        return []

    ut = loyalty.get_tier(user)
    if ut is None:
        return []

    # "You're X AOA away from <next tier>"
    next_tier = (
        Tier.objects.filter(is_active=True, rank__gt=ut.tier.rank)
        .order_by('rank').first()
    )
    spent = Decimal(str(ut.qualifying_spend or 0))
    payload = {
        'current_tier': ut.tier.code,
        'current_tier_name': ut.tier.name,
        'qualifying_spend': str(spent),
    }
    if next_tier:
        gap = max(Decimal('0'), next_tier.spend_threshold - spent)
        payload['next_tier'] = next_tier.code
        payload['next_tier_name'] = next_tier.name
        payload['gap_aoa'] = str(gap)
        reason = f'next tier {next_tier.name}: {gap} AOA to go'
    else:
        reason = f'you are at the top tier {ut.tier.name}'

    return [
        Tile(
            id=f'tier_perk:{user.id}', kind='tier_perk',
            ref_id=str(ut.tier.id),
            # Banner-like score so it stays near the top but not above
            # personalised products
            score=0.85,
            diversity_key='banner',
            payload=payload,
            reason=reason,
        )
    ]


register(Producer(name='loyalty.tier_perk', fn=_tier_perk_tiles,
                   section='home', cache_tag='feed:user'))
