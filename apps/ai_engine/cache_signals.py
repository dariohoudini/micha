"""
Feed cache invalidation signals.
Ensures personalised feed reflects latest user actions immediately.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


def _invalidate(user_id):
    from django.core.cache import cache
    cache.delete(f'hyper_ctx_v2:{user_id}')


@receiver(post_save, sender='wishlist.WishlistItem')
def on_wishlist_change(sender, instance, **kwargs):
    _invalidate(instance.wishlist.user_id)


@receiver(post_delete, sender='wishlist.WishlistItem')
def on_wishlist_remove(sender, instance, **kwargs):
    _invalidate(instance.wishlist.user_id)


@receiver(post_save, sender='cart.CartItem')
def on_cart_change(sender, instance, **kwargs):
    _invalidate(instance.cart.user_id)


@receiver(post_save, sender='orders.Order')
def on_order_change(sender, instance, **kwargs):
    _invalidate(instance.buyer_id)


@receiver(post_save, sender='ai_engine.BehavioralEvent')
def on_behavior_event(sender, instance, created, **kwargs):
    if created:
        _invalidate(instance.user_id)
