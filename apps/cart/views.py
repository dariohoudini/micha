from rest_framework import permissions, status
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
        cart, _ = Cart.objects.get_or_create(user=request.user)
        serializer = CartSerializer(cart, context={'request': request})
        return Response(serializer.data)


class AddToCartView(APIView):
    """POST /api/cart/add/ — Add item to cart."""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request):
        serializer = AddToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        product = get_object_or_404(Product, pk=data['product_id'])
        cart, _ = Cart.objects.get_or_create(user=request.user)

        cart_item, created = CartItem.objects.get_or_create(
            cart=cart, product=product,
            defaults={
                'quantity': data['quantity'],
                'variant_info': data.get('variant_info'),
            }
        )

        if not created:
            new_qty = cart_item.quantity + data['quantity']
            if new_qty > product.quantity:
                return Response(
                    {"detail": f"Only {product.quantity} items available."},
                    status=400
                )
            cart_item.quantity = new_qty
            cart_item.save()

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

        if not quantity or int(quantity) < 1:
            return Response({"detail": "Quantity must be at least 1."}, status=400)

        quantity = int(quantity)
        if quantity > item.product.quantity:
            return Response(
                {"detail": f"Only {item.product.quantity} items available."},
                status=400
            )

        item.quantity = quantity
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
            return Response({"detail": "Product is no longer available."}, status=400)

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
