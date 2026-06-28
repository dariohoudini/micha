from celery import shared_task
from django.utils import timezone
from datetime import timedelta
from apps.core.task_locks import singleton_task

@shared_task(name='orders.auto_complete_old_orders')
@singleton_task('beat:orders.auto_complete_old_orders')
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
@singleton_task('beat:orders.enforce_buyer_protection')
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


@shared_task(name='orders.enforce_return_deadlines')
@singleton_task('beat:orders.enforce_return_deadlines')
def enforce_return_deadlines(batch_size: int = 200):
    """SLA enforcement for returns.

    Two deadline classes:
      • Seller didn't respond within SELLER_RESPONSE_HOURS to a 'pending'
        return  → auto_approve (favours the buyer; flags the seller for ops).
      • Buyer didn't act within PICKUP_DEADLINE_DAYS of an 'approved' return
        → cancel (so stock isn't held forever).
    """
    from apps.orders.return_models import ReturnRequest, ReturnStatus
    from apps.orders import return_service

    now = timezone.now()
    auto_approved = 0
    cancelled = 0

    # Seller SLA misses → auto-approve
    stale_pending = (
        ReturnRequest.objects
        .filter(status=ReturnStatus.PENDING,
                seller_response_deadline_at__lte=now)
        .order_by('seller_response_deadline_at')[:batch_size]
    )
    for rr in stale_pending:
        try:
            return_service.system_auto_approve(rr)
            auto_approved += 1
        except Exception:
            pass

    # Buyer pickup window lapsed → cancel
    stale_approved = (
        ReturnRequest.objects
        .filter(status__in=(ReturnStatus.APPROVED, ReturnStatus.AUTO_APPROVED),
                pickup_deadline_at__lte=now)
        .order_by('pickup_deadline_at')[:batch_size]
    )
    for rr in stale_approved:
        try:
            return_service.system_cancel_for_pickup_timeout(rr)
            cancelled += 1
        except Exception:
            pass

    return {'auto_approved': auto_approved, 'cancelled': cancelled}


@shared_task(name='orders.auto_confirm_delivered')
def auto_confirm_delivered():
    """User Process Flow §10.6 — buyer auto-confirms after 7 days.

    Runs daily. For every order in ``delivered`` status whose
    delivered_at is older than 7 days, mark as ``completed`` so the
    seller payout proceeds. Logs each transition to UserEvent.
    """
    from datetime import timedelta
    from django.utils import timezone
    from .models import Order
    from apps.analytics.models import UserEvent

    cutoff = timezone.now() - timedelta(days=7)
    qs = Order.objects.filter(status='delivered', delivered_at__lte=cutoff)
    n = 0
    for order in qs.iterator():
        try:
            order.status = 'completed'
            order.save(update_fields=['status'])
            UserEvent.objects.create(
                user=order.buyer, event='order.auto_confirmed',
                properties={'order_id': str(order.id), 'reason': 'timeout_7d'},
            )
            n += 1
        except Exception:
            pass
    return {'auto_confirmed': n}


# ─── AliExpress Technical Engineering Workflow CH 9.3 + CH 10.1 ────

@shared_task(name='orders.expire_unpaid_orders')
def expire_unpaid_orders():
    """Cron: cancel pending-payment orders that exceed the per-method
    TTL. Spec §9.3:
       card / paypal / klarna     → 1 hour
       atm_reference / bank_wire   → 48 hours
       mobile money (multicaixa / unitel) → 15 minutes
    Inventory is restored via the cancellation handler.
    """
    from datetime import timedelta as _td
    from django.utils import timezone as _tz
    from django.db.models import Q
    from .models import Order
    from .state_machine import transition
    now = _tz.now()
    fast   = ('multicaixa', 'unitel_money', 'mobile_money')
    medium = ('card', 'googlepay', 'applepay', 'paypal', 'klarna', 'afterpay', 'alipay')
    slow   = ('bank_wire', 'atm_reference', 'cod')
    # Order.payment is a OneToOne reverse relation to Payment
    # (apps/orders/models.py). The method field lives there; orders
    # without a Payment row default to the slowest TTL so we don't
    # kill a legit order mid-creation.
    qs = Order.objects.filter(status='pending', payment_status='pending').filter(
        Q(payment__method__in=fast,   created_at__lt=now - _td(minutes=15)) |
        Q(payment__method__in=medium, created_at__lt=now - _td(hours=1)) |
        Q(payment__method__in=slow,   created_at__lt=now - _td(hours=48)) |
        Q(payment__isnull=True,       created_at__lt=now - _td(hours=48))
    )[:500]
    expired = 0
    for o in qs:
        try:
            transition(o, 'payment_failed', actor=None, note='Payment TTL expired',
                       source='expire_unpaid_orders_cron')
            try:
                from apps.analytics.models import UserEvent
                UserEvent.objects.create(user=o.buyer, event='order.payment_expired',
                    properties={'order_id': str(o.id), 'method': o.payment_method})
            except Exception:
                pass
            expired += 1
        except Exception:
            pass
    return {'expired': expired}


@shared_task(name='orders.check_seller_shipping_deadlines')
def check_seller_shipping_deadlines():
    """Cron: warn sellers whose confirmed orders exceed processing-time
    SLA, and auto-cancel after a 24h grace if still unshipped. Spec
    §10.1. Compensation: restore inventory + initiate refund + bump
    seller's auto-cancel rate metric (gates future Choice eligibility).
    """
    from datetime import timedelta as _td
    from django.utils import timezone as _tz
    from .models import Order
    from .state_machine import transition
    now = _tz.now()
    warned = 0
    cancelled = 0

    # Stage 1: warn newly overdue.
    overdue = Order.objects.filter(status='confirmed', shipping_overdue_notified=False)[:500]
    for o in overdue:
        # Each order has processing_time_days stored on Product; fall back to 3.
        processing_days = 3
        try:
            first_item = o.items.first()
            processing_days = int(getattr(first_item.product, 'processing_time_days', None) or 3)
        except Exception:
            pass
        deadline = (o.confirmed_at or o.created_at) + _td(days=processing_days)
        if now < deadline:
            continue
        # Mark warned + push to seller. We rely on the existing
        # notification dispatcher (apps.notifications) — best-effort.
        try:
            o.shipping_overdue_notified = True
            o.overdue_notified_at = now
            o.save(update_fields=['shipping_overdue_notified', 'overdue_notified_at'])
            warned += 1
            try:
                from apps.analytics.models import UserEvent
                UserEvent.objects.create(user=o.seller, event='seller.ship_deadline_missed',
                    properties={'order_id': str(o.id), 'days_overdue': (now - deadline).days})
            except Exception:
                pass
        except Exception:
            pass

    # Stage 2: 24h after notification with no shipment → auto-cancel.
    escalate = Order.objects.filter(
        status='confirmed', shipping_overdue_notified=True,
        overdue_notified_at__lt=now - _td(hours=24),
    )[:500]
    for o in escalate:
        try:
            transition(o, 'cancelled', actor=None,
                       note='Auto-cancelled: seller failed to ship within SLA',
                       source='seller_sla_escalation_cron')
            # Inventory restore is handled by the cancellation handler.
            try:
                from apps.analytics.models import UserEvent
                UserEvent.objects.create(user=o.buyer, event='order.auto_cancelled_seller_failed',
                    properties={'order_id': str(o.id), 'seller_id': o.seller_id})
            except Exception:
                pass
            cancelled += 1
        except Exception:
            pass
    return {'warned': warned, 'auto_cancelled': cancelled}
