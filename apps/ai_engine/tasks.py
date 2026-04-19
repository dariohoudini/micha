"""
apps/ai_engine/tasks.py — MICHA Express AI Engine v2

Celery task hierarchy:
  ai_fast   → taste profile updates (< 10s after event)
  ai_medium → recommendation rebuilds, price checks, notifications
  ai_heavy  → nightly embedding computation (OpenAI API calls)

Cost tracking:
  OpenAI text-embedding-3-small: $0.02 per 1M tokens
  GPT-4o-mini: $0.15/1M input + $0.60/1M output tokens
  Estimated monthly cost at 10K users: ~$8-15/month
"""
import logging
from celery import shared_task
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


# ── Fast queue — profile updates ──────────────────────────────────────────────

@shared_task(
    name='ai_engine.update_taste_profile_incremental',
    bind=True, max_retries=3, default_retry_delay=10,
    queue='ai_fast', acks_late=True,
)
def update_taste_profile_incremental(self, user_id: str, event_id: str):
    """
    Incremental taste profile update from a single behavioral event.
    Fires within seconds of user action.
    """
    try:
        from .services import TasteProfileService
        TasteProfileService.compute_profile_update(user_id, event_id)
    except Exception as exc:
        logger.error(f"Incremental profile update failed: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    name='ai_engine.embed_user_profile',
    bind=True, max_retries=2, default_retry_delay=30,
    queue='ai_fast',
)
def embed_user_profile(self, user_id: str):
    """
    (Re)generates OpenAI embedding for user taste profile.
    Called after quiz completion and every 10 significant events.
    Cost: ~$0.000004 per call (text-embedding-3-small)
    """
    try:
        from django.contrib.auth import get_user_model
        from .services import EmbeddingService, TasteProfileService

        User = get_user_model()
        user = User.objects.get(id=user_id)
        profile = TasteProfileService.get_or_create_profile(user)

        text = profile.get_embedding_input_text()
        if not text.strip():
            return

        embedding = EmbeddingService.embed_text(text)
        if embedding:
            profile.embedding = embedding
            profile.embedding_text = text
            profile.embedding_updated_at = timezone.now()
            profile.save(update_fields=['embedding', 'embedding_text', 'embedding_updated_at'])
            logger.info(f"User {user_id} profile embedding updated ({len(embedding)} dims)")

    except Exception as exc:
        logger.error(f"User embedding failed for {user_id}: {exc}")
        raise self.retry(exc=exc)


# ── Medium queue — recommendations ────────────────────────────────────────────

@shared_task(
    name='ai_engine.rebuild_user_recommendations',
    bind=True, max_retries=2, default_retry_delay=60,
    queue='ai_medium', acks_late=True,
)
def rebuild_user_recommendations(self, user_id: str):
    """
    Rebuilds home feed recommendation cache for one user.
    Triggered after significant behavioral events.
    """
    try:
        from django.contrib.auth import get_user_model
        from .services import RecommendationService

        User = get_user_model()
        user = User.objects.get(id=user_id)
        cache = RecommendationService.compute_home_feed(user)
        logger.info(f"Recommendations rebuilt for {user_id}: {len(cache.product_ids)} products")

    except Exception as exc:
        logger.error(f"Recommendation rebuild failed for {user_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    name='ai_engine.compute_single_product_similarity',
    bind=True, max_retries=2,
    queue='ai_medium',
)
def compute_single_product_similarity(self, product_id: str):
    """Computes similar products for one product on-demand (cache miss)."""
    try:
        from .services import RecommendationService
        import uuid
        RecommendationService.compute_similar_products(uuid.UUID(product_id))
    except Exception as exc:
        logger.error(f"Product similarity failed for {product_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    name='ai_engine.refresh_stale_recommendation_caches',
    queue='ai_medium',
)
def refresh_stale_recommendation_caches():
    """
    Every 6 hours: refresh recommendation caches expiring within 1 hour.
    Prioritises users who haven't been refreshed longest.
    """
    from django.contrib.auth import get_user_model
    from .models import RecommendationCache

    User = get_user_model()
    stale_threshold = timezone.now() + timedelta(hours=1)

    fresh_user_ids = RecommendationCache.objects.filter(
        feed_type='home_feed',
        expires_at__gt=stale_threshold,
    ).values_list('user_id', flat=True)

    stale_users = User.objects.filter(
        is_active=True,
    ).exclude(id__in=fresh_user_ids)[:500]  # Max 500 per run

    count = 0
    for user in stale_users:
        rebuild_user_recommendations.delay(str(user.id))
        count += 1

    logger.info(f"Queued recommendation refresh for {count} users")


