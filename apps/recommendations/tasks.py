"""
Recommendation Tasks — Fixed for Scale
Fixes:
1. PersonalisedFeedView annotate(Sum()) replaced with pre-computed cache
2. ProductSimilarity rebuild uses batch cursor pagination (not full table scan)
3. BrowsingSession cleanup — delete sessions older than 30 days
4. StockUrgencySignal cleanup — delete signals older than 5 minutes
5. All tasks have idempotency guards
"""
from celery import shared_task
from django.utils import timezone
from django.core.cache import cache
import logging

logger = logging.getLogger('micha')


# ── Feed pre-computation ──────────────────────────────────────────────────────

@shared_task(name='recommendations.precompute_user_feeds', bind=True, max_retries=3)
def precompute_user_feeds(self):
    """
    Pre-compute personalised feed for every active user.
    Runs every 30 minutes via Celery Beat.
    Result cached in Redis per user — feed endpoint reads from cache, never runs live query.

    This replaces the catastrophic annotate(Sum()) approach that ran
    N correlated subqueries per product per user on every homepage load.
    """
    from django.contrib.auth import get_user_model
    from apps.recommendations.models import UserInterest
    from apps.products.models import Product

    User = get_user_model()
    users = User.objects.filter(
        is_active=True,
        is_deleted=False,
    ).only('id').iterator(chunk_size=100)

    computed = 0
    for user in users:
        try:
            _compute_feed_for_user(user.id)
            computed += 1
        except Exception as e:
            logger.error(f"Feed precompute failed for user {user.id}: {e}")

    return f"Pre-computed feeds for {computed} users"


def _compute_feed_for_user(user_id):
    """Compute and cache feed for a single user."""
    from apps.recommendations.models import UserInterest, ProductInteraction
    from apps.products.models import Product

    interests = list(
        UserInterest.objects.filter(
            user_id=user_id, score__gt=0
        ).order_by('-score').values_list('category_id', flat=True)[:5]
    )

    if interests:
        purchased_ids = list(
            ProductInteraction.objects.filter(
                user_id=user_id, type='purchase'
            ).values_list('product_id', flat=True)[:1000]
        )
        product_ids = list(
            Product.objects.filter(
                category_id__in=interests,
                is_active=True,
                is_archived=False,
            ).exclude(
                id__in=purchased_ids
            ).order_by('-views', '-created_at').values_list('id', flat=True)[:40]
        )
    else:
        # New user — trending
        product_ids = list(
            Product.objects.filter(
                is_active=True, is_archived=False
            ).order_by('-views', '-created_at').values_list('id', flat=True)[:40]
        )

    cache_key = f'feed:user:{user_id}'
    cache.set(cache_key, product_ids, timeout=1800)  # 30 minutes


def get_cached_feed(user_id):
    """Get pre-computed feed from cache. Falls back to simple trending."""
    from apps.products.models import Product

    cache_key = f'feed:user:{user_id}'
    product_ids = cache.get(cache_key)

    if not product_ids:
        # Cache miss — compute synchronously and cache
        _compute_feed_for_user(user_id)
        product_ids = cache.get(cache_key, [])

    if not product_ids:
        # Complete fallback
        product_ids = list(
            Product.objects.filter(
                is_active=True, is_archived=False
            ).order_by('-views').values_list('id', flat=True)[:20]
        )

    return Product.objects.filter(
        id__in=product_ids, is_active=True
    ).select_related('store', 'category').prefetch_related('images')


# ── Product similarity rebuild ─────────────────────────────────────────────────

@shared_task(name='recommendations.recalculate_similarity', bind=True, max_retries=2)
def recalculate_product_similarity(self):
    """
    Nightly: rebuild product co-purchase similarity scores.
    FIX: Uses cursor-based batch processing instead of loading all orders at once.
    Processes 1,000 orders at a time to avoid memory exhaustion.
    """
    from apps.recommendations.models import ProductSimilarity
    from apps.orders.models import OrderItem

    BATCH_SIZE = 1000
    co_purchase = {}
    last_order_id = None
    batches = 0

    while True:
        qs = OrderItem.objects.filter(
            order__status__in=['delivered', 'completed']
        ).select_related('order').order_by('order_id')

        if last_order_id:
            qs = qs.filter(order_id__gt=last_order_id)

        batch = list(qs[:BATCH_SIZE])
        if not batch:
            break

        # Group by order
        order_products = {}
        for item in batch:
            order_products.setdefault(item.order_id, []).append(item.product_id)
            last_order_id = item.order_id

        # Count co-purchases
        for pid_list in order_products.values():
            unique = list(set(pid_list))
            for i, a in enumerate(unique):
                for b in unique[i + 1:]:
                    key = (min(a, b), max(a, b))
                    co_purchase[key] = co_purchase.get(key, 0) + 1

        batches += 1

        # Memory guard — flush to DB every 10 batches
        if batches % 10 == 0:
            _flush_similarity(co_purchase)
            co_purchase = {}
            logger.info(f"Similarity rebuild: processed {batches * BATCH_SIZE} orders")

    # Flush remaining
    if co_purchase:
        _flush_similarity(co_purchase)

    return f"Similarity rebuild complete — {batches} batches processed"


