from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


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
