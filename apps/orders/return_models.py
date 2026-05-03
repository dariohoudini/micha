
from django.db import models
from django.conf import settings
User = settings.AUTH_USER_MODEL

class ReturnRequest(models.Model):
    STATUS = [
        ('pending','Pending'),('approved','Approved'),
        ('rejected','Rejected'),('completed','Completed'),
    ]
    REASON = [
        ('wrong_item','Wrong item'),('damaged','Damaged'),
        ('not_as_described','Not as described'),('missing_parts','Missing parts'),
        ('changed_mind','Changed mind'),
    ]
    PICKUP = [('pickup','Pickup'),('dropoff','Drop-off')]

    order = models.ForeignKey('orders.Order', on_delete=models.CASCADE, related_name='return_requests')
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='return_requests')
    reason = models.CharField(max_length=30, choices=REASON)
    description = models.TextField(blank=True)
    photo = models.ImageField(upload_to='return_photos/', null=True, blank=True)
    pickup_method = models.CharField(max_length=10, choices=PICKUP, default='pickup')
    status = models.CharField(max_length=15, choices=STATUS, default='pending')
    admin_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Return {self.order_id} — {self.reason}"
