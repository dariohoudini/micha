
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

@shared_task(name='cart.send_abandonment_nudge')
def send_abandonment_nudge():
    """
    Find carts idle for 2+ hours with items.
    Send push notification nudge to buyer.
    Runs every 30 minutes via Celery beat.
    """
    from apps.cart.models import Cart
    from apps.notifications.models import Notification
    cutoff = timezone.now() - timedelta(hours=2)
    abandoned = Cart.objects.filter(
        updated_at__lte=cutoff,
        items__isnull=False,
    ).select_related('user').distinct()

    sent = 0
    for cart in abandoned:
        item_count = cart.items.count()
        if item_count == 0:
            continue
        already_notified = Notification.objects.filter(
            recipient=cart.user,
            notification_type='cart_abandonment',
            created_at__gte=cutoff,
        ).exists()
        if not already_notified:
            Notification.objects.create(
                recipient=cart.user,
                notification_type='cart_abandonment',
                title='Ainda tens produtos no carrinho',
                message=f'Tens {item_count} produto(s) à espera. Completa a tua compra antes que esgotem!',
            )
            sent += 1
    return f'Sent {sent} cart abandonment nudges'
