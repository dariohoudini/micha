from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL

class Review(models.Model):
    RATING_CHOICES = [(i, i) for i in range(1, 6)]

    reviewer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="given_reviews", default=1
    )
    seller = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="received_reviews", default=1
    )

    rating = models.IntegerField(choices=RATING_CHOICES)
    comment = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("reviewer", "seller")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.reviewer} → {self.seller} ({self.rating})"
