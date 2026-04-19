"""
Orders Models — Soft Delete Protection
FIX: Orders are financial records and must NEVER be hard deleted.
     Override delete() to raise an error preventing accidental deletion.
     Use is_deleted flag for soft delete instead.
"""
from django.db import models, transaction
from django.conf import settings
import uuid

User = settings.AUTH_USER_MODEL


class OrderManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)

    def all_including_deleted(self):
        return super().get_queryset()


class Order(models.Model):
    STATUS = (
        ("pending","Pending"),("confirmed","Confirmed"),("processing","Processing"),
        ("shipped","Shipped"),("delivered","Delivered"),("completed","Completed"),
        ("cancelled","Cancelled"),("refunded","Refunded"),
    )
    PAYMENT_STATUS = (
        ("pending","Pending"),("paid","Paid"),("failed","Failed"),("refunded","Refunded"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    buyer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="orders")
    seller = models.ForeignKey(User, on_delete=models.PROTECT, related_name="seller_orders")
    idempotency_key = models.CharField(max_length=100, unique=True, blank=True)

    shipping_name = models.CharField(max_length=200, blank=True)
    shipping_phone = models.CharField(max_length=20, blank=True)
    shipping_address = models.TextField(blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_province = models.CharField(max_length=100, blank=True)
    shipping_country = models.CharField(max_length=100, default="Angola")

    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    coupon_code = models.CharField(max_length=50, blank=True)

    status = models.CharField(max_length=15, choices=STATUS, default="pending")
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS, default="pending")

    tracking_number = models.CharField(max_length=100, blank=True)
    carrier = models.CharField(max_length=50, blank=True)
    estimated_delivery = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    gift_wrap = models.BooleanField(default=False)

    # FIX: Soft delete — never hard delete a financial record
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="deleted_orders"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrderManager()  # excludes soft-deleted
    all_objects = models.Manager()  # includes everything

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["buyer", "-created_at"]),
            models.Index(fields=["seller", "status"]),
            models.Index(fields=["status", "payment_status"]),
            models.Index(fields=["idempotency_key"]),
            models.Index(fields=["is_deleted", "status"]),
        ]

    def delete(self, *args, **kwargs):
        """FIX: Prevent hard deletion of orders — they are financial records."""
        raise PermissionError(
            "Orders cannot be hard deleted — they are financial records. "
            "Use soft_delete() instead."
        )

    def soft_delete(self, deleted_by=None):
        """Soft delete — marks order as deleted without removing from DB."""
        from django.utils import timezone
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = deleted_by
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    def verify_total(self):
        computed = sum(item.unit_price * item.quantity for item in self.items.all())
        computed_total = computed + self.shipping_cost - self.discount
        if abs(float(computed_total) - float(self.total)) > 0.01:
            raise ValueError(
                f"Order total mismatch: stored={self.total}, computed={computed_total}"
            )
        return True

    def update_status(self, new_status, changed_by=None, note=""):
        with transaction.atomic():
            old = self.status
            self.status = new_status
            self.save(update_fields=["status", "updated_at"])
            OrderStatusLog.objects.create(
                order=self, from_status=old, to_status=new_status,
                changed_by=changed_by, note=note,
            )

    def __str__(self):
        return f"Order {self.id} — {self.buyer.email}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="order_items")
    product_title = models.CharField(max_length=200)
    product_sku = models.CharField(max_length=100, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        indexes = [models.Index(fields=["order", "product"])]

    def save(self, *args, **kwargs):
        self.total_price = self.unit_price * self.quantity
        super().save(*args, **kwargs)


class OrderStatusLog(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_logs")
    from_status = models.CharField(max_length=15)
    to_status = models.CharField(max_length=15)
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["order", "-created_at"])]


class Payment(models.Model):
    STATUS = (("pending","Pending"),("paid","Paid"),("failed","Failed"),("refunded","Refunded"))
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="payment")
    method = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    gateway_reference = models.CharField(max_length=200, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=5, default="AOA")
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["gateway_reference"])]


class Refund(models.Model):
    STATUS = (("pending","Pending"),("approved","Approved"),("rejected","Rejected"),("processed","Processed"))
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="refunds")
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="refund_requests")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS, default="pending")
    admin_note = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
