
from django.db import models
from django.conf import settings
User = settings.AUTH_USER_MODEL

class ReviewFlag(models.Model):
    STATUS = [('pending','Pending'),('dismissed','Dismissed'),('actioned','Actioned')]
    REASON = [
        ('fake','Fake review'),('offensive','Offensive content'),
        ('wrong_product','Wrong product'),('competitor','From competitor'),('other','Other'),
    ]
    review = models.ForeignKey('reviews.ProductReview', on_delete=models.CASCADE, related_name='flags')
    flagged_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='review_flags')
    reason = models.CharField(max_length=20, choices=REASON)
    details = models.TextField(blank=True)
    status = models.CharField(max_length=15, choices=STATUS, default='pending')
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_flags')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('review', 'flagged_by')

    def __str__(self):
        return f"Flag on review {self.review_id} — {self.reason}"
