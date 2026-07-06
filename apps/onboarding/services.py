"""
First-Run doc CH11 — the guest profile → account carry-over.

At signup everything the guest built becomes the account: locale
(language/currency), interests (the personalisation seed), and
attribution — copied to the user by linking the guest device to the
new user_id. Atomic + idempotent (a second call is a no-op once the
profile is linked). The welcome coupon is granted separately at
registration (apps.promotions.welcome).
"""
import logging

from django.utils import timezone

log = logging.getLogger('onboarding')

# Map the guest locale language to the User.language choices ('pt'/'en').
_LANG_MAP = {
    'pt-AO': 'pt', 'pt': 'pt', 'pt-PT': 'pt', 'pt-BR': 'pt',
    'en': 'en', 'en-US': 'en', 'en-GB': 'en',
}


def carry_over_guest_profile(user, device_id):
    """Copy a guest profile onto a freshly-registered user. Never raises
    — a carry-over hiccup must not break signup. Returns the linked
    GuestProfile or None."""
    if not device_id:
        return None
    try:
        from .models import GuestProfile
        gp = GuestProfile.objects.filter(device_id=device_id).first()
        if gp is None or gp.linked_user_id is not None:
            return gp  # unknown device, or already carried over → no-op

        locale = gp.locale or {}
        updates = []
        lang = _LANG_MAP.get(locale.get('language'))
        if lang and getattr(user, 'language', None) != lang:
            user.language = lang
            updates.append('language')
        currency = locale.get('currency')
        if currency and getattr(user, 'currency', None) != currency:
            user.currency = currency
            updates.append('currency')
        if updates:
            user.save(update_fields=updates)

        # Seed personalisation from the guest interests (best-effort —
        # reuses the taste-profile engine; a brand-new account then
        # skips the cold-start).
        if gp.interests:
            try:
                from apps.ai_engine.services import TasteProfileService
                TasteProfileService.update_from_onboarding(
                    user=user,
                    quiz_data={'categories': gp.interests},
                )
            except Exception:
                log.debug('interest carry-over seeding skipped', exc_info=True)

        # Merge the SERVER-SIDE guest cart into the account cart (doc
        # CH9/CH12 semantics: clamp to stock, store the CURRENT price,
        # sum into an existing row). This is what makes the cart survive
        # a reinstall or a second device — the localStorage path
        # (/cart/merge/) still runs post-login and surfaces conflicts.
        _merge_guest_cart(user, gp)

        gp.linked_user = user
        gp.carried_over_at = timezone.now()
        gp.save(update_fields=['linked_user', 'carried_over_at', 'updated_at'])
        return gp
    except Exception:
        log.exception('guest-profile carry-over failed for device %s', device_id)
        return None


def _merge_guest_cart(user, guest_profile):
    """Fold the guest cart snapshot into the user's Cart, then retire
    the snapshot. Same validation rules as /cart/merge/: dead products
    skipped, quantity clamped to available stock, current price stored."""
    snapshot = list(guest_profile.cart_items.all())
    if not snapshot:
        return
    try:
        from apps.cart.models import Cart, CartItem
        from apps.inventory.models import ProductVariantCombo
        from apps.products.models import Product

        cart, _ = Cart.objects.get_or_create(user=user)
        for row in snapshot:
            try:
                product = Product.objects.filter(
                    pk=row.product_id, is_active=True, is_archived=False,
                ).first()
                if product is None:
                    continue
                combo = None
                if row.variant_combo_id:
                    combo = ProductVariantCombo.objects.filter(
                        pk=row.variant_combo_id, product=product,
                        is_active=True,
                    ).first()
                    if combo is None:
                        continue
                available = combo.quantity if combo else product.quantity
                if available <= 0:
                    continue
                existing = CartItem.objects.filter(
                    cart=cart, product=product, variant_combo=combo,
                ).first()
                if existing is not None:
                    existing.quantity = min(existing.quantity + row.quantity,
                                            available)
                    existing.save(update_fields=['quantity', 'updated_at'])
                else:
                    CartItem.objects.create(
                        cart=cart, product=product, variant_combo=combo,
                        quantity=min(row.quantity, available),
                        price_at_add=combo.price if combo else product.price,
                    )
            except Exception:
                continue
        # Retired: the account cart is now the truth. This also makes the
        # carry-over idempotent for the cart (a retried signup finds an
        # empty snapshot).
        guest_profile.cart_items.all().delete()
    except Exception:
        log.exception('guest cart merge failed for guest %s', guest_profile.pk)
