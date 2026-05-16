"""
apps/alerts/models.py

Saved-search alerts. Buyers express "let me know when a new <something>
matches what I was searching for" — the engagement primitive AliExpress
calls "search subscriptions".

Two tables:

  SavedSearch       What the user told us to watch for. Normalised query +
                    filters + baseline set of product IDs that matched at
                    creation time. The runner compares each periodic re-run
                    against this baseline; only NEW matches fire alerts.

  AlertDelivery     Append-only delivery audit. One row per "we told the
                    user about X matches at time T". Used to:
                      - dedupe (we don't re-notify on the same match)
                      - rate-limit ("at most one digest per user per day")
                      - prove to support we sent the notification
                      - feed the open-rate analytics later

The PriceAlert table (apps/recommendations) is separate and stays as-is —
it pre-dates this and works for product-level alerts. AlertDelivery is
designed to subsume both eventually.
"""
from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class SavedSearch(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE,
                             related_name='saved_searches', db_index=True)
    # Human-friendly name shown in the UI ("phones under 200k").
    name = models.CharField(max_length=120)
    # The normalized query string (lowercased, whitespace-collapsed) — same
    # shape as search_events.SearchEvent.query_normalized so analysis joins
    # are trivial.
    query_normalized = models.CharField(max_length=200, db_index=True)
    # Free-form filter dict (price_min, price_max, category, brand, …).
    filters = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    # Snapshot of product IDs that matched at creation time. The runner
    # compares each re-run against this set and notifies on additions.
    # Stored as JSONField for portability — at ~50 ids × 36 chars (UUID) =
    # ~2KB per row, which is fine. Trimmed to MAX_BASELINE_SIZE entries to
    # bound storage.
    baseline_product_ids = models.JSONField(default=list, blank=True)

    last_run_at = models.DateTimeField(null=True, blank=True)
    # Soft cap on how often the runner notifies for THIS saved search.
    # Defaults to "at most one digest per day" — buyers don't want a flood.
    min_notify_interval_seconds = models.PositiveIntegerField(default=86400)
    last_notified_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    MAX_BASELINE_SIZE = 200

    class Meta:
        indexes = [
            models.Index(fields=['is_active', 'last_run_at']),
        ]
        ordering = ['-created_at']


class AlertKind(models.TextChoices):
    SAVED_SEARCH      = 'saved_search',      'Saved search'
    PRICE_DROP        = 'price_drop',        'Price drop'
    BACK_IN_STOCK     = 'back_in_stock',     'Back in stock'


class DeliveryChannel(models.TextChoices):
    IN_APP    = 'in_app',    'In-app notification'
    EMAIL     = 'email',     'Email'
    PUSH      = 'push',      'Push notification'
    OUTBOX    = 'outbox',    'Outbox (downstream consumers)'


class AlertDelivery(models.Model):
    """Append-only audit row per alert fired. Composable across all alert
    kinds (saved-search, price-drop, back-in-stock) — one query gives the
    user's full notification history."""
    user = models.ForeignKey(User, on_delete=models.CASCADE,
                             related_name='alert_deliveries')
    kind = models.CharField(max_length=20, choices=AlertKind.choices, db_index=True)
    channel = models.CharField(max_length=10, choices=DeliveryChannel.choices)

    # FK to the alert config row. Polymorphic via ref_* — saved_search FK
    # is the common case; price/stock alerts use ref_type+ref_id.
    saved_search = models.ForeignKey(
        SavedSearch, on_delete=models.CASCADE,
        related_name='deliveries', null=True, blank=True,
    )
    ref_type = models.CharField(max_length=40, blank=True)
    ref_id   = models.CharField(max_length=80, blank=True)

    # Product IDs included in this delivery (JSON list of strings).
    product_ids = models.JSONField(default=list, blank=True)
    # Free-form payload that was sent — useful for ops investigating
    # complaints ("the email I got said X, what really triggered?").
    payload = models.JSONField(default=dict, blank=True)

    delivered_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', '-delivered_at']),
            models.Index(fields=['kind', '-delivered_at']),
            models.Index(fields=['saved_search', '-delivered_at']),
        ]
        ordering = ['-delivered_at']