@shared_task(
    name='ai_engine.check_all_price_drops',
    queue='ai_medium',
)
def check_all_price_drops():
    """
    Daily: checks all active price watches.
    Runs at 09:00 WAT when users are awake.
    """
    from .models import PriceDropAlert
    from .services import PriceDropService

    watching = PriceDropAlert.objects.filter(
        status='watching'
    ).select_related('user', 'user__ai_notification_preferences')

    triggered = 0
    for alert in watching:
        try:
            from apps.products.models import Product
            product = Product.objects.get(id=alert.product_id)
            if alert.should_trigger(float(product.price)):
                prefs = getattr(alert.user, 'ai_notification_preferences', None)
                if prefs and prefs.can_notify('price_drop'):
                    PriceDropService._send_notification(alert, float(product.price))
                    alert.status = 'triggered'
                    alert.triggered_at = timezone.now()
                    alert.times_triggered += 1
                    alert.save()
                    triggered += 1
        except Exception as e:
            logger.debug(f"Price check skipped: {e}")

    logger.info(f"Price drop check: {triggered} alerts triggered")


@shared_task(
    name='ai_engine.log_search_query',
    queue='ai_fast',
)
def log_search_query(raw: str, parsed: dict, user_id: str = None):
    """Async search query logging."""
    from .models import SearchQuery
    try:
        from django.contrib.auth import get_user_model
        user = None
        if user_id:
            User = get_user_model()
            user = User.objects.filter(id=user_id).first()

        SearchQuery.objects.create(
            user=user,
            raw_query=raw[:500],
            normalized_query=raw.lower().strip()[:500],
            detected_language=parsed.get('language', 'pt'),
            parsed_intent=parsed,
            detected_category=parsed.get('category', ''),
            detected_price_max=parsed.get('price_max'),
            detected_price_min=parsed.get('price_min'),
            detected_occasion=parsed.get('occasion', ''),
            detected_style=parsed.get('style', ''),
        )
    except Exception as e:
        logger.debug(f"Search log failed: {e}")


# ── Heavy queue — nightly embedding computation ───────────────────────────────

@shared_task(
    name='ai_engine.embed_single_product',
    bind=True, max_retries=2, default_retry_delay=60,
    queue='ai_heavy',
)
def embed_single_product(self, product_id: str):
    """
    Generates OpenAI embedding for one product.
    Called when product is approved by admin.
    Cost: ~$0.000004 per product (text-embedding-3-small)
    """
    try:
        from .models import ProductEmbedding
        from .services import EmbeddingService

        try:
            from apps.products.models import Product
            product = Product.objects.get(id=product_id)
        except Exception:
            logger.warning(f"Product {product_id} not found — skipping embedding")
            return

        emb_obj, _ = ProductEmbedding.objects.get_or_create(product_id=product_id)

        # Build embedding text
        tags = getattr(product, 'tags', []) or []
        if hasattr(tags, 'values_list'):
            tags = list(tags.values_list('name', flat=True))

        text = (
            f"{product.name}. "
            f"Category: {product.category}. "
            f"Price: {product.price} Kz. "
            f"Tags: {', '.join(tags)}. "
            f"{(product.description or '')[:500]}"
        )

        embedding = EmbeddingService.embed_text(text)
        if not embedding:
            return

        emb_obj.embedding = embedding
        emb_obj.embedding_text = text[:1000]
        emb_obj.name = product.name[:255]
        emb_obj.category = str(product.category)
        emb_obj.price = product.price
        emb_obj.tags = tags[:20]
        emb_obj.seller_id = getattr(product, 'seller_id', None)
        emb_obj.is_express = getattr(product, 'is_express', False)
        emb_obj.is_active = getattr(product, 'is_active', True)
        emb_obj.total_sales = getattr(product, 'total_sales', 0) or 0
        emb_obj.total_views = getattr(product, 'total_views', 0) or 0
        emb_obj.avg_rating = float(getattr(product, 'avg_rating', 0) or 0)
        emb_obj.popularity_score = _compute_popularity(product)
        emb_obj.save()

        # Trigger similarity computation
        compute_single_product_similarity.apply_async(
            args=[product_id], countdown=60
        )
        logger.info(f"Product {product_id} embedded successfully")

    except Exception as exc:
        logger.error(f"Product embedding failed for {product_id}: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    name='ai_engine.embed_all_products_nightly',
    queue='ai_heavy',
)
def embed_all_products_nightly():
    """
    Nightly: re-embeds all active products.
    Updates popularity scores and re-triggers similarity computation.
    Scheduled: 02:00 WAT daily.
    """
    try:
        from apps.products.models import Product
        active = Product.objects.filter(is_active=True).values_list('id', flat=True)
        count = 0
        for pid in active:
            embed_single_product.apply_async(args=[str(pid)], countdown=count * 2)
            count += 1
        logger.info(f"Nightly embedding queued for {count} products")
    except ImportError:
        logger.warning("Products app not available")


