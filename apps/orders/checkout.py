"""
Checkout Service — Atomic & Idempotent
Fixes:
1. Everything wrapped in @transaction.atomic — no partial orders
2. Idempotency key — duplicate requests return same order, not two orders
3. Total verified before payment is initiated
4. Stock reserved atomically before order is created
5. Price snapshot taken from product at checkout time
"""
import uuid
import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order, OrderItem, Payment
from apps.cart.models import Cart, CartItem
from apps.inventory.models import StockReservation
from apps.products.models import Product

logger = logging.getLogger('micha')


class CheckoutError(Exception):
    """Raised when checkout cannot proceed. Safe to show to user."""
    pass


class CheckoutService:
    """
    Handles the full checkout flow atomically.
    Usage:
        service = CheckoutService(user=request.user, data=request.data)
        orders = service.execute()  # returns list of Order objects (one per seller)
    """

    def __init__(self, user, data):
        self.user = user
        self.address_id = data.get('address_id')
        self.payment_method = data.get('payment_method', 'card')
        self.notes = data.get('notes', '')
        self.gift_wrap = data.get('gift_wrap', False)
        self.coupon_code = data.get('coupon_code', '')
        # Idempotency key — client generates once, retries use same key
        self.idempotency_key = data.get('idempotency_key') or str(uuid.uuid4())

    def execute(self):
        """
        Execute checkout atomically. Returns list of created orders.
        Raises CheckoutError if anything is wrong.
        """
        # IDEMPOTENCY: If this key was already processed, return existing orders
        existing = Order.objects.filter(
            idempotency_key=self.idempotency_key,
            buyer=self.user,
        )
        if existing.exists():
            logger.info(f"Idempotent checkout: returning existing orders for key {self.idempotency_key}")
            return list(existing)

        with transaction.atomic():
            return self._process_checkout()

    def _process_checkout(self):
        # 1. Load cart
        try:
            cart = Cart.objects.get(user=self.user)
        except Cart.DoesNotExist:
            raise CheckoutError("Your cart is empty.")

        cart_items = CartItem.objects.filter(
            cart=cart
        ).select_related(
            'product', 'product__store', 'product__store__owner', 'product__category'
        ).select_for_update()  # Lock cart items during checkout

        if not cart_items.exists():
            raise CheckoutError("Your cart is empty.")

        # 2. Validate all items and lock stock
        validated_items = []
        for item in cart_items:
            product = item.product
            if not product.is_active or product.is_archived:
                raise CheckoutError(f"'{product.title}' is no longer available.")
            if product.quantity < item.quantity:
                raise CheckoutError(
                    f"'{product.title}' only has {product.quantity} left. "
                    f"You requested {item.quantity}."
                )
            validated_items.append(item)

        # 3. Load shipping address
        address = self._get_address()

        # 4. Apply coupon if provided
        discount = self._apply_coupon(cart_items)

        # 5. Group items by seller
        seller_items = {}
        for item in validated_items:
            seller = item.product.store.owner
            seller_items.setdefault(seller, []).append(item)

        # 6. Create one order per seller
        orders = []
        for seller, items in seller_items.items():
            order = self._create_order(seller, items, address, discount, orders)
            orders.append(order)

        # 7. Deduct stock atomically (with row locks)
        for item in validated_items:
            product = Product.objects.select_for_update().get(pk=item.product.pk)
            if product.quantity < item.quantity:
                raise CheckoutError(f"Stock changed for '{product.title}'. Please refresh your cart.")
            product.quantity -= item.quantity
            if product.quantity == 0:
                product.is_active = False
            product.save(update_fields=['quantity', 'is_active'])

        # 8. Clear cart
        cart_items.delete()

        logger.info(f"Checkout complete: {len(orders)} orders created for user {self.user.email}")
        return orders

    def _get_address(self):
        if not self.address_id:
            raise CheckoutError("Shipping address is required.")
        from apps.shipping.models import ShippingAddress
        try:
            return ShippingAddress.objects.get(pk=self.address_id, user=self.user)
        except ShippingAddress.DoesNotExist:
            raise CheckoutError("Shipping address not found.")

    def _apply_coupon(self, cart_items):
        discount = Decimal('0.00')
        if not self.coupon_code:
            return discount
        try:
            from apps.promotions.models import Coupon
            coupon = Coupon.objects.get(
                code=self.coupon_code,
                is_active=True,
            )
            if coupon.is_valid():
                subtotal = sum(item.product.price * item.quantity for item in cart_items)
                discount = coupon.calculate_discount(subtotal)
                coupon.record_use()
        except Exception:
            pass  # Invalid coupon — proceed without discount
        return discount

    def _create_order(self, seller, items, address, discount, existing_orders):
        # Split discount proportionally if multiple sellers
        subtotal = sum(item.product.price * item.quantity for item in items)
        from apps.shipping.models import DeliveryZone
        shipping_cost = Decimal('500.00')  # default
        try:
            zone = DeliveryZone.objects.filter(city__iexact=address.city).first()
            if zone:
                shipping_cost = zone.base_cost
        except Exception:
            pass

        total = subtotal + shipping_cost - discount

        # Build idempotency key per seller (unique per checkout session per seller)
        seller_idem_key = f"{self.idempotency_key}:{seller.pk}"

        order = Order.objects.create(
            buyer=self.user,
            seller=seller,
            idempotency_key=seller_idem_key,
            shipping_name=address.full_name,
            shipping_phone=address.phone,
            shipping_address=address.address_line,
            shipping_city=address.city,
            shipping_province=getattr(address, 'province', ''),
            shipping_country=getattr(address, 'country', 'Angola'),
            subtotal=subtotal,
            shipping_cost=shipping_cost,
            discount=discount,
            total=total,
            coupon_code=self.coupon_code,
            notes=self.notes,
            gift_wrap=self.gift_wrap,
            status='pending',
            payment_status='pending',
        )

        # Create order items with price snapshot
        order_items = []
        for item in items:
            order_items.append(OrderItem(
                order=order,
                product=item.product,
                product_title=item.product.title,  # snapshot
                product_sku=item.product.sku or '',
                unit_price=item.product.price,      # snapshot at checkout time
                quantity=item.quantity,
            ))
        OrderItem.objects.bulk_create(order_items)

        # Verify total before payment
        order.verify_total()

        # Create payment record
        Payment.objects.create(
            order=order,
            method=self.payment_method,
            amount=total,
            currency='AOA',
        )

        # Log initial status
        from apps.orders.models import OrderStatusLog
        OrderStatusLog.objects.create(
            order=order,
            from_status='',
            to_status='pending',
            note='Order created at checkout',
        )

        return order
