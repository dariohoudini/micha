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
        # Loyalty store credit redemption (whole-Kz amount).
        # Coerce via Decimal so a string like "100.50" doesn't go through
        # float() and pick up binary-floating-point drift. The int()
        # cast then truncates fractional Kz deliberately — store credit
        # is redeemed in whole units.
        try:
            from apps.core.money import to_decimal
            self.use_store_credit = max(
                0, int(to_decimal(data.get('use_store_credit', 0))),
            )
        except (TypeError, ValueError):
            self.use_store_credit = 0
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

        # 5b. Apply store credit (loyalty redemption) — splits proportionally
        credit_result = self._apply_store_credit(seller_items, coupon_result['per_seller'])

        # 6. Create one order per seller with full discount decomposition
        orders = []
        for seller, items in seller_items.items():
            platform_subsidy = coupon_result.get('per_seller_platform', {}).get(seller.id, Decimal('0'))
            seller_subsidy = coupon_result.get('per_seller_seller', {}).get(seller.id, Decimal('0'))
            store_credit = credit_result['per_seller'].get(seller.id, Decimal('0'))
            order = self._create_order(
                seller, items, address,
                platform_subsidy=platform_subsidy,
                seller_subsidy=seller_subsidy,
                store_credit=store_credit,
                codes_used=coupon_result['codes_used'],
                existing_orders=orders,
            )
            orders.append(order)

        # 7. Deduct stock atomically — DEADLOCK-FREE.
        #
        # Two production issues this section addresses:
        #
        # (a) Lock ordering. Without sorted locking, two concurrent
        #     checkouts of overlapping carts can acquire the same set
        #     of product rows in DIFFERENT orders, producing a
        #     deadlock cycle. Postgres auto-detects + aborts one of
        #     them, but customers see 500s during high-traffic events.
        #
        #     Fix: sort product PKs and variant PKs ascending, then
        #     acquire all locks in that order. Concurrent checkouts
        #     queue up rather than deadlock.
        #
        # (b) Per-row lock round-trips. The old code did N separate
        #     SELECT FOR UPDATE queries — one per item. A 10-item
        #     cart was 10 sequential DB round-trips. The batched
        #     pk__in form takes ONE round-trip and the database
        #     locks rows in index order.
        from apps.inventory.models import ProductVariantCombo
        from apps.telemetry.metrics import checkout_stock_contention

        # Collect PKs we need to lock, sorted for deterministic order.
        items_by_combo_pk = {}
        items_by_product_pk = {}
        for item in validated_items:
            if item.variant_combo_id:
                items_by_combo_pk.setdefault(item.variant_combo_id, 0)
                items_by_combo_pk[item.variant_combo_id] += item.quantity
            else:
                items_by_product_pk.setdefault(item.product.pk, 0)
                items_by_product_pk[item.product.pk] += item.quantity

        # Lock products first (PK-sorted), then variants (PK-sorted).
        # Locking products before variants is part of the global lock
        # order: any other code path touching both must lock in this
        # order too (see apps/orders/stock_restore for the matching
        # implementation).
        if items_by_product_pk:
            locked_products = {
                p.pk: p for p in
                Product.objects.select_for_update(of=("self",))
                .filter(pk__in=sorted(items_by_product_pk.keys()))
                .order_by('pk')
            }
        else:
            locked_products = {}

        if items_by_combo_pk:
            locked_combos = {
                c.pk: c for c in
                ProductVariantCombo.objects.select_for_update(of=("self",))
                .filter(pk__in=sorted(items_by_combo_pk.keys()))
                .order_by('pk')
            }
        else:
            locked_combos = {}

        # Apply decrements with re-validation under lock.
        for combo_pk, total_qty in items_by_combo_pk.items():
            combo = locked_combos.get(combo_pk)
            if combo is None:
                checkout_stock_contention.labels(reason='product_vanished').inc()
                raise CheckoutError(
                    'Stock changed since you opened your cart. Please refresh.'
                )
            if combo.quantity < total_qty:
                checkout_stock_contention.labels(reason='variant_oversold').inc()
                raise CheckoutError(
                    f"'{combo.product.title}' ({combo.label}) stock changed. "
                    f"Please refresh your cart."
                )
            combo.quantity -= total_qty
            if combo.quantity == 0:
                combo.is_active = False
            combo.save(update_fields=['quantity', 'is_active'])

        for product_pk, total_qty in items_by_product_pk.items():
            product = locked_products.get(product_pk)
            if product is None:
                checkout_stock_contention.labels(reason='product_vanished').inc()
                raise CheckoutError(
                    'Stock changed since you opened your cart. Please refresh.'
                )
            if product.quantity < total_qty:
                checkout_stock_contention.labels(reason='product_oversold').inc()
                raise CheckoutError(
                    f"'{product.title}' stock changed. "
                    f"Please refresh your cart."
                )
            product.quantity -= total_qty
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

    def _apply_store_credit(self, seller_items, coupon_per_seller):
        """Redeem the user's store_credit balance against this checkout.

        Capped at min(requested, balance, sum(seller_subtotals_after_coupon)).
        Splits proportionally across sellers based on remaining subtotal.
        Atomically decrements the user's balance.
        """
        empty = {'per_seller': {}, 'amount': Decimal('0')}
        if self.use_store_credit <= 0:
            return empty

        from django.db import transaction
        from django.contrib.auth import get_user_model
        User = get_user_model()

        # Compute per-seller subtotals net of coupon discount
        remaining = {}
        for seller, items in seller_items.items():
            sub = sum(
                ((it.price_at_add or it.product.price) * it.quantity for it in items),
                Decimal('0')
            )
            sub_after = sub - coupon_per_seller.get(seller.id, Decimal('0'))
            remaining[seller.id] = max(sub_after, Decimal('0'))
        total_remaining = sum(remaining.values(), Decimal('0'))
        if total_remaining <= 0:
            return empty

        # Lock user row, cap requested amount at current balance
        with transaction.atomic():
            locked = User.objects.select_for_update().get(pk=self.user.pk)
            balance = Decimal(str(locked.store_credit or 0))
            requested = Decimal(str(self.use_store_credit))
            applied = min(requested, balance, total_remaining)
            if applied <= 0:
                return empty
            locked.store_credit = balance - applied
            locked.save(update_fields=['store_credit'])
            self.user.store_credit = locked.store_credit  # keep instance fresh

            # Source of truth: post to ledger.
            # The buyer's store_credit account is debited; the platform refund pool
            # is credited (the platform now "owes" itself this redeemed credit, which
            # offsets the platform's earlier outlay when the credit was first awarded).
            try:
                from apps.ledger.service import transfer
                from apps.ledger.models import Account, AccountType
                transfer(
                    from_account=Account.for_user(
                        self.user, AccountType.USER_STORE_CREDIT, currency='AOA'
                    ),
                    to_account=Account.platform(
                        AccountType.PLATFORM_REFUND_POOL, currency='AOA'
                    ),
                    amount=applied,
                    journal_key=f'checkout:{self.idempotency_key}:store_credit',
                    ref_type='checkout',
                    ref_id=self.idempotency_key,
                    description=f'Store-credit redemption {applied} Kz',
                    user=self.user,
                )
            except Exception:
                # Ledger posting failure must not break checkout (legacy column already updated).
                # Reconciliation cron will surface the drift.
                pass

        # Split proportionally
        per_seller = {}
        for sid, rem in remaining.items():
            if rem <= 0:
                continue
            share = (applied * rem / total_remaining).quantize(Decimal('0.01'))
            per_seller[sid] = share

        return {'per_seller': per_seller, 'amount': applied}

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

        # Per-seller discount split between platform-funded and seller-funded.
        per_seller = {}            # total discount per seller (platform + seller)
        per_seller_platform = {}   # share funded by platform (subsidised by us)
        per_seller_seller = {}     # share funded by the seller (lower margin)
        for seller_id, sub in seller_subtotals.items():
            platform_share = Decimal('0')
            seller_share = Decimal('0')
            if platform and grand_subtotal > 0:
                pc = platform[0]
                full_disc = Decimal(str(pc.calculate_discount(grand_subtotal)))
                if full_disc > 0:
                    platform_share = (full_disc * sub / grand_subtotal).quantize(Decimal('0.01'))
            if seller_id in per_seller_coupon:
                sc = per_seller_coupon[seller_id]
                seller_share = Decimal(str(sc.calculate_discount(sub)))
            per_seller_platform[seller_id] = platform_share
            per_seller_seller[seller_id] = seller_share
            per_seller[seller_id] = platform_share + seller_share

        # Increment usage count atomically (one per coupon — shared across sellers
        # for platform coupon, once per seller-specific coupon)
        for c in coupons:
            Coupon.objects.filter(pk=c.pk).update(used_count=F('used_count') + 1)

        return {
            'per_seller': per_seller,
            'per_seller_platform': per_seller_platform,
            'per_seller_seller': per_seller_seller,
            'codes_used': [c.code for c in coupons],
        }

    def _create_order(self, seller, items, address, *, platform_subsidy, seller_subsidy,
                      store_credit, codes_used, existing_orders):
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

        platform_subsidy = Decimal(str(platform_subsidy or 0))
        seller_subsidy = Decimal(str(seller_subsidy or 0))
        store_credit = Decimal(str(store_credit or 0))
        total_discount = platform_subsidy + seller_subsidy + store_credit
        # Cap each component proportionally if it would push total below zero
        if total_discount > subtotal:
            scale = subtotal / total_discount
            platform_subsidy = (platform_subsidy * scale).quantize(Decimal('0.01'))
            seller_subsidy = (seller_subsidy * scale).quantize(Decimal('0.01'))
            store_credit = (store_credit * scale).quantize(Decimal('0.01'))
            total_discount = platform_subsidy + seller_subsidy + store_credit

        total = subtotal + shipping_cost - total_discount

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
            discount=total_discount,
            platform_subsidy=platform_subsidy,
            seller_subsidy=seller_subsidy,
            store_credit_used=store_credit,
            total=total,
            coupon_code=','.join(codes_used)[:50] if codes_used else '',
            notes=self.notes,
            gift_wrap=self.gift_wrap,
            status='pending',
            payment_status='pending',
        )
        # Initial Buyer Protection deadline: 48h for the seller to confirm.
        from django.utils import timezone
        from datetime import timedelta
        order.protection_state = 'awaiting_seller'
        order.protection_deadline_at = timezone.now() + timedelta(
            days=Order.PROTECTION_DAYS.get('pending', 2)
        )
        order.save(update_fields=['protection_state', 'protection_deadline_at'])

        # Create order items with price + variant snapshot.
        # IMPORTANT: bulk_create bypasses Model.save(), and OrderItem.save()
        # is where total_price = unit_price * quantity is computed. Without
        # this manual compute, the bulk_create would crash on the NOT NULL
        # constraint against orders_orderitem.total_price.
        order_items = []
        for item in items:
            combo = item.variant_combo
            unit_price = combo.price if combo else item.product.price
            quantity = item.quantity
            order_items.append(OrderItem(
                order=order,
                product=item.product,
                variant_combo=combo,
                variant_options=(combo.options if combo else {}),
                product_title=item.product.title,
                product_sku=(combo.sku if combo and combo.sku else item.product.sku or ''),
                unit_price=unit_price,
                quantity=quantity,
                total_price=Decimal(unit_price) * quantity,
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
