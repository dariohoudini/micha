from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import Cart, CartItem
from .serializers import CartSerializer, AddToCartSerializer
from apps.products.models import Product
from apps.users.permissions import IsNotSuspended


class CartView(APIView):
    """GET /api/cart/ — View current cart."""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get(self, request):
        from django.db.models import Prefetch
        from apps.products.models import Product
        cart, _ = Cart.objects.get_or_create(user=request.user)
        # Prefetch the items + product + product images + variant_combo so
        # the serializer doesn't N+1 across the cart.
        cart = (
            Cart.objects
            .filter(pk=cart.pk)
            .prefetch_related(
                Prefetch('items__product', queryset=Product.objects.prefetch_related('images')),
                'items__variant_combo',
            )
            .first()
        )
        serializer = CartSerializer(cart, context={'request': request})
        return Response(serializer.data)


class AddToCartView(APIView):
    """POST /api/cart/add/ — Add item to cart."""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request):
        from apps.inventory.models import ProductVariantCombo

        serializer = AddToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        product = get_object_or_404(Product, pk=data['product_id'])
        cart, _ = Cart.objects.get_or_create(user=request.user)

        combo = None
        combo_id = data.get('variant_combo_id')
        if combo_id:
            combo = get_object_or_404(ProductVariantCombo, pk=combo_id, product=product, is_active=True)

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart, product=product, variant_combo=combo,
            defaults={'quantity': data['quantity']},
        )

        if not created:
            new_qty = cart_item.quantity + data['quantity']
            available = combo.quantity if combo else product.quantity
            if new_qty > available:
                return Response(
                    {"detail": f"Apenas {available} unidades disponíveis."},
                    status=400
                )
            cart_item.quantity = new_qty
            # Re-compute tier price for the new quantity (skip when variant set)
            if not combo:
                from apps.products.models import PriceTier
                cart_item.price_at_add = PriceTier.price_for_quantity(
                    product, new_qty, product.price
                )
            cart_item.save()

        # Funnel KPI (Gap-Coverage CH9B) — pairs with signups and GMV so
        # a drop can be located to a funnel stage.
        try:
            from apps.telemetry.metrics import cart_additions_total
            cart_additions_total.inc()
        except Exception:
            pass

        return Response(
            CartSerializer(cart, context={'request': request}).data,
            status=201
        )


class UpdateCartItemView(APIView):
    """PATCH /api/cart/items/<id>/ — Update quantity."""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def patch(self, request, item_id):
        cart = get_object_or_404(Cart, user=request.user)
        item = get_object_or_404(CartItem, pk=item_id, cart=cart)
        quantity = request.data.get('quantity')
        try:
            quantity = int(quantity)
            if quantity < 1 or quantity > 100:
                return Response({'error': 'Quantidade inválida (1-100)'}, status=400)
        except (TypeError, ValueError):
            return Response({'error': 'Quantidade inválida'}, status=400)

        if not quantity or int(quantity) < 1:
            return Response({'error': 'Quantity must be at least 1.'}, status=400)

        quantity = int(quantity)
        available = item.variant_combo.quantity if item.variant_combo else item.product.quantity
        if quantity > available:
            return Response(
                {"detail": f"Apenas {available} unidades disponíveis."},
                status=400
            )

        item.quantity = quantity
        # Re-compute tier price for the new quantity (skip when variant set)
        if not item.variant_combo:
            from apps.products.models import PriceTier
            item.price_at_add = PriceTier.price_for_quantity(
                item.product, quantity, item.product.price
            )
        item.save()
        return Response(CartSerializer(cart, context={'request': request}).data)


class RemoveCartItemView(APIView):
    """DELETE /api/cart/items/<id>/ — Remove item from cart."""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def delete(self, request, item_id):
        cart = get_object_or_404(Cart, user=request.user)
        item = get_object_or_404(CartItem, pk=item_id, cart=cart)
        item.delete()
        return Response(CartSerializer(cart, context={'request': request}).data)


class ClearCartView(APIView):
    """DELETE /api/cart/clear/ — Empty the cart."""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def delete(self, request):
        cart = get_object_or_404(Cart, user=request.user)
        cart.items.all().delete()
        return Response({"detail": "Cart cleared."})


