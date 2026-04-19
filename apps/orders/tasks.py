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
        from apps.payments.models import SellerWallet, WalletTransaction, EarningsHold
        try:
            escrow = Escrow.objects.get(order_id=order_id, status='holding')
            escrow.status = 'released'
            escrow.released_at = timezone.now()
            escrow.save()
            wallet, _ = SellerWallet.objects.get_or_create(seller=escrow.order.seller)
            wallet.balance += escrow.amount
            wallet.pending_balance = max(0, wallet.pending_balance - escrow.amount)
            wallet.save()
            WalletTransaction.objects.create(
                wallet=wallet, type='release', amount=escrow.amount,
                description=f'Escrow released for order {order_id}',
                balance_after=wallet.balance,
            )
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
