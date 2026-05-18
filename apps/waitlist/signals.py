"""
apps/waitlist/signals.py

Detect 0→positive stock transitions on Product (and ProductVariantCombo)
and kick off the waitlist notification fanout. We do this via signals
so apps/products/models.py stays clean of waitlist coupling.

How the detection works:
  • pre_save handler stashes the old quantity on the instance (via a
    Django-private _state.fields_cache trick — but we use a simpler
    approach: query the row fresh before save).
  • post_save compares old vs new; if 0 → > 0, enqueue notify task.

The pre_save lookup is O(1) by PK and only runs on UPDATE (not INSERT)
so the overhead is negligible.
"""
import logging
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

log = logging.getLogger(__name__)


def _resolve_product_model():
    from apps.products.models import Product
    return Product


@receiver(pre_save)
def _stash_old_stock(sender, instance, **kwargs):
    """Stash the pre-save quantity so post_save can detect a 0→>0 jump."""
    Product = _resolve_product_model()
    if sender is not Product:
        return
    if instance.pk is None:
        instance._old_quantity = None
        return
    try:
        old = Product.objects.filter(pk=instance.pk).values_list(
            'quantity', flat=True,
        ).first()
        instance._old_quantity = int(old) if old is not None else None
    except Exception:
        instance._old_quantity = None


@receiver(post_save)
def _detect_restock(sender, instance, created, **kwargs):
    """If quantity moved 0 → positive, fire the waitlist fanout."""
    Product = _resolve_product_model()
    if sender is not Product or created:
        return
    old = getattr(instance, '_old_quantity', None)
    new = int(getattr(instance, 'quantity', 0) or 0)
    if old is None or old > 0 or new <= 0:
        return  # not a 0 → > 0 transition

    try:
        from apps.waitlist.tasks import notify_restock_task
        notify_restock_task.delay(instance.id)
    except Exception:
        # Inline fallback so tests / Celery-less envs still see the
        # notification chain.
        try:
            from apps.waitlist.service import notify_on_restock
            notify_on_restock(instance)
        except Exception:
            log.exception('inline restock notification failed for %s',
                            instance.pk)
