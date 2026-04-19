from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Avg

User = settings.AUTH_USER_MODEL


class Store(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stores')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    # Cached average rating — updated whenever a StoreReview is saved/deleted
    cached_rating = models.DecimalField(
        max_digits=3, decimal_places=2, default=0.00
    )
    total_reviews_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('owner', 'name')
        ordering = ['-created_at']

    def update_rating_cache(self):
        """Recalculate and store the average rating. Call after any review change."""
        result = self.reviews.aggregate(avg=Avg('rating'))
        self.cached_rating = round(result['avg'] or 0, 2)
        self.total_reviews_count = self.reviews.count()
        self.save(update_fields=['cached_rating', 'total_reviews_count'])

    def __str__(self):
        return f"{self.name} ({self.owner.email})"


class StoreReview(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='store_reviews')
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('store', 'reviewer')
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update store cache after every save
        self.store.update_rating_cache()

    def delete(self, *args, **kwargs):
        store = self.store
        super().delete(*args, **kwargs)
        # Update store cache after deletion
        store.update_rating_cache()

    def __str__(self):
        return f"{self.reviewer.email} → {self.store.name} ({self.rating}★)"
