from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


class Report(models.Model):
    TARGET_CHOICES = [
        ("seller", "Seller"),
        ("product", "Product"),
    ]

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("reviewed", "Reviewed"),
        ("actioned", "Actioned"),
    ]

    reporter = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="reports_made"
    )

    # Add defaults for existing rows to fix migrations
    target_type = models.CharField(
        max_length=10, choices=TARGET_CHOICES, default="seller"
    )
    target_id = models.PositiveIntegerField(default=1)  # default for existing rows

    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        unique_together = ("reporter", "target_type", "target_id")

    def __str__(self):
        return f"{self.reporter} → {self.target_type}:{self.target_id}"
