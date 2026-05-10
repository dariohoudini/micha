"""
Orders Models — Soft Delete Protection
FIX: Orders are financial records and must NEVER be hard deleted.
     Override delete() to raise an error preventing accidental deletion.
     Use is_deleted flag for soft delete instead.
"""
from django.db import models, transaction
from apps.payments.models import EncryptedCharField
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
    buyer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="orders", db_index=True)
    seller = models.ForeignKey(User, on_delete=models.PROTECT, related_name="seller_orders")
    idempotency_key = models.CharField(max_length=100, unique=True, blank=True)

    shipping_name = models.CharField(max_length=200, blank=True)
    shipping_phone = EncryptedCharField(max_length=500, blank=True)
    shipping_address = EncryptedCharField(max_length=2000, blank=True)
    shipping_city = models.CharField(max_length=100, blank=True)
    shipping_province = models.CharField(max_length=100, blank=True)
    shipping_country = models.CharField(max_length=100, default="Angola")

    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    # Decomposition of `discount` so we can audit "who paid for this discount".
    # platform_subsidy + seller_subsidy + store_credit_used = discount
    platform_subsidy = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Portion of discount funded by the platform (platform-wide coupons)',
    )
    seller_subsidy = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Portion of discount funded by this seller (seller-specific coupons)',
    )
    store_credit_used = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Portion redeemed from buyer loyalty / store credit',
    )
    total = models.DecimalField(max_digits=12, decimal_places=2)
    coupon_code = models.CharField(max_length=50, blank=True)

    status = models.CharField(max_length=15, choices=STATUS, default="pending")
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS, default="pending")

    tracking_number = models.CharField(max_length=100, blank=True)
    carrier = models.CharField(max_length=50, blank=True)
    estimated_delivery = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    gift_wrap = models.BooleanField(default=False)
    delivery_slot = models.CharField(
        max_length=20,
        choices=[('morning','Morning 8h-12h'),('afternoon','Afternoon 12h-17h'),('evening','Evening 17h-21h')],
        blank=True
    )

    # FIX: Soft delete — never hard delete a financial record
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="deleted_orders"
    )

    # ── MICHA Buyer Protection ───────────────────────────────────────────
    # state machine derived from order.status:
    #   awaiting_seller — pending; seller has 48h to confirm
    #   awaiting_ship   — confirmed; seller has 7 days to ship
    #   in_transit      — shipped; auto-mark delivered after 30 days
    #   in_protection   — delivered; buyer can dispute/return for 60 days
    #   completed       — protection lapsed cleanly (or buyer confirmed early)
    #   broken          — auto-cancelled / auto-refunded due to lapsed deadline
    PROTECTION_STATES = (
        ("none", "None (cancelled / refunded)"),
        ("awaiting_seller", "Awaiting seller confirmation"),
        ("awaiting_ship", "Awaiting shipment"),
        ("in_transit", "In transit"),
        ("in_protection", "Buyer protection (post-delivery)"),
        ("completed", "Protection completed"),
        ("broken", "Protection broken (auto-refunded)"),
    )
    protection_state = models.CharField(
        max_length=20, choices=PROTECTION_STATES, default="awaiting_seller", db_index=True,
    )
    protection_deadline_at = models.DateTimeField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrderManager()  # excludes soft-deleted
    all_objects = models.Manager()  # includes everything

    # Fraud detection
    fraud_score = models.IntegerField(default=0, help_text='0-100 fraud risk score from FraudEngine')
    fraud_action = models.CharField(max_length=20, default='allow', help_text='allow/flag/hold/block')

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

    # ── Buyer Protection: deadline policy per status ────────────────────
    # Days the seller / buyer has before the protection auto-actions.
    PROTECTION_DAYS = {
        "pending":   2,    # seller must confirm within 48h
        "confirmed": 7,    # then has a week to ship
        "processing": 7,   # treated like confirmed
        "shipped":   30,   # auto-mark delivered after 30 days no update
        "delivered": 60,   # post-delivery protection window for buyer
    }
    PROTECTION_STATE_BY_STATUS = {
        "pending":    "awaiting_seller",
        "confirmed":  "awaiting_ship",
        "processing": "awaiting_ship",
        "shipped":    "in_transit",
        "delivered":  "in_protection",
        "completed":  "completed",
        "cancelled":  "none",
        "refunded":   "none",
    }

    def _compute_protection_for_status(self, status):
        """Return (state, deadline_at) for the given order status."""
        from django.utils import timezone
        from datetime import timedelta
        state = self.PROTECTION_STATE_BY_STATUS.get(status, "none")
        days = self.PROTECTION_DAYS.get(status)
        deadline = timezone.now() + timedelta(days=days) if days else None
        return state, deadline

    def update_status(self, new_status, changed_by=None, note=""):
        with transaction.atomic():
            old = self.status
            self.status = new_status

            # Recompute protection state + deadline based on the new status.
            new_state, new_deadline = self._compute_protection_for_status(new_status)
            self.protection_state = new_state
            self.protection_deadline_at = new_deadline
            self.save(update_fields=[
                "status", "protection_state", "protection_deadline_at", "updated_at",
            ])

            OrderStatusLog.objects.create(
                order=self, from_status=old, to_status=new_status,
                changed_by=changed_by, note=note,
            )
            # Telemetry — track every transition so we can chart funnel + lapses
            try:
                from apps.telemetry.metrics import orders_status_transitions
                orders_status_transitions.labels(
                    from_status=old or 'new',
                    to_status=new_status,
                ).inc()
            except Exception:
                pass
            # Auto-create a buyer-visible tracking event for every status change
            OrderTrackingEvent.objects.create(
                order=self,
                code=new_status,
                description=note or OrderTrackingEvent.DEFAULT_DESCRIPTIONS.get(new_status, new_status),
                location="",
                is_visible_to_buyer=True,
            )

    def __str__(self):
        return f"Order {self.id} — {self.buyer.email}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="order_items", db_index=True)
    variant_combo = models.ForeignKey(
        "inventory.ProductVariantCombo",
        on_delete=models.SET_NULL,
        related_name="order_items",
        null=True, blank=True,
    )
    variant_options = models.JSONField(
        default=dict, blank=True,
        help_text='Snapshot of variant options at purchase time, e.g. {"Color": "Red", "Size": "M"}',
    )
    product_title = models.CharField(max_length=200)
    product_sku = models.CharField(max_length=100, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField()
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    # Fraud detection
    fraud_score = models.IntegerField(default=0, help_text='0-100 fraud risk score from FraudEngine')
    fraud_action = models.CharField(max_length=20, default='allow', help_text='allow/flag/hold/block')

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

    # Fraud detection
    fraud_score = models.IntegerField(default=0, help_text='0-100 fraud risk score from FraudEngine')
    fraud_action = models.CharField(max_length=20, default='allow', help_text='allow/flag/hold/block')

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["order", "-created_at"])]


