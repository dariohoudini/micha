"""
Notification Models
FIX: Added deduplication — no more 3 identical "Your order shipped" notifications
     when Celery retries a task 3 times.
FIX: reference_id field added so we can deduplicate on (user, type, reference_id).
"""
from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL

# Re-export auxiliary models so Django's app registry picks them up.
# Suppression + NotificationLog live in their own files for separation
# of concerns (different lifecycle, different retention).
from .suppression_models import SuppressedEmail  # noqa: F401,E402
from .notification_log_models import NotificationLog  # noqa: F401,E402
from .device_models import DeviceToken  # noqa: F401,E402  R5: multi-device push


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

        # R5: multi-device push fan-out. Pre-R5 this checked
        # ``user.fcm_token`` (a single field) which broke when a user
        # had more than one device. push_service.send_to_user enumerates
        # active DeviceToken rows and sends to each, with FCM error
        # responses driving token deactivation.
        #
        # send_to_user also honours user.push_notifications and the
        # back-compat legacy fcm_token field, so this call stays the
        # single chokepoint.
        if getattr(user, 'push_notifications', True):
            try:
                from apps.notifications.push_service import send_to_user
                send_to_user(
                    user,
                    title=title,
                    body=message[:100],
                    data={
                        'type': type,
                        'reference_id': reference_id,
                        **(data or {}),
                    },
                )
            except Exception:
                # Push failure never blocks notification creation —
                # the in-app row is still there for next app open.
                pass

        return notification

    def mark_read(self):
        from django.utils import timezone
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=['is_read', 'read_at'])

    def __str__(self):
        return f"{self.type}: {self.title} → {self.user.email}"


class NotificationManager:
    """Helper to create personalised notifications with user name + product."""

    @staticmethod
    def order_confirmed(user, order):
        from apps.notifications.models import Notification
        Notification.objects.create(
            recipient=user,
            notification_type='order_update',
            title=f'Pedido confirmado!',
            message=f'Olá {user.profile.full_name or user.email.split("@")[0]}! O teu pedido #{str(order.id)[:8].upper()} foi confirmado pelo vendedor.',
            data={'order_id': str(order.id)},
        )

    @staticmethod
    def order_shipped(user, order):
        from apps.notifications.models import Notification
        Notification.objects.create(
            recipient=user,
            notification_type='order_update',
            title='O teu pedido está a caminho!',
            message=f'O teu pedido #{str(order.id)[:8].upper()} foi enviado. {f"Rastreamento: {order.tracking_number}" if order.tracking_number else "Entrega prevista em breve."}',
            data={'order_id': str(order.id)},
        )

    @staticmethod
    def order_delivered(user, order):
        from apps.notifications.models import Notification
        Notification.objects.create(
            recipient=user,
            notification_type='order_update',
            title='Pedido entregue!',
            message=f'O teu pedido chegou! Partilha a tua experiência e avalia o vendedor.',
            data={'order_id': str(order.id)},
        )

    @staticmethod
    def price_drop(user, product, old_price, new_price):
        from apps.notifications.models import Notification
        saving = old_price - new_price
        Notification.objects.create(
            recipient=user,
            notification_type='price_drop',
            title=f'Preço desceu! -{int((saving/old_price)*100)}%',
            message=f'"{product.title}" baixou de {int(old_price):,} Kz para {int(new_price):,} Kz. Poupa {int(saving):,} Kz!',
            data={'product_id': product.id, 'product_slug': product.slug},
        )

    @staticmethod
    def back_in_stock(user, product):
        from apps.notifications.models import Notification
        Notification.objects.create(
            recipient=user,
            notification_type='back_in_stock',
            title='Produto disponível!',
            message=f'"{product.title}" está de volta ao stock. Compra agora antes que esgote!',
            data={'product_id': product.id, 'product_slug': product.slug},
        )

    @staticmethod
    def cart_abandonment(user, item_count):
        from apps.notifications.models import Notification
        name = user.profile.full_name.split()[0] if hasattr(user, 'profile') and user.profile.full_name else ''
        greeting = f'{name}, tens' if name else 'Tens'
        Notification.objects.create(
            recipient=user,
            notification_type='cart_abandonment',
            title='Ainda tens produtos no carrinho',
            message=f'{greeting} {item_count} produto{"s" if item_count > 1 else ""} à espera. Completa a compra antes que esgotem!',
        )
