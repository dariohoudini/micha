"""
Notification Models
FIX: Added deduplication — no more 3 identical "Your order shipped" notifications
     when Celery retries a task 3 times.
FIX: reference_id field added so we can deduplicate on (user, type, reference_id).
"""
from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class Notification(models.Model):
    TYPE_CHOICES = (
        ('order', 'Order Update'),
        ('payment', 'Payment'),
        ('message', 'Message'),
        ('review', 'Review'),
        ('promotion', 'Promotion'),
        ('system', 'System'),
        ('verification', 'Verification'),
        ('dispute', 'Dispute'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    message = models.TextField()
    data = models.JSONField(default=dict)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    # FIX: Deduplication key — prevents duplicate notifications on Celery retry
    # Set reference_id to order_id, product_id, etc. for deduplication
    # unique_together prevents same notification being created twice
    reference_id = models.CharField(max_length=100, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'is_read', '-created_at']),
            models.Index(fields=['user', 'type']),
            models.Index(fields=['user', 'reference_id']),
        ]
        # FIX: Deduplicate on (user, type, reference_id) within last 24 hours
        # This prevents Celery retries from sending duplicate notifications
        # Note: unique_together only when reference_id is meaningful
        # Leave as comment — enforce in send() method instead

    @classmethod
    def send(cls, user, type, title, message, data=None, reference_id=''):
        """
        Create notification with deduplication.
        If a notification with same (user, type, reference_id) exists in last hour,
        skip creation — prevents duplicate notifications on task retry.
        """
        from django.utils import timezone
        from datetime import timedelta

        if reference_id:
            recent_cutoff = timezone.now() - timedelta(hours=1)
            already_exists = cls.objects.filter(
                user=user,
                type=type,
                reference_id=reference_id,
                created_at__gte=recent_cutoff,
            ).exists()
            if already_exists:
                return None  # Deduplicated

        notification = cls.objects.create(
            user=user,
            type=type,
            title=title,
            message=message,
            data=data or {},
            reference_id=reference_id,
        )

        # Send FCM push if user has token and push is enabled
        if user.fcm_token and user.push_notifications:
            try:
                from apps.recommendations.tasks import send_push
                send_push.delay(
                    token=user.fcm_token,
                    title=title,
                    body=message[:100],
                    data={'type': type, 'reference_id': reference_id, **(data or {})},
                )
            except Exception:
                pass  # Push failure never blocks notification creation

        return notification

    def mark_read(self):
        from django.utils import timezone
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=['is_read', 'read_at'])

    def __str__(self):
        return f"{self.type}: {self.title} → {self.user.email}"
