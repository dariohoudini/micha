"""
First-Run Experience doc — Screen 6 / CH7 / the carry-over (CH11).

The welcome / first-order coupon is the new-user hook: a real promo
record that a new account is born holding, so it is present at the very
first checkout ("the incentive is not lost by not-yet-having-an-account").

MICHA's guest cart is client-side, so the natural moment to re-scope the
incentive to the user is account creation (the gate). This module owns
the coupon definition and an idempotent grant that runs at registration.
"""
from datetime import timedelta

from django.utils import timezone


WELCOME_CODE = 'BEMVINDO15'


def ensure_welcome_coupon():
    """Get-or-create the platform welcome coupon. Idempotent — safe to
    call on every registration and from a seed command."""
    from .models import Coupon
    coupon, _ = Coupon.objects.get_or_create(
        code=WELCOME_CODE,
        defaults={
            'discount_type': 'percentage',
            'discount_value': 15,
            # Light floor so it is meaningful but reachable in AOA.
            'min_order_amount': 1000,
            # Cap the percentage so a large first order can't over-discount.
            'max_discount_amount': 10000,
            'usage_limit_per_user': 1,
            'is_active': True,
        },
    )
    return coupon


def grant_welcome_coupon(user):
    """Grant the welcome coupon to a freshly-registered user. Idempotent
    (UserCoupon is unique per user+coupon) and never raises — a promo
    hiccup must not break signup. Returns the UserCoupon or None."""
    try:
        from .models import UserCoupon
        coupon = ensure_welcome_coupon()
        # Give the new user a comfortable window to place a first order.
        if coupon.valid_until is None:
            coupon.valid_until = timezone.now() + timedelta(days=30)
            coupon.save(update_fields=['valid_until'])
        uc, _ = UserCoupon.objects.get_or_create(
            user=user, coupon=coupon, defaults={'status': 'available'},
        )
        return uc
    except Exception:
        import logging
        logging.getLogger('promotions').exception(
            'welcome coupon grant failed for user %s', getattr(user, 'id', '?'))
        return None
