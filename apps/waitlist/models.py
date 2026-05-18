"""
apps/waitlist/models.py

Waitlist subscriptions. Buyers who hit an out-of-stock product can join
the waitlist; we notify them in FIFO order when stock returns.

Why a new app instead of extending apps.recommendations.BackInStockAlert:
  • Need FIFO ordering (existing model has no position field — alerts
    fire in arbitrary order).
  • Need conversion tracking (existing has notified=True bool but no
    "did the buyer actually buy after we told them?").
  • Need rate-limited fanout (existing fires all alerts at once — for
    a viral product with 50k waitlisters that's a thundering herd).
  • Need outbox composability so seller webhooks fire.
  • Need cleanup of stale entries (existing accumulates forever).

The old BackInStockAlert stays in place — extracting its data into the
new model is a future migration. New code paths use WaitlistEntry.
"""
from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class WaitlistStatus(models.TextChoices):
    WAITING   = 'waiting',   'Waiting for restock'
    NOTIFIED  = 'notified',  'Notified — buyer should act'
    CONVERTED = 'converted', 'Converted — buyer purchased'
    CANCELLED = 'cancelled', 'Cancelled by buyer'
    EXPIRED   = 'expired',   'Expired (stale entry purged)'


class WaitlistEntry(models.Model):
    """One row per (user, product) waitlist subscription."""
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='waitlist_entries',
    )
    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE,
        related_name='waitlist_entries',
    )
    # Optional: which variant the user wants. Empty = any variant counts.
    variant_combo = models.ForeignKey(
        'inventory.ProductVariantCombo', on_delete=models.CASCADE,
        null=True, blank=True, related_name='waitlist_entries',
    )

    status = models.CharField(
        max_length=10, choices=WaitlistStatus.choices,
        default=WaitlistStatus.WAITING, db_index=True,
    )
    # Position relative to the product. Assigned at join time from a
    # per-product sequence; lower = earlier joiner. NOT a primary key —
    # users who cancel leave gaps; we don't compact (compaction would
    # be O(N) and the gaps don't matter for FIFO semantics).
    position = models.PositiveIntegerField(db_index=True)

    joined_at = models.DateTimeField(auto_now_add=True, db_index=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    converted_at = models.DateTimeField(null=True, blank=True)
    # When the user actually buys, we stamp this for analytics.
    converted_order_id = models.CharField(max_length=80, blank=True)

    class Meta:
        constraints = [
            # One active entry per (user, product, variant). Re-joining
            # a product after cancelling is allowed — different status.
            models.UniqueConstraint(
                fields=['user', 'product', 'variant_combo'],
                condition=models.Q(status='waiting'),
                name='uniq_active_waitlist_entry',
            ),
        ]
        indexes = [
            models.Index(fields=['product', 'status', 'position']),
            models.Index(fields=['user', '-joined_at']),
        ]
        ordering = ['product', 'position']

    def __str__(self):
        return f'WaitlistEntry({self.user_id}, {self.product_id}, '\
               f'pos={self.position}, {self.status})'
