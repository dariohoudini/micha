from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from .models import Wishlist, WishlistItem
from apps.products.models import Product
from apps.products.serializers import PublicProductSerializer
from apps.users.permissions import IsNotSuspended


class WishlistView(APIView):
    """GET /api/wishlist/ — View full wishlist."""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get(self, request):
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        items = wishlist.items.select_related('product').all()
        data = []
        for item in items:
            data.append({
                'id': item.id,
                'added_at': item.added_at,
                'product': PublicProductSerializer(item.product).data,
            })
        return Response({'count': len(data), 'items': data})


class AddToWishlistView(APIView):
    """POST /api/wishlist/add/ — Add product to wishlist. { product_id }"""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request):
        product_id = request.data.get('product_id')
        product = get_object_or_404(Product, pk=product_id, is_active=True)
        wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
        _, created = WishlistItem.objects.get_or_create(
            wishlist=wishlist, product=product
        )
        if not created:
            return Response({"detail": "Already in wishlist."}, status=200)
        return Response({"detail": "Added to wishlist."}, status=201)


class RemoveFromWishlistView(APIView):
    """DELETE /api/wishlist/items/<id>/ — Remove item from wishlist."""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def delete(self, request, item_id):
        wishlist = get_object_or_404(Wishlist, user=request.user)
        item = get_object_or_404(WishlistItem, pk=item_id, wishlist=wishlist)
        item.delete()
        return Response({"detail": "Removed from wishlist."})


class ClearWishlistView(APIView):
    """DELETE /api/wishlist/clear/ — Clear entire wishlist."""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def delete(self, request):
        wishlist = get_object_or_404(Wishlist, user=request.user)
        wishlist.items.all().delete()
        return Response({"detail": "Wishlist cleared."})
