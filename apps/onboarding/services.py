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

        gp.linked_user = user
        gp.carried_over_at = timezone.now()
        gp.save(update_fields=['linked_user', 'carried_over_at', 'updated_at'])
        return gp
    except Exception:
        log.exception('guest-profile carry-over failed for device %s', device_id)
        return None
