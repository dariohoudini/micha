"""
Product signals.

Triggers:
  * Product post_save     → re-index search_vector (Postgres only)
                          → assign product_group if not set (SPU/SKU model)
  * tags m2m_changed      → re-index search_vector
"""
import logging

from django.db import connection, transaction
from django.db.models.signals import m2m_changed, post_save, pre_save
from django.dispatch import receiver

from .models import Product, ProductGroup
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


@receiver(pre_save, sender=Product)
def assign_product_group(sender, instance, **kwargs):
    """SPU/SKU plumbing: every Product gets canonicalised to a ProductGroup
    keyed by (title, brand, category). Sellers listing the same item for
    sale all share the group. Recomputes the group when the title or brand
    changes (rare but cheap).
    """
    try:
        # Existing product whose discriminator changed → re-canonicalise
        if instance.pk:
            try:
                old = Product.objects.only('title', 'brand', 'category_id', 'product_group_id').get(pk=instance.pk)
            except Product.DoesNotExist:
                old = None
            if old and (old.title == instance.title and old.brand == (instance.brand or '')
                        and old.category_id == instance.category_id and instance.product_group_id):
                return  # nothing relevant changed
        group, _ = ProductGroup.find_or_create(
            title=instance.title,
            brand=instance.brand or '',
            category=instance.category,
        )
        instance.product_group = group
    except Exception:
        # Auto-grouping must never block a product save
        logger.exception('assign_product_group failed; product saved without group')


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
