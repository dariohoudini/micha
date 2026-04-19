from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class FraudAlert(models.Model):
    """Flag suspicious orders or user behaviour automatically."""
    SEVERITY_CHOICES = (
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    )
    TYPE_CHOICES = (
        ('high_value_new_account', 'High Value Order from New Account'),
        ('multiple_failed_payments', 'Multiple Failed Payments'),
        ('unusual_location', 'Unusual Login Location'),
        ('rapid_orders', 'Rapid Successive Orders'),
        ('multiple_accounts', 'Suspected Multiple Accounts'),
        ('chargeback_history', 'Chargeback History'),
        ('banned_keyword', 'Banned Keyword in Product'),
    )

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='fraud_alerts', null=True, blank=True
    )
    order = models.ForeignKey(
        'orders.Order', on_delete=models.SET_NULL, null=True, blank=True, related_name='fraud_alerts'
    )
    type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    description = models.TextField()
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_fraud_alerts'
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.type} — {self.severity}"


class IPBan(models.Model):
    """Block specific IP addresses."""
    ip_address = models.GenericIPAddressField(unique=True)
    reason = models.TextField()
    banned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='ip_bans'
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_active(self):
        if self.expires_at and timezone.now() > self.expires_at:
            return False
        return True

    def __str__(self):
        return f"IP Ban: {self.ip_address}"


class BannedKeyword(models.Model):
    """Keywords that auto-flag products for review."""
    keyword = models.CharField(max_length=100, unique=True)
    severity = models.CharField(max_length=10, choices=(
        ('warn', 'Warn'), ('block', 'Block Immediately')
    ), default='warn')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.keyword


class ContentModerationFlag(models.Model):
    """Auto-flagged content for admin review."""
    CONTENT_TYPE_CHOICES = (
        ('product', 'Product'),
        ('review', 'Review'),
        ('message', 'Message'),
        ('profile', 'Profile'),
    )
    content_type = models.CharField(max_length=15, choices=CONTENT_TYPE_CHOICES)
    content_id = models.PositiveIntegerField()
    reason = models.CharField(max_length=200)
    keyword_matched = models.CharField(max_length=100, blank=True)
    is_resolved = models.BooleanField(default=False)
    action_taken = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


# ── Fraud Detection Logic ─────────────────────────────────────

def check_order_fraud(order):
    """
    Run automated fraud checks on a new order.
    Call this after order creation.
    """
    alerts = []
    user = order.buyer

    # High value order from new account (< 7 days old)
    from datetime import timedelta
    if float(order.total) > 50000:  # 50,000 AOA
        account_age = (timezone.now() - user.date_joined).days
        if account_age < 7:
            alerts.append(FraudAlert.objects.create(
                user=user, order=order,
                type='high_value_new_account',
                severity='high',
                description=f'Order total {order.total} AOA from account created {account_age} days ago.',
            ))

    # Rapid successive orders (3+ orders in 1 hour)
    from apps.orders.models import Order
    recent_orders = Order.objects.filter(
        buyer=user,
        created_at__gte=timezone.now() - timedelta(hours=1)
    ).count()
    if recent_orders >= 3:
        alerts.append(FraudAlert.objects.create(
            user=user, order=order,
            type='rapid_orders',
            severity='medium',
            description=f'{recent_orders} orders placed in the last hour.',
        ))

    return alerts


def check_product_content(product):
    """Scan product title/description for banned keywords."""
    banned = BannedKeyword.objects.all()
    text = f"{product.title} {product.description}".lower()
    for kw in banned:
        if kw.keyword.lower() in text:
            ContentModerationFlag.objects.create(
                content_type='product',
                content_id=product.pk,
                reason=f'Banned keyword detected',
                keyword_matched=kw.keyword,
            )
            if kw.severity == 'block':
                product.is_active = False
                product.save(update_fields=['is_active'])
            break
