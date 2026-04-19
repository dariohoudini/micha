"""
apps/ai_engine/signals.py
Auto-tracks behavioral events from existing app actions.
"""
import logging
logger = logging.getLogger(__name__)


def register_signals():
    try:
        from apps.orders.models import Order
        from django.db.models.signals import post_save
        from django.dispatch import receiver

        @receiver(post_save, sender=Order)
        def on_order_saved(sender, instance, created, **kwargs):
            if not created:
                return
            try:
                from .services import TasteProfileService, SizeRecommendationService
                TasteProfileService.record_event(
                    user=instance.user,
                    event_type='purchase',
                    product_id=getattr(instance, 'product_id', None),
                    seller_id=getattr(instance, 'seller_id', None),
                    category=getattr(instance, 'category', ''),
                    price=instance.total,
                    source='checkout',
                )
                size = getattr(instance, 'size', None)
                category = getattr(instance, 'category', None)
                if size and category:
                    SizeRecommendationService.update_from_purchase(
                        user=instance.user,
                        category=str(category),
                        size=str(size),
                    )
            except Exception as e:
                logger.error(f"AI order signal failed: {e}")

    except ImportError:
        pass

    try:
        from apps.products.models import Product
        from django.db.models.signals import post_save
        from django.dispatch import receiver

        @receiver(post_save, sender=Product)
        def on_product_saved(sender, instance, created, **kwargs):
            if getattr(instance, 'is_active', False):
                try:
                    from .tasks import embed_single_product
                    embed_single_product.apply_async(
                        args=[str(instance.id)],
                        countdown=5,
                    )
                except Exception as e:
                    logger.error(f"AI product embedding signal failed: {e}")

    except ImportError:
        pass

    try:
        from django.contrib.auth import get_user_model
        from django.db.models.signals import post_save
        from django.dispatch import receiver

        User = get_user_model()

        @receiver(post_save, sender=User)
        def on_user_created(sender, instance, created, **kwargs):
            if created:
                try:
                    from .services import TasteProfileService
                    TasteProfileService.get_or_create_profile(instance)
                except Exception as e:
                    logger.error(f"AI user profile creation signal failed: {e}")

    except Exception:
        pass
