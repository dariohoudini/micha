"""
apps/cart/tasks.py
───────────────────

Cart-abandonment recovery (R5).

Background
──────────
Pre-R5 this task was BROKEN in three ways and shipping the bug:

  1. Wrong field names on Notification.objects.create — the model
     uses ``user=`` + ``type=``, not ``recipient=`` + ``notification_type=``.
     Every invocation TypeError'd out. The task ran every 30 minutes
     and crashed every time. Zero abandonment pings ever sent.

  2. Even if (1) hadn't crashed, the task only wrote in-app Notification
     rows — no push delivery. The whole point of abandonment recovery
     is to PUSH the user back into the app; an in-app row that they
     only see when they next open the app is a no-op.

  3. Dedup logic was logically wrong: ``already_notified`` queried for
     a notification ``created_at__gte=cutoff`` where cutoff = now -
     2h. So a user idle 5h had no notifications within the 2h window
     → re-pinged every run → spam.

This commit fixes all three by:

  • Using Notification.send() — correct field names + automatic push
    fan-out via apps.notifications.push_service.send_to_user (R5-A).
  • Tracking dedup state on Cart.last_abandonment_ping_at (R5-B
    migration) — one DB-level field, can't drift like the query-based
    approach.
  • Eligibility window [1h, 25h]: give the user 1h to checkout
    on their own before nudging (don't be annoying), don't ping carts
    older than 25h (cold leads — different campaign, not abandonment).
  • Re-ping interval: 24h. We ping at most once per day per cart.

Revenue lever
─────────────
Industry data on cart abandonment push notifications: 10-15% recovery.
On any non-trivial GMV this is the highest-ROI Celery task in the
codebase. Hence the careful test coverage.
"""
from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.utils import timezone


# ─── Tunables ─────────────────────────────────────────────────────────

# Don't nudge before this — give the buyer a chance to finish on their
# own. Pinging at the 30-second mark would feel spammy.
ABANDONMENT_MIN_AGE_HOURS = 1

# Cold lead cutoff — past this, a different (sale / restock) campaign
# is more effective than an abandonment ping. Don't burn the channel.
ABANDONMENT_MAX_AGE_HOURS = 25

# At-most-once-per-day per cart.
ABANDONMENT_REPING_HOURS = 24

# Per-run cap. Prevents one run from sending 50k pushes if the
# eligibility query unexpectedly broadens. Easy operational knob.
PER_RUN_LIMIT = 500


# ─── Public task ──────────────────────────────────────────────────────

@shared_task(name='cart.send_abandonment_nudge')
def send_abandonment_nudge() -> dict:
    """Send a push reminder to users with carts idle for 1-25 hours.

    Returns a summary dict for monitoring. The Celery result backend
    surfaces this in Flower / the admin UI so operators can confirm
    the task is actually delivering pushes (vs the pre-R5 silent-crash
    behaviour).
    """
    from apps.cart.models import Cart
    from apps.notifications.models import Notification

    now = timezone.now()
    min_age_cutoff = now - timedelta(hours=ABANDONMENT_MIN_AGE_HOURS)
    max_age_cutoff = now - timedelta(hours=ABANDONMENT_MAX_AGE_HOURS)
    reping_cutoff = now - timedelta(hours=ABANDONMENT_REPING_HOURS)

    # Eligibility:
    #   updated_at in [max_age_cutoff, min_age_cutoff]
    #     i.e., 1h–25h old
    #   AND last_abandonment_ping_at is NULL OR older than 24h
    #   AND cart has at least one item
    qs = (
        Cart.objects
        .filter(updated_at__lte=min_age_cutoff)
        .filter(updated_at__gte=max_age_cutoff)
        .filter(items__isnull=False)
        .filter(
            # last_ping_at NULL → never pinged
            # last_ping_at < cutoff → eligible to re-ping
            models_q_eligible_for_reping(reping_cutoff)
        )
        .select_related('user')
        .distinct()
    )

    summary = {'eligible': 0, 'sent': 0, 'skipped': 0, 'errors': 0}

    # Materialise the PKs first so the ``.update()`` after each send
    # doesn't shift the queryset under our iteration.
    eligible_pks = list(qs.values_list('pk', flat=True)[:PER_RUN_LIMIT])
    summary['eligible'] = len(eligible_pks)

    for pk in eligible_pks:
        try:
            cart = (
                Cart.objects
                .select_related('user')
                .prefetch_related('items')
                .filter(pk=pk)
                .first()
            )
            if cart is None:
                summary['skipped'] += 1
                continue

            # Re-check inside the loop — items may have been removed
            # between the eligibility query and now.
            item_count = cart.items.count()
            if item_count == 0:
                summary['skipped'] += 1
                continue

            user = cart.user
            if user is None or not getattr(user, 'is_active', False):
                summary['skipped'] += 1
                continue

            # Title + body. Portuguese first (target market); the FE
            # will localise based on user.language preference for the
            # in-app row, but the push payload goes out in pt-PT here
            # because the gateway can't know the locale at send time.
            title = 'Não te esqueças do teu carrinho'
            body = (
                f'Tens {item_count} produto(s) à espera. '
                'Completa a compra antes que esgote!'
            )

            # Notification.send() does:
            #   1. dedup by (user, type, reference_id) within last hour
            #   2. create in-app Notification row
            #   3. fan out push via push_service.send_to_user (R5-A)
            Notification.send(
                user=user,
                type='cart_abandonment',
                title=title,
                message=body,
                data={'cta': 'open_cart'},
                reference_id=f'cart:{cart.pk}',
            )

            # Mark this cart as pinged — even if Notification.send()
            # dedup'd internally, we update the ping timestamp so the
            # 24h re-ping window is enforced at the Cart level (the
            # source-of-truth field).
            cart.last_abandonment_ping_at = now
            cart.save(update_fields=['last_abandonment_ping_at'])
            summary['sent'] += 1

        except Exception:
            # Per-cart failure must not abort the whole run — one bad
            # row shouldn't deny the other 499 users their reminder.
            summary['errors'] += 1
            import logging
            logging.getLogger('micha.cart').warning(
                'cart abandonment ping failed for cart_id=%s', pk,
                exc_info=True,
            )

    return summary


# ─── Helpers ─────────────────────────────────────────────────────────

def models_q_eligible_for_reping(reping_cutoff):
    """Q expression: cart is eligible to be (re-)pinged.

    Pulled out so the eligibility predicate is one place to update
    if we add per-user opt-out, per-segment frequency caps, etc.
    """
    from django.db.models import Q
    return Q(last_abandonment_ping_at__isnull=True) | Q(
        last_abandonment_ping_at__lt=reping_cutoff,
    )
