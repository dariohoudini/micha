"""
Keep `Product.search_vector` fresh.

Triggers:
  * Product post_save  → re-index (covers create + edit of any text field)
  * tags m2m_changed   → re-index (tag list changed)
"""
import logging

from django.db import connection, transaction
from django.db.models.signals import m2m_changed, post_save
from django.dispatch import receiver

from .models import Product
from .search import update_search_vector

logger = logging.getLogger(__name__)


def _safe_update(product_pk):
    if connection.vendor != 'postgresql':
        return
    try:
        product = Product.objects.select_related('category').prefetch_related('tags').get(pk=product_pk)
    except Product.DoesNotExist:
        return
    try:
        update_search_vector(product)
    except Exception:
        logger.exception(f'search_vector update failed for product {product_pk}')


@receiver(post_save, sender=Product)
def on_product_saved(sender, instance, **kwargs):
    # Defer to after-commit so tags m2m additions in the same transaction
    # are visible when we recompute.
    transaction.on_commit(lambda: _safe_update(instance.pk))


@receiver(m2m_changed, sender=Product.tags.through)
def on_product_tags_changed(sender, instance, action, **kwargs):
    if action not in ('post_add', 'post_remove', 'post_clear'):
        return
    transaction.on_commit(lambda: _safe_update(instance.pk))