@shared_task(
    name='ai_engine.compute_all_similar_products_nightly',
    queue='ai_heavy',
)
def compute_all_similar_products_nightly():
    """
    Nightly: computes product-to-product similarity for all active products.
    Runs after embed_all_products_nightly.
    Scheduled: 03:00 WAT daily.
    """
    from .models import ProductEmbedding
    from .services import RecommendationService

    products = ProductEmbedding.objects.filter(is_active=True)
    count = 0
    for prod in products:
        RecommendationService.compute_similar_products(prod.product_id)
        count += 1

    logger.info(f"Product similarity computed for {count} products")


# ── Notification tasks ────────────────────────────────────────────────────────

@shared_task(
    name='ai_engine.send_push_notification',
    bind=True, max_retries=3, default_retry_delay=30,
    queue='ai_medium',
)
def send_push_notification(self, user_id: str, title: str, body: str, data: dict = None):
    """
    Sends push notification via FCM/APNS.
    Plug in your push provider here (Firebase, OneSignal, etc.)
    """
    try:
        logger.info(f"Push notification to {user_id}: {title}")
        # TODO: Wire to FCM/OneSignal when push service is configured
        # from firebase_admin import messaging
        # message = messaging.Message(...)
        # messaging.send(message)
    except Exception as exc:
        logger.error(f"Push notification failed: {exc}")
        raise self.retry(exc=exc)


@shared_task(
    name='ai_engine.send_flash_sale_notifications',
    queue='ai_medium',
)
def send_flash_sale_notifications(user_ids: list, flash_sale_id: str,
                                   category: str, discount_pct: int):
    """Sends targeted flash sale notifications."""
    for user_id in user_ids:
        send_push_notification.delay(
            user_id=user_id,
            title=f"Flash Sale! -{discount_pct}% em {category} ⚡",
            body="Oferta por tempo limitado. Aproveite agora!",
            data={
                'type': 'flash_sale',
                'flash_sale_id': flash_sale_id,
                'category': category,
                'discount_pct': discount_pct,
            }
        )
    logger.info(f"Flash sale notifications sent to {len(user_ids)} users")


# ── Helper ────────────────────────────────────────────────────────────────────

def _compute_popularity(product) -> float:
    """0-1 popularity score from product metrics."""
    try:
        sales = float(getattr(product, 'total_sales', 0) or 0)
        views = float(getattr(product, 'total_views', 0) or 0)
        rating = float(getattr(product, 'avg_rating', 0) or 0)
        sales_score = min(sales / 500, 1.0)
        views_score = min(views / 5000, 1.0)
        rating_score = rating / 5.0
        return round(sales_score * 0.5 + views_score * 0.3 + rating_score * 0.2, 4)
    except Exception:
        return 0.0