class OrderTrackingEvent(models.Model):
    """A single checkpoint in the order's journey, like AliExpress tracking timeline.

    Auto-created on every status change; sellers can also POST manual events
    (e.g., "Saiu do armazém em Luanda — 14:30").
    """
    DEFAULT_DESCRIPTIONS = {
        "pending":    "Pedido recebido",
        "confirmed":  "Pedido confirmado pelo vendedor",
        "processing": "Pedido em preparação",
        "shipped":    "Pedido enviado",
        "delivered":  "Pedido entregue",
        "completed":  "Pedido concluído",
        "cancelled":  "Pedido cancelado",
        "refunded":   "Pedido reembolsado",
    }

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="tracking_events")
    code = models.CharField(
        max_length=30,
        help_text="Status code or custom (e.g. 'shipped', 'in_transit', 'out_for_delivery', 'arrived_hub')",
    )
    description = models.CharField(max_length=300, blank=True)
    location = models.CharField(max_length=120, blank=True, help_text='e.g. "Luanda - Kilamba"')
    is_visible_to_buyer = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="tracking_events_created")
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["occurred_at"]
        indexes = [models.Index(fields=["order", "-occurred_at"])]

    def __str__(self):
        return f"{self.order_id} · {self.code} @ {self.occurred_at}"


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

    # Fraud detection
    fraud_score = models.IntegerField(default=0, help_text='0-100 fraud risk score from FraudEngine')
    fraud_action = models.CharField(max_length=20, default='allow', help_text='allow/flag/hold/block')

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
