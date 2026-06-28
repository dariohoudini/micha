"""
Promotions signals — User Process Flow §7.6 + §12.3.

Hooks Product.quantity edge transitions to fan out:
  • Stock-back-in-stock pushes to all waiting StockNotification rows.
  • Notification rows flipped to ``is_notified=True`` so the same
    user isn't paged twice on the next stock dip-and-recover.

We use a pre_save snapshot to detect the 0→positive transition
because Django's post_save only gives us the new state.
"""
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone

# Lazy imports inside handlers to avoid app-load cycle.


@receiver(pre_save, sender='products.Product')
def _snapshot_old_qty(sender, instance, **kwargs):
    if not instance.pk:
        instance._old_quantity = None
        return
    try:
        instance._old_quantity = sender.objects.only('quantity').get(pk=instance.pk).quantity
    except sender.DoesNotExist:
        instance._old_quantity = None


@receiver(post_save, sender='products.Product')
def _stock_back_notify(sender, instance, created, **kwargs):
    if created:
        return
    old = getattr(instance, '_old_quantity', None)
    new = getattr(instance, 'quantity', 0) or 0
    if old in (None,) or old > 0 or new <= 0:
        return  # not a 0 → >0 transition
    # Fan out: persist the notification on each row + log to UserEvent.
    try:
        from .models import StockNotification
        from apps.analytics.models import UserEvent
        rows = StockNotification.objects.filter(
            product=instance, is_notified=False,
        ).select_related('user')
        now = timezone.now()
        # bulk update to avoid N round-trips for hot products.
        ids = list(rows.values_list('id', flat=True))
        if not ids:
            return
        StockNotification.objects.filter(id__in=ids).update(
            is_notified=True, notified_at=now,
        )
        UserEvent.objects.bulk_create([
            UserEvent(
                user_id=r['user_id'],
                event='stock.notify_fired',
                properties={'product_id': instance.id, 'sku_id': r.get('sku_id', '')},
            )
            for r in StockNotification.objects.filter(id__in=ids).values('user_id', 'sku_id')
        ])
    except Exception:
        # Never let a notification failure block a stock update.
        import logging
        logging.getLogger('micha').exception('stock.notify_fan_out_failed')