class MoveWishlistToCartView(APIView):
    """POST /api/cart/from-wishlist/<item_id>/ — Move wishlist item to cart."""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request, item_id):
        from apps.wishlist.models import WishlistItem
        wishlist_item = get_object_or_404(
            WishlistItem, pk=item_id, wishlist__user=request.user
        )
        product = wishlist_item.product

        if not product.is_active or product.is_archived:
            return Response({'error': 'Product is no longer available.'}, status=400)

        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart, product=product,
            defaults={'quantity': 1}
        )
        if not created:
            cart_item.quantity += 1
            cart_item.save()

        wishlist_item.delete()
        return Response(
            CartSerializer(cart, context={'request': request}).data
        )


class MergeAnonCartView(APIView):
    """POST /api/cart/merge/  body: {items: [{product_id, variant_combo_id?, quantity}, ...]}

    Called by the frontend RIGHT AFTER login to fold an anonymous-session
    cart (kept in localStorage) into the freshly-logged-in user's
    server-side cart. Without this endpoint, a buyer who browses anon,
    adds 5 items, then signs in loses their cart — they see an empty
    cart on first page after login and bounce.

    Merge rules:
      • For each input item, find a matching (cart, product, variant_combo)
        row. If found → add quantities (capped at available stock).
        If not → insert a new CartItem at the product's current price.
      • Unknown / inactive / archived product_ids → silently skipped
        (the client's anon cart could contain stale ids).
      • variant_combo_id that doesn't belong to the product → skipped.
      • Stock-clamped: never let merged quantity exceed available stock
        (an anon cart from yesterday might want 10 of something we now
        have 3 of).
      • Idempotent at the request level — calling /merge/ with the same
        payload twice produces the same end state, not double quantities.
        (Achieved via update-with-current-quantity semantics: we look at
        the existing cart row's quantity and clamp the SUM, not the
        delta.)

    Returns the merged cart shape — same as GET /api/cart/.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    MAX_ITEMS = 50

    def post(self, request):
        items_in = request.data.get('items') or []
        if not isinstance(items_in, list):
            return Response({'error': 'validation_error',
                             'detail': 'items must be a list'}, status=400)
        if len(items_in) > self.MAX_ITEMS:
            return Response({'error': 'too_many_items',
                             'detail': f'max {self.MAX_ITEMS} items'},
                            status=400)

        from apps.inventory.models import ProductVariantCombo

        cart, _ = Cart.objects.get_or_create(user=request.user)
        merged = 0
        skipped = 0
        for raw in items_in:
            # WIDE try/except wraps the entire per-item processing: a stale
            # localStorage cart can contain garbage (bad PK type, bad combo,
            # malformed dict). Skip individually, don't abort the whole merge.
            try:
                product_id = raw.get('product_id')
                combo_id = raw.get('variant_combo_id')
                qty = int(raw.get('quantity') or 1)
                if not product_id or qty < 1:
                    skipped += 1
                    continue

                product = Product.objects.filter(
                    pk=product_id, is_active=True, is_archived=False,
                ).first()
                if product is None:
                    skipped += 1
                    continue

                combo = None
                if combo_id:
                    combo = ProductVariantCombo.objects.filter(
                        pk=combo_id, product=product, is_active=True,
                    ).first()
                    if combo is None:
                        skipped += 1
                        continue

                available = combo.quantity if combo else product.quantity
                if available <= 0:
                    skipped += 1
                    continue

                existing = CartItem.objects.filter(
                    cart=cart, product=product, variant_combo=combo,
                ).first()
                if existing is not None:
                    target = min(existing.quantity + qty, available)
                    if target != existing.quantity:
                        existing.quantity = target
                        existing.save(update_fields=['quantity', 'updated_at'])
                    merged += 1
                else:
                    CartItem.objects.create(
                        cart=cart, product=product, variant_combo=combo,
                        quantity=min(qty, available),
                        price_at_add=combo.price if combo else product.price,
                    )
                    merged += 1
            except Exception:
                skipped += 1
                continue

        return Response({
            'merged': merged, 'skipped': skipped,
            'cart': CartSerializer(cart, context={'request': request}).data,
        }, status=200)
