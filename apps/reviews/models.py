from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class Review(models.Model):
    """Review left on a seller (existing)."""
    RATING_CHOICES = [(i, i) for i in range(1, 6)]

    reviewer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="given_reviews"
    , db_index=True)
    seller = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="received_reviews"
    , db_index=True)
    rating = models.IntegerField(choices=RATING_CHOICES)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("reviewer", "seller")
        ordering = ["-created_at"]
        # DB & Storage doc CH23 ck_review_rating: the DB is the last line of
        # defence — a rating outside 1..5 can never be persisted, even if a
        # caller bypasses the choices validation.
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rating__gte=1) & models.Q(rating__lte=5),
                name="ck_review_rating_1_5"),
        ]

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
    , db_index=True)
    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE, related_name='reviews'
    , db_index=True)
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
        # DB & Storage doc CH23 ck_review_rating (1..5).
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rating__gte=1) & models.Q(rating__lte=5),
                name="ck_product_review_rating_1_5"),
        ]

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