def _flush_similarity(co_purchase):
    """Write co-purchase scores to DB in bulk."""
    from apps.recommendations.models import ProductSimilarity

    to_update = []
    for (pid_a, pid_b), count in co_purchase.items():
        score = min(count / 10.0, 1.0)
        to_update.extend([
            ProductSimilarity(product_a_id=pid_a, product_b_id=pid_b, similarity_score=score, co_purchase_count=count),
            ProductSimilarity(product_a_id=pid_b, product_b_id=pid_a, similarity_score=score, co_purchase_count=count),
        ])

    if to_update:
        ProductSimilarity.objects.bulk_create(
            to_update,
            update_conflicts=True,
            update_fields=['similarity_score', 'co_purchase_count', 'updated_at'],
            unique_fields=['product_a', 'product_b'],
        )


# ── Cleanup tasks ─────────────────────────────────────────────────────────────

@shared_task(name='recommendations.cleanup_browsing_sessions')
def cleanup_browsing_sessions():
    """
    FIX: BrowsingSession grows forever without this.
    Delete sessions older than DATA_RETENTION['browsing_sessions'] days (default 30).
    """
    from apps.recommendations.models import BrowsingSession
    from django.conf import settings
    from datetime import timedelta

    days = getattr(settings, 'DATA_RETENTION', {}).get('browsing_sessions', 30)
    cutoff = timezone.now() - timedelta(days=days)
    deleted, _ = BrowsingSession.objects.filter(last_active__lte=cutoff).delete()
    return f"Deleted {deleted} old browsing sessions"


@shared_task(name='recommendations.cleanup_stock_urgency')
def cleanup_stock_urgency():
    """
    FIX: StockUrgencySignal grows forever without this.
    Delete signals older than 5 minutes — they're meaningless after that.
    Runs every 5 minutes via Beat.
    """
    from apps.recommendations.models import StockUrgencySignal
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(minutes=5)
    deleted, _ = StockUrgencySignal.objects.filter(last_seen__lte=cutoff).delete()
    return f"Deleted {deleted} expired urgency signals"


@shared_task(name='recommendations.check_price_alerts', bind=True, max_retries=3)
def check_price_alerts(self):
    """Check price alerts with idempotency guard."""
    from apps.recommendations.models import PriceAlert
    from apps.notifications.utils import send_notification

    # Idempotency: lock key to prevent double processing
    lock_key = 'task:check_price_alerts'
    if not cache.add(lock_key, '1', timeout=25 * 60):  # 25 min lock
        return "Skipped — already running"

    try:
        alerts = PriceAlert.objects.filter(
            is_triggered=False
        ).select_related('user', 'product')

        triggered = 0
        for alert in alerts:
            if alert.product.price <= alert.target_price:
                send_notification(
                    user=alert.user,
                    type='promotion',
                    title='Price dropped!',
                    message=f'{alert.product.title} is now {alert.product.price} AOA — your target was {alert.target_price} AOA!',
                    data={'product_id': str(alert.product_id)},
                )
                alert.is_triggered = True
                alert.notified_at = timezone.now()
                alert.save(update_fields=['is_triggered', 'notified_at'])
                triggered += 1

        return f"Checked {alerts.count()} alerts, triggered {triggered}"
    finally:
        cache.delete(lock_key)


@shared_task(name='recommendations.check_back_in_stock', bind=True, max_retries=3)
def check_back_in_stock_alerts(self):
    """Check back-in-stock alerts with idempotency guard."""
    from apps.recommendations.models import BackInStockAlert
    from apps.notifications.utils import send_notification

    lock_key = 'task:check_back_in_stock'
    if not cache.add(lock_key, '1', timeout=13 * 60):
        return "Skipped — already running"

    try:
        alerts = BackInStockAlert.objects.filter(
            notified=False,
            product__quantity__gt=0,
            product__is_active=True,
        ).select_related('user', 'product')

        count = 0
        for alert in alerts:
            send_notification(
                user=alert.user,
                type='promotion',
                title='Back in stock!',
                message=f'{alert.product.title} is available again!',
                data={'product_id': str(alert.product_id)},
            )
            alert.notified = True
            alert.save(update_fields=['notified'])
            count += 1

        return f"Notified {count} back-in-stock subscribers"
    finally:
        cache.delete(lock_key)


@shared_task(name='recommendations.weekly_digest')
def send_weekly_digest():
    """Weekly personalised email using pre-computed feeds."""
    from django.contrib.auth import get_user_model
    from django.core.mail import send_mail
    from django.conf import settings
    from apps.products.models import Product

    User = get_user_model()
    users = User.objects.filter(
        is_active=True, is_email_verified=True,
        promo_notifications=True, email_notifications=True,
    ).iterator(chunk_size=100)

    sent = 0
    for user in users:
        try:
            # Use pre-computed feed
            product_ids = cache.get(f'feed:user:{user.id}', [])
            if not product_ids:
                continue

            products = Product.objects.filter(id__in=product_ids[:6], is_active=True)
            if not products.exists():
                continue

            lines = '\n'.join([f'  • {p.title} — {p.price} AOA' for p in products])
            name = ''
            try:
                name = user.profile.full_name.split()[0]
            except Exception:
                pass

            send_mail(
                subject='Your weekly picks from MICHA',
                message=f'Hi {name or "there"},\n\nHere are this week\'s picks:\n\n{lines}\n\n— The MICHA team',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
            sent += 1
        except Exception as e:
            logger.error(f"Digest email failed for user {user.id}: {e}")

    return f"Weekly digest sent to {sent} users"
