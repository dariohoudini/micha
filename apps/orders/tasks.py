from celery import shared_task
from django.utils import timezone
from datetime import timedelta

@shared_task(name='orders.auto_complete_old_orders')
def auto_complete_old_orders():
    """Auto-complete orders delivered 7+ days ago with no open dispute."""
    try:
        from apps.orders.models import Order
        cutoff = timezone.now() - timedelta(days=7)
        qs = Order.objects.filter(
            status='delivered',
            updated_at__lte=cutoff,
        )
        # Exclude orders with open disputes
        try:
            from apps.trust.models import Dispute
            disputed_order_ids = Dispute.objects.filter(
                status__in=['open', 'under_review']
            ).values_list('order_id', flat=True)
            qs = qs.exclude(id__in=disputed_order_ids)
        except Exception:
            pass

        count = qs.count()
        qs.update(status='completed')

        # Release escrow for completed orders
        for order_id in qs.values_list('id', flat=True):
            release_order_escrow.delay(str(order_id))

        return f"Auto-completed {count} orders"
    except Exception as e:
        return f"Error: {e}"

@shared_task(name='orders.release_order_escrow')
def release_order_escrow(order_id):
    """Release escrow for a completed order and credit seller wallet."""
    try:
        from apps.trust.models import Escrow
        from apps.payments.models import SellerWallet, WalletTransaction
        try:
            escrow = Escrow.objects.get(order_id=order_id, status='holding')
            escrow.status = 'released'
            escrow.released_at = timezone.now()
            escrow.save()
            wallet, _ = SellerWallet.objects.get_or_create(seller=escrow.order.seller)
            # Cached counters (legacy read paths)
            from apps.payments.models import SellerWallet
            locked_wallet = SellerWallet.objects.select_for_update(of=('self',)).get(pk=wallet.pk)
            locked_wallet.balance += escrow.amount
            locked_wallet.save(update_fields=['balance', 'updated_at'])
            wallet = locked_wallet
            wallet.pending_balance = max(0, wallet.pending_balance - escrow.amount)
            wallet.save()
            WalletTransaction.objects.create(
                wallet=wallet, type='release', amount=escrow.amount,
                description=f'Escrow released for order {order_id}',
                balance_after=wallet.balance,
            )
            # Source of truth: post to ledger (idempotent on order_id)
            try:
                from apps.ledger.service import record_escrow_release
                record_escrow_release(order=escrow.order, amount=escrow.amount)
            except Exception:
                pass
        except Escrow.DoesNotExist:
            pass
        return f"Escrow released for order {order_id}"
    except Exception as e:
        return f"Error releasing escrow: {e}"

@shared_task(name='orders.send_order_confirmation')
def send_order_confirmation(order_id):
    """Send confirmation email to buyer after successful payment."""
    try:
        from apps.orders.models import Order
        from django.core.mail import send_mail
        from django.conf import settings
        order = Order.objects.select_related('buyer').get(pk=order_id)
        send_mail(
            subject=f'Order #{order_id} confirmed — MICHA',
            message=(
                f'Hi,\n\n'
                f'Your order has been confirmed!\n'
                f'Total: {order.total} AOA\n'
                f'Track it at: {settings.FRONTEND_URL}/orders/{order_id}/\n\n'
                f'Thank you for shopping with MICHA.'
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[order.buyer.email],
            fail_silently=True,
        )
        return f"Confirmation email sent for order {order_id}"
    except Exception as e:
        return f"Error: {e}"

@shared_task(name='orders.send_shipping_notification')
def send_shipping_notification(order_id):
    """Push + in-app notification when seller marks order as shipped."""
    try:
        from apps.orders.models import Order
        from apps.notifications.utils import send_notification, send_push
        order = Order.objects.select_related('buyer').get(pk=order_id)
        send_notification(
            user=order.buyer,
            type='order',
            title='Your order has shipped!',
            message=f'Order #{order_id} is on its way. Tap to track.',
            data={'order_id': str(order_id)},
        )
        if order.buyer.fcm_token:
            send_push.delay(
                token=order.buyer.fcm_token,
                title='Order shipped!',
                body=f'Order #{order_id} is on its way.',
                data={'type': 'order_shipped', 'order_id': str(order_id)},
            )
        return f"Shipping notification sent for order {order_id}"
    except Exception as e:
        return f"Error: {e}"


# ── Buyer Protection enforcement ─────────────────────────────────────────
# Add to celery beat schedule:
#     'orders.enforce_protection': {'task': 'orders.enforce_buyer_protection', 'schedule': 600.0}
# Runs every 10 minutes — picks orders whose protection_deadline_at has passed
# and emits the appropriate outbox event for the auto-action.
#
# Outbox topics:
#   order.protection_lapsed_pending    — seller never confirmed → auto-cancel + refund buyer
#   order.protection_lapsed_unshipped  — seller confirmed but never shipped → auto-cancel + refund
#   order.protection_lapsed_in_transit — shipped but not delivered after 30d → auto-confirm delivered
#   order.protection_completed         — 60d post-delivery passed → mark complete (release loyalty etc)

PROTECTION_TOPICS = {
    'awaiting_seller': 'order.protection_lapsed_pending',
    'awaiting_ship':   'order.protection_lapsed_unshipped',
    'in_transit':      'order.protection_lapsed_in_transit',
    'in_protection':   'order.protection_completed',
}


@shared_task(name='orders.enforce_buyer_protection')
def enforce_buyer_protection(batch_size=200):
    """Scan orders whose buyer-protection deadline has lapsed; emit one outbox
    event per order so the actual action is durable + retryable.

    Idempotent — uses dedupe_key keyed on (order_id, state) so the same
    lapse can't fire twice. The outbox handler advances the order state,
    which prevents further re-emission.
    """
    from django.db import transaction
    from apps.orders.models import Order
    from apps.outbox.service import publish

    now = timezone.now()
    expired = Order.objects.filter(
        protection_deadline_at__lte=now,
        protection_state__in=list(PROTECTION_TOPICS.keys()),
        is_deleted=False,
    ).only('id', 'protection_state').order_by('protection_deadline_at')[:batch_size]

    fired = 0
    for order in expired:
        topic = PROTECTION_TOPICS.get(order.protection_state)
        if not topic:
            continue
        try:
            with transaction.atomic():
                publish(
                    topic=topic,
                    payload={'order_id': str(order.id), 'from_state': order.protection_state},
                    dedupe_key=f'{topic}:{order.id}',
                    ref_type='order', ref_id=str(order.id),
                )
            try:
                from apps.telemetry.metrics import protection_lapsed
                protection_lapsed.labels(from_state=order.protection_state).inc()
            except Exception:
                pass
            fired += 1
        except Exception:
            pass
    return f'Emitted {fired} protection-lapse event(s).'
