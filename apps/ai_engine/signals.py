"""
apps/ai_engine/signals.py

Auto-tracks behavioral events from existing app actions.

Launch-blocker fixes (R8)
─────────────────────────

Pre-fix, two post_save signals here logged ERRORs on EVERY save:

  • on_order_saved referenced ``instance.user`` — Order's FK is
    ``buyer``, not ``user``. Every order save AttributeError'd inside
    the try/except and dropped an ERROR line.

  • on_product_saved enqueued embed_single_product with a
    str(product_pk). ProductEmbedding.product_id is a UUIDField but
    Product uses BigAutoField (int) PKs — so the task ALWAYS fails
    with ``"X" is not a valid UUID``. Every product save = 1 ERROR
    + 1 task retry queued.

Both are caught (so they don't crash the save), but they pollute
``ERROR`` log volume and burn Celery retry capacity for no benefit.
The ai_engine schema needs reconciliation before either signal can
actually work — until then we make them safe no-ops, gated behind
settings flags so they can be flipped on once the schema is fixed.
"""
import logging
logger = logging.getLogger(__name__)


def _enabled(name: str, default: bool = False) -> bool:
    """Check a settings flag for whether an AI signal is enabled."""
    try:
        from django.conf import settings
        return bool(getattr(settings, name, default))
    except Exception:
        return default


def register_signals():
    # ── Order signal ───────────────────────────────────────────────
    try:
        from apps.orders.models import Order
        from django.db.models.signals import post_save
        from django.dispatch import receiver

        @receiver(post_save, sender=Order)
        def on_order_saved(sender, instance, created, **kwargs):
            if not created:
                return
            if not _enabled('AI_ENGINE_ORDER_SIGNAL_ENABLED', False):
                return  # disabled until taste-profile service is reconciled

            try:
                from .services import TasteProfileService, SizeRecommendationService

                # Use ``buyer`` — Order.user does not exist. The
                # pre-R8 code path crashed on this line on every order.
                user = getattr(instance, 'buyer', None)
                if user is None:
                    return

                # Order does not carry a single product/category/size
                # — those live on OrderItem. Iterate items so the
                # taste profile gets per-item granularity.
                items = list(instance.items.all()) if hasattr(instance, 'items') else []
                for item in items:
                    product = getattr(item, 'product', None)
                    if product is None:
                        continue
                    TasteProfileService.record_event(
                        user=user,
                        event_type='purchase',
                        product_id=getattr(item, 'product_id', None),
                        seller_id=getattr(instance, 'seller_id', None),
                        category=str(getattr(product, 'category', '') or ''),
                        price=getattr(item, 'unit_price', None) or instance.total,
                        source='checkout',
                    )
            except Exception as e:
                # Stay defensive — but log at WARNING (not ERROR) so
                # the AI side never spams the error budget.
                logger.warning("AI order signal best-effort failed: %s", e,
                               exc_info=True)

    except ImportError:
        pass

    # ── Product embedding signal ───────────────────────────────────
    try:
        from apps.products.models import Product
        from django.db.models.signals import post_save
        from django.dispatch import receiver

        @receiver(post_save, sender=Product)
        def on_product_saved(sender, instance, created, **kwargs):
            # PRE-R8 BUG: ProductEmbedding.product_id is a UUIDField,
            # but Product.id is a BigAutoField. Every save fired a
            # task that ALWAYS failed with ``"X" is not a valid UUID``.
            # Gate the signal behind a settings flag until the
            # embedding schema is migrated to BigIntegerField. Until
            # then this is a no-op — much better than the noisy
            # always-fails path.
            if not _enabled('AI_ENGINE_EMBEDDING_SIGNAL_ENABLED', False):
                return
            if not getattr(instance, 'is_active', False):
                return
            try:
                from .tasks import embed_single_product
                embed_single_product.apply_async(
                    args=[str(instance.id)],
                    countdown=5,
                )
            except Exception as e:
                logger.warning("AI product embedding signal failed: %s", e,
                               exc_info=True)

    except ImportError:
        pass

    # ── User taste-profile signal ──────────────────────────────────
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
                except Exception:
                    # Suppressed: profile creation is best-effort
                    # observability — never blocks user registration.
                    logger.debug("Suppressed exception", exc_info=True)

    except Exception:
        logger.debug("Suppressed exception", exc_info=True)
