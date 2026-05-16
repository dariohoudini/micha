from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


# ─── Relevance feedback ────────────────────────────────────────────────────
# Two tables: a raw event log (append-only, high write rate) and a rolled-up
# boost score per (query, product) that the search query joins against. The
# rollup is recomputed periodically by a Celery task with time decay — recent
# clicks count more than year-old ones.

class SearchEventKind(models.TextChoices):
    IMPRESSION = 'impression', 'Impression (shown in results)'
    CLICK      = 'click',      'Clicked through to detail'
    CART       = 'cart',       'Added to cart from search'
    PURCHASE   = 'purchase',   'Purchased after searching'


class SearchEvent(models.Model):
    """Raw per-interaction log. Append-only; aggregated into QueryProductBoost
    by a periodic task. Indexed for the aggregation query path; not intended
    to be read directly at request time."""
    query_normalized = models.CharField(max_length=200, db_index=True)
    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE,
        related_name='search_events',
    )
    kind = models.CharField(
        max_length=12, choices=SearchEventKind.choices, db_index=True,
    )
    # Position in the result list (1-indexed). Lower = stronger signal.
    position = models.PositiveSmallIntegerField(null=True, blank=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    # Anonymous-user signals are still useful in aggregate. Hash of the
    # session cookie or device fingerprint.
    anon_token = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['query_normalized', 'kind', '-created_at']),
            models.Index(fields=['product', 'kind', '-created_at']),
        ]


class QueryProductBoost(models.Model):
    """Aggregated relevance score per (query, product). Search adds this to
    the BM25 rank at query time. Updated by ``search.recompute_query_boosts``
    (Celery beat). Reads served from the cache primitive."""
    query_normalized = models.CharField(max_length=200)
    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE,
        related_name='query_boosts',
    )
    # Composite score in [0, 1]. 0 = no signal; 1 = overwhelmingly relevant.
    score = models.FloatField(default=0.0)
    # Sample size feeding this score — used to dampen low-confidence boosts.
    sample_size = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['query_normalized', 'product'],
                name='uniq_query_product_boost',
            ),
        ]
        indexes = [
            models.Index(fields=['query_normalized', '-score']),
        ]


class SearchHistory(models.Model):
    """Track what users search for — powers suggestions and autocomplete."""
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='search_history',
        null=True, blank=True
    )
    query = models.CharField(max_length=200)
    result_count = models.PositiveIntegerField(default=0)
    searched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-searched_at']

    def __str__(self):
        return f"{self.query}"


class RecentlyViewed(models.Model):
    """Track products a user recently viewed."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='recently_viewed')
    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE, related_name='viewed_by'
    )
    viewed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'product')
        ordering = ['-viewed_at']

    def __str__(self):
        return f"{self.user.email} viewed {self.product.title}"
