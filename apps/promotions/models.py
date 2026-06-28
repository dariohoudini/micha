from django.db import models
from django.conf import settings
from django.utils import timezone

User = settings.AUTH_USER_MODEL


class Coupon(models.Model):
    TYPE_CHOICES = (
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount'),
        ('free_shipping', 'Free Shipping'),
    )

    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='percentage')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    min_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_discount_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text='Cap for percentage discounts'
    )

    # Limits
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    usage_limit_per_user = models.PositiveIntegerField(default=1)
    used_count = models.PositiveIntegerField(default=0)

    # Who created it (admin or seller)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name='created_coupons'
    )
    # Optionally restrict to a specific seller's products
    seller = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='seller_coupons'
    )

    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} ({self.discount_type})"

    def is_valid(self):
        if not self.is_active:
            return False
        if self.valid_until and timezone.now() > self.valid_until:
            return False
        if self.usage_limit and self.used_count >= self.usage_limit:
            return False
        return True

    def calculate_discount(self, subtotal):
        if subtotal < self.min_order_amount:
            return 0
        if self.discount_type == 'percentage':
            discount = subtotal * (self.discount_value / 100)
            if self.max_discount_amount:
                discount = min(discount, self.max_discount_amount)
            return round(discount, 2)
        elif self.discount_type == 'fixed':
            return min(self.discount_value, subtotal)
        elif self.discount_type == 'free_shipping':
            return 0  # handled at shipping level
        return 0


class FlashSale(models.Model):
    """Time-limited discount on a specific product."""
    product = models.ForeignKey(
        'products.Product', on_delete=models.CASCADE, related_name='flash_sales'
    )
    sale_price = models.DecimalField(max_digits=10, decimal_places=2)
    original_price = models.DecimalField(max_digits=10, decimal_places=2)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def is_live(self):
        now = timezone.now()
        return self.is_active and self.start_time <= now <= self.end_time

    @property
    def discount_percentage(self):
        if self.original_price > 0:
            return round(((self.original_price - self.sale_price) / self.original_price) * 100, 1)
        return 0

    class Meta:
        ordering = ['-start_time']

    def __str__(self):
        return f"Flash sale: {self.product.title} — {self.sale_price}"


class CouponRedemptionStatus(models.TextChoices):
    APPLIED = 'applied', 'Applied'
    RELEASED = 'released', 'Released'


class CouponRedemption(models.Model):
    """Per-redemption audit ledger.

    Sum of APPLIED redemptions for a coupon must equal Coupon.used_count.
    Idempotent per (coupon, order_id): the unique constraint guarantees
    that a retried checkout for the same order produces ONE redemption
    row, not two.
    """
    coupon = models.ForeignKey(
        Coupon, on_delete=models.CASCADE, related_name='redemptions',
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='coupon_redemptions',
    )
    # Stored as CharField, not FK, so an order in another schema /
    # microservice can be referenced without a hard FK dependency.
    order_id = models.CharField(max_length=80)
    applied_amount = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal_at_apply = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
    )
    status = models.CharField(
        max_length=12, choices=CouponRedemptionStatus.choices,
        default=CouponRedemptionStatus.APPLIED,
    )
    applied_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['coupon', 'order_id'],
                name='uniq_coupon_redemption_per_order',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'coupon']),
            models.Index(fields=['status', 'applied_at']),
        ]

    def __str__(self):
        return f'{self.coupon.code} → order {self.order_id} ({self.status})'


class UserCoupon(models.Model):
    """User Process Flow §16.2 — buyer's "collected" coupons wallet.

    Separate from Coupon (the source-of-truth definition) and from
    CouponRedemption (the per-order audit). A UserCoupon row means
    "this buyer has saved this coupon for later use". Status flips
    to ``used`` when a CouponRedemption lands.
    """
    STATUS = (
        ('available', 'Available'),
        ('used', 'Used'),
        ('expired', 'Expired'),
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='collected_coupons', db_index=True)
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, related_name='collected_by', db_index=True)
    status = models.CharField(max_length=12, choices=STATUS, default='available', db_index=True)
    collected_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    order_id = models.CharField(max_length=80, blank=True)

    class Meta:
        unique_together = ('user', 'coupon')
        ordering = ['-collected_at']
        indexes = [models.Index(fields=['user', 'status'])]

    def __str__(self):
        return f'{self.user.email} ↺ {self.coupon.code} ({self.status})'


class StockNotification(models.Model):
    """User Process Flow §7.6 "Notify Me" — backorder waitlist.

    When a buyer requests a notification for an out-of-stock product
    we persist the desire here. A signal on Product.quantity going
    from 0 → >0 should fan out push notifications and mark these
    rows ``notified=True``. We expose a /resolve/ endpoint the
    inventory worker can call when stock returns.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='stock_notifications', db_index=True)
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='stock_notifications', db_index=True)
    sku_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    is_notified = models.BooleanField(default=False, db_index=True)

    class Meta:
        unique_together = ('user', 'product', 'sku_id')
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.email} → wants {self.product_id} (notified={self.is_notified})'


class SaleEvent(models.Model):
    """AliExpress Complete 2025 CH 17.3 — major sale calendar.

    Admin-configured platform-wide events (11.11, 3.28, 8.28, Black
    Friday, Choice Day). Renders as a hero banner on home + tints
    product cards with an event badge while the event window is
    active. ``slug`` is the deep link target (e.g. /event/1111-2026).
    """
    KIND = (
        ('platform', 'Platform-wide'),
        ('category', 'Category'),
        ('seller',   'Seller'),
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True)
    kind = models.CharField(max_length=12, choices=KIND, default='platform')
    headline = models.CharField(max_length=200, blank=True)
    subheading = models.CharField(max_length=400, blank=True)
    banner_image = models.ImageField(upload_to='sale_events/', blank=True, null=True)
    bg_color = models.CharField(max_length=20, default='#C9A84C')
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField(db_index=True)
    is_active = models.BooleanField(default=True)
    cta_label = models.CharField(max_length=40, default='Ver ofertas')
    cta_url = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-starts_at']
        indexes = [models.Index(fields=['is_active', 'starts_at', 'ends_at'])]

    def is_live(self):
        from django.utils import timezone
        now = timezone.now()
        return self.is_active and self.starts_at <= now <= self.ends_at

    def __str__(self):
        return f'{self.name} ({self.starts_at:%Y-%m-%d})'
