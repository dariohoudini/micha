"""
Cart Models
FIX: version field added for optimistic locking
     Prevents two browser tabs from both adding the last item in stock
     Checkout detects version mismatch and rejects the second request
"""
from django.db import models, transaction
from django.conf import settings
from django.db.models import F

User = settings.AUTH_USER_MODEL


class Cart(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="cart")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=["user"])]

    @property
    def total(self):
        return sum(item.line_total for item in self.items.all())

    @property
    def item_count(self):
        return self.items.aggregate(total=models.Sum("quantity"))["total"] or 0

    def __str__(self):
        return f"Cart({self.user.email})"


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.CASCADE, related_name="cart_items", db_index=True)
    variant_combo = models.ForeignKey(
        "inventory.ProductVariantCombo",
        on_delete=models.CASCADE,
        related_name="cart_items",
        null=True, blank=True,
        help_text="Set when product has variants and user picked one",
    )
    quantity = models.PositiveIntegerField(default=1)
    price_at_add = models.DecimalField(max_digits=10, decimal_places=2)

    # Optimistic locking — detect concurrent modifications
    version = models.PositiveIntegerField(default=1)

    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # Same product can appear multiple times if different variant combos chosen
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "product", "variant_combo"],
                name="cart_unique_product_variant",
            ),
        ]
        indexes = [models.Index(fields=["cart", "product"])]

    @property
    def line_total(self):
        return self.price_at_add * self.quantity

    @property
    def price_changed(self):
        """True if seller changed price since item was added."""
        current = self.variant_combo.price if self.variant_combo else self.product.price
        return current != self.price_at_add

    def save(self, *args, **kwargs):
        if not self.pk:
            self.price_at_add = self.variant_combo.price if self.variant_combo else self.product.price
        else:
            # Increment version on every update — detect concurrent changes
            self.version = F("version") + 1
        super().save(*args, **kwargs)

    def update_quantity(self, new_quantity, expected_version):
        """
        FIX: Optimistic lock — only update if version matches.
        Raises ValueError if another request modified this item concurrently.
        """
        with transaction.atomic():
            updated = CartItem.objects.filter(
                pk=self.pk, version=expected_version
            ).update(
                quantity=new_quantity,
                version=F("version") + 1,
            )
            if not updated:
                raise ValueError(
                    "Cart was modified by another request. Please refresh and try again."
                )

    def __str__(self):
        return f"{self.quantity}x {self.product.title}"
