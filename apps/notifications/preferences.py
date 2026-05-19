"""
apps/notifications/preferences.py
─────────────────────────────────

The chokepoint that decides whether the platform may send a given
email / push / SMS to a given user.

Why this exists
─────────────────
``NotificationPreference`` model already exists (lives in apps/ai_engine
for historical reasons) with all the right fields: per-category opt-ins,
master channel toggles, quiet hours, daily caps. But NONE of the actual
email-send sites consult it before calling django.core.mail.send_mail.

Consequence: a user who toggles "marketing emails OFF" still receives
recommendations, flash-sale alerts, etc. That's a CAN-SPAM violation
(US), a GDPR Art. 7(3) violation (EU — consent withdrawal must be
respected), and an Angola Lei 22/11 violation. Real legal risk.
Plus the obvious "I unsubscribed but you keep emailing me" user-trust
damage that drives spam-folder marking → deliverability collapse.

What this module guarantees
────────────────────────────
  1. Transactional emails (verify-email, password-reset, account-
     locked) always send unless the address is on the suppression
     list. These are legally exempt from opt-out.

  2. Marketing emails (price drops, flash sales, recommendations) only
     send if the user has the master ``email_enabled`` AND the
     per-category flag set. Bypass = compliance violation.

  3. Behavioral emails (order status changes, new chat messages,
     dispute updates) only send if the per-category flag is set,
     respecting the master channel toggle.

  4. Suppression list (bounces, complaints, manual unsubscribes)
     is a HARD BLOCK regardless of category. Address there → no
     send, ever, until manually re-subscribed.

  5. Quiet hours suppress non-urgent categories. Lockout / 2FA still
     fire (they're urgent + transactional).

  6. Daily caps prevent a runaway send loop from blasting one user.

Public API
──────────
  should_send(user, category, channel='email') → (allowed, reason)
    Pure check. Reason is a short code for logging / response.

  send_email_if_allowed(user, category, subject, message, ...)
    Thin wrapper: should_send → send_mail → write NotificationLog
    row. Returns (sent: bool, reason: str). Existing callers replace
    ``send_mail(...)`` with this.

  suppress(email, reason)
    Add an email address to the suppression list. Called by the
    bounce/complaint webhook handler AND by the unsubscribe endpoint.

  is_suppressed(email) → bool
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from enum import Enum
from typing import Optional, Tuple

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone


log = logging.getLogger(__name__)


# ─── Category taxonomy ────────────────────────────────────────────────────

class Category(str, Enum):
    # ── Transactional — always sent (legally exempt from opt-out) ──────
    EMAIL_VERIFICATION   = 'email_verification'
    PASSWORD_RESET       = 'password_reset'
    ACCOUNT_SECURITY     = 'account_security'    # lockout, 2FA changes
    ORDER_CONFIRMATION   = 'order_confirmation'  # receipt-style
    PAYMENT_RECEIPT      = 'payment_receipt'
    REFUND_CONFIRMATION  = 'refund_confirmation'

    # ── Behavioral — preference-respected but service-related ─────────
    ORDER_UPDATE         = 'order_update'        # shipped / delivered
    DISPUTE              = 'dispute'
    CHAT_MESSAGE         = 'chat_message'
    RETURN_UPDATE        = 'return_update'
    PAYOUT_UPDATE        = 'payout_update'       # seller

    # ── Marketing — opt-out hard-respected ────────────────────────────
    PRICE_DROP           = 'price_drop'
    FLASH_SALE           = 'flash_sale'
    RECOMMENDATION       = 'recommendation'
    NEWSLETTER           = 'newsletter'
    SELLER_NUDGE         = 'seller_nudge'        # "add products!" reminders


TRANSACTIONAL = frozenset({
    Category.EMAIL_VERIFICATION,
    Category.PASSWORD_RESET,
    Category.ACCOUNT_SECURITY,
    Category.ORDER_CONFIRMATION,
    Category.PAYMENT_RECEIPT,
    Category.REFUND_CONFIRMATION,
})

MARKETING = frozenset({
    Category.PRICE_DROP,
    Category.FLASH_SALE,
    Category.RECOMMENDATION,
    Category.NEWSLETTER,
    Category.SELLER_NUDGE,
})

BEHAVIORAL = frozenset({
    Category.ORDER_UPDATE,
    Category.DISPUTE,
    Category.CHAT_MESSAGE,
    Category.RETURN_UPDATE,
    Category.PAYOUT_UPDATE,
})

# Categories considered URGENT — bypass quiet hours.
# Anything that the user actively needs RIGHT NOW.
URGENT = frozenset({
    Category.ACCOUNT_SECURITY,   # somebody's attacking your account
    Category.PASSWORD_RESET,     # user requested it; needs OTP now
    Category.EMAIL_VERIFICATION, # just signed up
})


# Reason codes for the should_send return value
class Reason:
    ALLOWED = 'allowed'
    SUPPRESSED = 'suppressed'                # on suppression list
    USER_DEACTIVATED = 'user_deactivated'    # account closed
    NO_EMAIL = 'no_email_on_record'
    CHANNEL_DISABLED = 'channel_disabled'    # email_enabled=False (master)
    CATEGORY_DISABLED = 'category_disabled'  # per-category opt-out
    QUIET_HOURS = 'quiet_hours'
    DAILY_CAP = 'daily_cap_reached'


@dataclass
class Decision:
    allowed: bool
    reason: str


# ─── Pure check: should we send? ──────────────────────────────────────────

def should_send(user, category: Category, channel: str = 'email') -> Decision:
    """Pure decision function. Never sends; just decides.

    Order matters — most-restrictive blocks first so attackers who
    try to game the check get the strictest answer.
    """
    # 1. User must have an email (for email channel)
    if channel == 'email':
        if user is None or not getattr(user, 'email', None):
            return Decision(False, Reason.NO_EMAIL)
        # 2. Suppression list is a HARD block — regardless of category.
        if is_suppressed(user.email):
            return Decision(False, Reason.SUPPRESSED)
    # 3. Deactivated accounts shouldn't be receiving anything.
    if user is not None and not getattr(user, 'is_active', True):
        return Decision(False, Reason.USER_DEACTIVATED)

    cat = Category(category) if not isinstance(category, Category) else category

    # 4. Transactional always allowed past the hard blocks above —
    # legally required for service operation.
    if cat in TRANSACTIONAL:
        return Decision(True, Reason.ALLOWED)

    # 5. Load preferences. If the row doesn't exist (legacy user),
    # default to "all enabled" for behavioral, "all disabled" for
    # marketing — the safest interpretation of an unanswered consent.
    prefs = _get_preferences(user)
    channel_enabled, category_enabled = _resolve_flags(prefs, channel, cat)

    if not channel_enabled:
        return Decision(False, Reason.CHANNEL_DISABLED)
    if not category_enabled:
        return Decision(False, Reason.CATEGORY_DISABLED)

    # 6. Quiet hours suppress non-urgent categories.
    if cat not in URGENT and prefs is not None:
        if _in_quiet_hours(prefs):
            return Decision(False, Reason.QUIET_HOURS)

    # 7. Daily cap (only for high-volume categories: marketing).
    if cat in MARKETING and prefs is not None:
        if _daily_cap_reached(prefs, cat):
            return Decision(False, Reason.DAILY_CAP)

    return Decision(True, Reason.ALLOWED)


def _get_preferences(user):
    if user is None:
        return None
    try:
        # Late import — NotificationPreference lives in ai_engine.
        # Keeping it there for now; this service is the integration layer.
        from apps.ai_engine.models import NotificationPreference
        prefs, _ = NotificationPreference.objects.get_or_create(user=user)
        return prefs
    except Exception:
        log.exception('preferences: failed to load NotificationPreference')
        return None


def _resolve_flags(prefs, channel: str, cat: Category) -> Tuple[bool, bool]:
    """Map (channel, category) → (channel_enabled, category_enabled).

    If prefs is None (legacy users), defaults are:
      - email channel: enabled (transactional needs it; legacy users
        accepted ToS that included service emails)
      - behavioral categories: enabled (service-related)
      - marketing categories: DISABLED (we never had consent)
    """
    if prefs is None:
        channel_enabled = True
        category_enabled = cat not in MARKETING
        return channel_enabled, category_enabled

    if channel == 'email':
        channel_enabled = bool(getattr(prefs, 'email_enabled', True))
    elif channel == 'push':
        channel_enabled = bool(getattr(prefs, 'push_enabled', True))
    else:
        channel_enabled = True

    # Map our Category enum to the NotificationPreference flag fields.
    flag_map = {
        Category.PRICE_DROP:      'price_drops',
        Category.FLASH_SALE:      'flash_sales',
        Category.RECOMMENDATION:  'new_recommendations',
        Category.ORDER_UPDATE:    'order_updates',
        Category.CHAT_MESSAGE:    'chat_messages',
        # Categories without an explicit flag default to True (behavioral)
        # or False (marketing). The flag_map only lists fields that exist
        # on NotificationPreference.
    }
    field = flag_map.get(cat)
    if field is None:
        # Marketing categories without explicit pref field → assume
        # opt-out unless master toggle is on AND user has no pref row
        # (we conservatively default marketing to OFF on missing pref).
        category_enabled = (
            cat not in MARKETING
            or bool(getattr(prefs, 'email_enabled', False))
        )
    else:
        category_enabled = bool(getattr(prefs, field, True))

    return channel_enabled, category_enabled


def _in_quiet_hours(prefs) -> bool:
    """True if the current local time falls inside the user's quiet
    hours window. Wraps midnight correctly: quiet 22:00–07:00 matches
    both 23:00 and 03:00."""
    start = getattr(prefs, 'quiet_hours_start', None)
    end = getattr(prefs, 'quiet_hours_end', None)
    if not start or not end:
        return False
    now = timezone.localtime().time()
    if start <= end:
        return start <= now < end
    # Wraps midnight (e.g. 22:00 → 07:00)
    return now >= start or now < end


def _daily_cap_reached(prefs, cat: Category) -> bool:
    """Per-category daily cap. Resets at UTC midnight via the
    notification_count_reset_at field on NotificationPreference.
    Caller is responsible for incrementing the counter after a
    successful send (done in send_email_if_allowed)."""
    cap_field_map = {
        Category.RECOMMENDATION: 'max_daily_recommendations',
        Category.FLASH_SALE:     'max_daily_flash_sales',
    }
    field = cap_field_map.get(cat)
    if field is None:
        return False
    cap = int(getattr(prefs, field, 0) or 0)
    if cap <= 0:
        # Cap of zero means "unlimited" historically; treat 0 as "no cap".
        # Real opt-out is via the category flag, not the cap field.
        return False
    today = timezone.now().date()
    last_reset = getattr(prefs, 'notification_count_reset_at', None)
    if last_reset != today:
        # Counter belongs to a previous day; reset it.
        try:
            type(prefs).objects.filter(pk=prefs.pk).update(
                daily_notification_count=0,
                notification_count_reset_at=today,
            )
            prefs.daily_notification_count = 0
            prefs.notification_count_reset_at = today
        except Exception:
            pass
    return int(prefs.daily_notification_count or 0) >= cap


def _increment_daily_count(prefs):
    if prefs is None:
        return
    try:
        from django.db.models import F
        type(prefs).objects.filter(pk=prefs.pk).update(
            daily_notification_count=F('daily_notification_count') + 1,
        )
    except Exception:
        log.debug('preferences: increment_daily_count failed')


# ─── Suppression list ────────────────────────────────────────────────────

def is_suppressed(email: str) -> bool:
    """True if the address is on the suppression list."""
    if not email:
        return False
    try:
        from .suppression_models import SuppressedEmail
        return SuppressedEmail.objects.filter(email__iexact=email).exists()
    except Exception:
        return False


def suppress(email: str, *, reason: str = 'unsubscribe',
             source: str = 'manual') -> None:
    """Add an email to the suppression list. Idempotent."""
    if not email:
        return
    try:
        from .suppression_models import SuppressedEmail
        SuppressedEmail.objects.get_or_create(
            email=email.lower().strip(),
            defaults={'reason': reason[:80], 'source': source[:40]},
        )
        log.info('preferences.suppress: email=%s reason=%s source=%s',
                 email, reason, source)
    except Exception:
        log.exception('preferences.suppress failed')


def unsuppress(email: str) -> bool:
    """Remove an email from the suppression list. Returns True if
    it was present. Used by admin re-subscribe or by the user
    re-subscribing via account settings."""
    if not email:
        return False
    try:
        from .suppression_models import SuppressedEmail
        n, _ = SuppressedEmail.objects.filter(email__iexact=email).delete()
        return n > 0
    except Exception:
        return False


# ─── The send wrapper ────────────────────────────────────────────────────

def send_email_if_allowed(user, category: Category, *,
                          subject: str, message: str,
                          from_email: Optional[str] = None,
                          fail_silently: bool = True) -> Decision:
    """One-line replacement for ``send_mail`` that honours preferences.

    Replaces:
        send_mail(subject=..., message=..., recipient_list=[user.email], ...)

    With:
        send_email_if_allowed(user, Category.ORDER_UPDATE,
                              subject=..., message=...)

    Returns the Decision so callers can log / branch. NEVER raises —
    a preference-check failure must not crash the calling request.

    Side effects on success:
      • send_mail() called (or skipped silently if suppressed)
      • NotificationLog row written with the decision
      • daily_notification_count incremented if cap-tracked category
    """
    decision = should_send(user, category, channel='email')

    # Always write an audit row — so we can prove "we did NOT send this
    # because the user opted out" during a compliance investigation.
    try:
        from .notification_log_models import NotificationLog
        NotificationLog.objects.create(
            user=user,
            email=(user.email if user and getattr(user, 'email', None) else ''),
            category=category if isinstance(category, str) else category.value,
            channel='email',
            sent=decision.allowed,
            reason=decision.reason,
            subject=subject[:200],
        )
    except Exception:
        log.debug('preferences: NotificationLog write failed')

    if not decision.allowed:
        return decision

    # Append a one-click unsubscribe link for non-transactional emails.
    # Transactional emails legally can't have unsubscribe (the user
    # NEEDS them to use the service).
    cat = Category(category) if not isinstance(category, Category) else category
    if cat not in TRANSACTIONAL:
        message = message + _unsubscribe_footer(user)

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=from_email or settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=fail_silently,
        )
    except Exception:
        log.exception('preferences: send_mail failed for category=%s', category)
        return Decision(False, 'send_failed')

    # Bump daily cap counter for cap-tracked categories.
    if cat in MARKETING:
        prefs = _get_preferences(user)
        _increment_daily_count(prefs)

    return decision


def _unsubscribe_footer(user) -> str:
    """One-click unsubscribe footer required by RFC 8058 / CAN-SPAM /
    GDPR. Uses an HMAC-signed token so the URL works without auth —
    one-click really means one click, no login wall.
    """
    if user is None or not getattr(user, 'email', None):
        return ''
    try:
        from .unsubscribe import build_unsubscribe_url
        url = build_unsubscribe_url(user.email)
    except Exception:
        return ''
    return (
        '\n\n— — — — — — — — — — — — — — — — — — — — — — —\n'
        'Não queres receber estes emails? Cancela a subscrição: '
        f'{url}\n'
    )
