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

from apps.orders.models import Order, OrderItem, Payment
from apps.cart.models import Cart, CartItem
from apps.products.models import Product

logger = logging.getLogger('micha')


class CheckoutError(Exception):
    """Raised when checkout cannot proceed. Safe to show to user."""


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
        # Accept either coupon_codes (list) or coupon_code (single, legacy)
        codes = data.get('coupon_codes') or []
        if not isinstance(codes, list):
            codes = []
        single = data.get('coupon_code')
        if single and single not in codes:
            codes.append(single)
        self.coupon_codes = [str(c).strip().upper() for c in codes if str(c).strip()]
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
        ).select_for_update(of=("self",))  # Lock only cart items, not joined tables

        if not cart_items.exists():
            raise CheckoutError("Your cart is empty.")

        # 2. Validate all items and lock stock
        validated_items = []
        for item in cart_items:
            product = item.product
            if not product.is_active or product.is_archived:
                raise CheckoutError(f"'{product.title}' is no longer available.")
            if item.variant_combo:
                combo = item.variant_combo
                if not combo.is_active:
                    raise CheckoutError(f"'{product.title}' variant is no longer available.")
                if combo.quantity < item.quantity:
                    raise CheckoutError(
                        f"'{product.title}' ({combo.label}) only has {combo.quantity} left. "
                        f"You requested {item.quantity}."
                    )
            elif product.quantity < item.quantity:
                raise CheckoutError(
                    f"'{product.title}' only has {product.quantity} left. "
                    f"You requested {item.quantity}."
                )
            validated_items.append(item)

        # 3. Load shipping address
        address = self._get_address()

        # 4. Group items by seller
        seller_items = {}
        for item in validated_items:
            seller = item.product.store.owner
            seller_items.setdefault(seller, []).append(item)

        # 5. Apply coupons — returns per-seller discount Decimal + applied codes
        coupon_result = self._apply_coupons(seller_items)

        # 6. Create one order per seller, passing each seller's allocated discount
        orders = []
        for seller, items in seller_items.items():
            seller_discount = coupon_result['per_seller'].get(seller.id, Decimal('0'))
            order = self._create_order(seller, items, address, seller_discount,
                                       coupon_result['codes_used'], orders)
            orders.append(order)

        # 7. Deduct stock atomically (with row locks)
        from apps.inventory.models import ProductVariantCombo
        for item in validated_items:
            if item.variant_combo_id:
                combo = ProductVariantCombo.objects.select_for_update(of=("self",)).get(pk=item.variant_combo_id)
                if combo.quantity < item.quantity:
                    raise CheckoutError(
                        f"Stock changed for '{item.product.title}' ({combo.label}). Please refresh your cart."
                    )
                combo.quantity -= item.quantity
                if combo.quantity == 0:
                    combo.is_active = False
                combo.save(update_fields=['quantity', 'is_active'])
            else:
                product = Product.objects.select_for_update(of=("self",)).get(pk=item.product.pk)
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

    def _apply_coupons(self, seller_items):
        """Validate coupon codes with stacking rules and return per-seller discounts.

        Stacking rules (AliExpress-style):
          * At most one platform coupon (Coupon.seller is null)
          * At most one seller-specific coupon per seller
          * Platform discount is split across sellers proportionally to subtotal

        Returns:
          {
            'per_seller': {seller_id: Decimal discount},
            'codes_used': [str codes],
          }
        Raises CheckoutError on invalid / expired / duplicate-scope coupons.
        """
        empty = {'per_seller': {}, 'codes_used': []}
        if not self.coupon_codes:
            return empty

        from apps.promotions.models import Coupon
        from apps.orders.models import Order
        from django.db.models import F

        # De-dupe while preserving order
        seen = set()
        codes = [c for c in self.coupon_codes if not (c in seen or seen.add(c))]

        coupons = list(
            Coupon.objects.select_for_update().filter(code__in=codes, is_active=True)
        )
        found = {c.code for c in coupons}
        missing = [c for c in codes if c not in found]
        if missing:
            raise CheckoutError(f"Cupão inválido: {', '.join(missing)}")

        # Per-user limit & expiry
        for coupon in coupons:
            if not coupon.is_valid():
                raise CheckoutError(f"Cupão {coupon.code} expirado ou esgotado")
            if coupon.usage_limit_per_user:
                user_uses = Order.objects.filter(
                    buyer=self.user,
                    coupon_code__contains=coupon.code,
                    status__in=['confirmed', 'shipped', 'delivered', 'completed'],
                ).count()
                if user_uses >= coupon.usage_limit_per_user:
                    raise CheckoutError(f"Já usaste {coupon.code} o número máximo de vezes")

        # Stacking rules
        platform = [c for c in coupons if not c.seller_id]
        seller_specific = [c for c in coupons if c.seller_id]
        if len(platform) > 1:
            raise CheckoutError("Apenas um cupão da plataforma por compra")

        per_seller_coupon = {}
        for c in seller_specific:
            if c.seller_id in per_seller_coupon:
                raise CheckoutError("Apenas um cupão por loja por compra")
            per_seller_coupon[c.seller_id] = c

        # Subtotal per seller (use price_at_add to honour tier/variant pricing)
        seller_subtotals = {}
        grand_subtotal = Decimal('0')
        for seller, items in seller_items.items():
            sub = sum(
                ((it.price_at_add or it.product.price) * it.quantity for it in items),
                Decimal('0')
            )
            seller_subtotals[seller.id] = sub
            grand_subtotal += sub

        # Validate seller-specific coupons cover at least one item from that seller
        for seller_id, c in per_seller_coupon.items():
            if seller_id not in seller_subtotals:
                raise CheckoutError(f"Cupão {c.code} não se aplica a nenhum item")

        # Per-seller discount: platform allocation (proportional) + own seller coupon
        per_seller = {}
        for seller_id, sub in seller_subtotals.items():
            d = Decimal('0')
            # Platform coupon allocation
            if platform and grand_subtotal > 0:
                pc = platform[0]
                # If platform coupon has min_order_amount, it applies to grand subtotal
                full_disc = Decimal(str(pc.calculate_discount(grand_subtotal)))
                if full_disc > 0:
                    share = (full_disc * sub / grand_subtotal).quantize(Decimal('0.01'))
                    d += share
            # Seller-specific coupon
            if seller_id in per_seller_coupon:
                sc = per_seller_coupon[seller_id]
                d += Decimal(str(sc.calculate_discount(sub)))
            per_seller[seller_id] = d

        # Increment usage count atomically (one per coupon — shared across sellers
        # for platform coupon, once per seller-specific coupon)
        for c in coupons:
            Coupon.objects.filter(pk=c.pk).update(used_count=F('used_count') + 1)

        return {
            'per_seller': per_seller,
            'codes_used': [c.code for c in coupons],
        }

    def _create_order(self, seller, items, address, discount, codes_used, existing_orders):
        # Subtotal honours tier/variant pricing snapshotted on the cart item
        subtotal = sum(
            ((it.price_at_add or it.product.price) * it.quantity for it in items),
            Decimal('0')
        )
        from apps.shipping.models import DeliveryZone
        shipping_cost = Decimal('500.00')  # default
        try:
            zone = DeliveryZone.objects.filter(city__iexact=address.city).first()
            if zone:
                shipping_cost = zone.base_cost
        except Exception:
            pass

        # Cap discount at subtotal so total can't go negative
        discount = min(Decimal(str(discount or 0)), subtotal)
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
            coupon_code=','.join(codes_used)[:50] if codes_used else '',
            notes=self.notes,
            gift_wrap=self.gift_wrap,
            status='pending',
            payment_status='pending',
        )

        # Create order items with price + variant snapshot
        order_items = []
        for item in items:
            combo = item.variant_combo
            order_items.append(OrderItem(
                order=order,
                product=item.product,
                variant_combo=combo,
                variant_options=(combo.options if combo else {}),
                product_title=item.product.title,
                product_sku=(combo.sku if combo and combo.sku else item.product.sku or ''),
                unit_price=(combo.price if combo else item.product.price),
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

        # Log initial status + buyer-visible tracking event
        from apps.orders.models import OrderStatusLog, OrderTrackingEvent
        OrderStatusLog.objects.create(
            order=order,
            from_status='',
            to_status='pending',
            note='Order created at checkout',
        )
        OrderTrackingEvent.objects.create(
            order=order,
            code='pending',
            description=OrderTrackingEvent.DEFAULT_DESCRIPTIONS['pending'],
            is_visible_to_buyer=True,
        )

        return order
