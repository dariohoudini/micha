"""apps/waitlist/tasks.py — Celery drivers."""
import logging
from celery import shared_task
from apps.core.task_locks import singleton_task

log = logging.getLogger(__name__)


@shared_task(name='waitlist.notify_restock', bind=True, max_retries=0)
def notify_restock_task(self, product_id):
    """Fire alerts to the FIFO front of the waitlist. Singleton per-product
    so two restock-detection signals on the same product don't double-notify."""
    from apps.waitlist.service import notify_on_restock
    from apps.products.models import Product

    @singleton_task(f'waitlist.notify:{product_id}')
    def _run():
        product = Product.objects.filter(pk=product_id).first()
        if product is None:
            return {'error': 'product_not_found'}
        return notify_on_restock(product)
    return _run()


@shared_task(name='waitlist.drain_pending')
@singleton_task('beat:waitlist.drain_pending')
def drain_pending():
    """Beat task: scan in-stock products that still have a WAITING
    waitlist and drain another batch. Belt-and-braces for the signal
    path — if a stock update happened via raw SQL (skipping signals),
    we still catch up.
    """
    from apps.waitlist.models import WaitlistEntry, WaitlistStatus
    from apps.waitlist.service import notify_on_restock
    from apps.products.models import Product
    # Find products that:
    #   (a) have quantity > 0 RIGHT NOW
    #   (b) still have at least one WAITING entry
    waiting_product_ids = list(
        WaitlistEntry.objects
        .filter(status=WaitlistStatus.WAITING)
        .values_list('product_id', flat=True)
        .distinct()[:200]
    )
    drained = 0
    for pid in waiting_product_ids:
        p = Product.objects.filter(pk=pid, quantity__gt=0).first()
        if p is None:
            continue
        notify_on_restock(p)
        drained += 1
    return {'drained_products': drained}


@shared_task(name='waitlist.cleanup_stale')
@singleton_task('beat:waitlist.cleanup_stale')
def cleanup_stale():
    from apps.waitlist.service import cleanup_stale as _cleanup
    return _cleanup()
