from celery import shared_task

@shared_task(name='inventory.clean_expired_reservations')
def clean_expired_reservations():
    """Release stock reserved by abandoned checkouts (expires after 15 min)."""
    try:
        from apps.inventory.models import StockReservation
        from django.utils import timezone
        expired = StockReservation.objects.filter(
            expires_at__lte=timezone.now(),
            is_active=True,
        )
        count = 0
        for res in expired:
            res.product.quantity += res.quantity
            res.product.save(update_fields=['quantity'])
            res.is_active = False
            res.save(update_fields=['is_active'])
            count += 1
        return f"Released {count} expired stock reservations"
    except Exception as e:
        return f"Error: {e}"

@shared_task(name='inventory.send_low_stock_alerts')
def send_low_stock_alerts():
    """Alert sellers when product stock falls to or below threshold."""
    try:
        from apps.products.models import Product
        from apps.notifications.utils import send_notification, send_push
        low_stock = Product.objects.filter(
            is_active=True,
            quantity__gt=0,
            quantity__lte=5,
        ).select_related('store__owner')
        count = 0
        for product in low_stock:
            seller = product.store.owner
            send_notification(
                user=seller,
                type='system',
                title='Low stock alert',
                message=f'"{product.title}" only has {product.quantity} left. Restock soon!',
                data={'product_id': product.id},
            )
            if seller.fcm_token:
                send_push.delay(
                    token=seller.fcm_token,
                    title='Low stock!',
                    body=f'{product.title} — only {product.quantity} left',
                    data={'type': 'low_stock', 'product_id': str(product.id)},
                )
            count += 1
        return f"Sent {count} low stock alerts"
    except Exception as e:
        return f"Error: {e}"
