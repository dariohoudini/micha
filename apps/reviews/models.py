from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class Review(models.Model):
    """Review left on a seller (existing)."""
    RATING_CHOICES = [(i, i) for i in range(1, 6)]

    reviewer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="given_reviews"
    )
    seller = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="received_reviews"
    )
    rating = models.IntegerField(choices=RATING_CHOICES)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("reviewer", "seller")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reviewer} → {self.seller} ({self.rating}★)"


class ProductReview(models.Model):
    """
    Review on a specific product.
    Only allowed after a confirmed delivered order containing that product.
    """
    RATING_CHOICES = [(i, i) for i in range(1, 6)]

    reviewer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='product_reviews_given'
    )
    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE, related_name='reviews'
    )
    order_item = models.OneToOneField(
        'orders.OrderItem', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='review'
    )
    rating = models.IntegerField(choices=RATING_CHOICES)
    title = models.CharField(max_length=200, blank=True)
    comment = models.TextField(blank=True)

    # Seller reply to review
    seller_reply = models.TextField(blank=True, null=True)
    seller_replied_at = models.DateTimeField(null=True, blank=True)

    # Helpful votes
    helpful_count = models.PositiveIntegerField(default=0)

    is_verified_purchase = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('reviewer', 'product')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.reviewer.email} → {self.product.title} ({self.rating}★)"


class ReviewPhoto(models.Model):
    """Photos attached to a product review."""
    review = models.ForeignKey(ProductReview, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='review_photos/')
    uploaded_at = models.DateTimeField(auto_now_add=True)


class ReviewHelpfulVote(models.Model):
    """Track who voted a review as helpful (one vote per user per review)."""
    review = models.ForeignKey(
        ProductReview, on_delete=models.CASCADE, related_name='helpful_votes'
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='helpful_votes_cast')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('review', 'user')
