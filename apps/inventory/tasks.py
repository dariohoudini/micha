from celery import shared_task

@shared_task(name='inventory.clean_expired_reservations')
def clean_expired_reservations():
    """Release stock reserved by abandoned checkouts.

    Delegates to inventory.service.sweep_expired so the release path
    is identical to the on-demand release_reservation() path:
    select_for_update on both the reservation row and the target
    Product/ProductVariantCombo row. The old in-task implementation
    read res.product.quantity and saved without locking, which raced
    with concurrent reserves and lost stock-restore increments.

    Also: the prior version was variant-blind — it always restored
    Product.quantity, never ProductVariantCombo.quantity. Variant
    reservations expired without giving the variant stock back.
    """
    from .service import sweep_expired
    released = sweep_expired(limit=500)
    return f"Released {released} expired stock reservations"

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
