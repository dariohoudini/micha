"""apps/waitlist/views.py — buyer self-serve."""
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import WaitlistEntry, WaitlistStatus
from . import service


class WaitlistView(APIView):
    """POST /waitlist/<product_id>/  — join
       DELETE /waitlist/<product_id>/ — leave
       GET    /waitlist/<product_id>/ — my entry + product waitlist size
    """
    permission_classes = [permissions.IsAuthenticated]

    def _product(self, product_id):
        from apps.products.models import Product
        return get_object_or_404(Product, pk=product_id)

    def post(self, request, product_id):
        product = self._product(product_id)
        variant_id = request.data.get('variant_combo_id')
        combo = None
        if variant_id:
            from apps.inventory.models import ProductVariantCombo
            combo = ProductVariantCombo.objects.filter(
                pk=variant_id, product=product, is_active=True,
            ).first()
            if combo is None:
                return Response({'error': 'invalid_variant'}, status=400)
        try:
            entry = service.join(request.user, product, variant_combo=combo)
        except service.WaitlistError as e:
            return Response({'error': 'waitlist_error',
                             'detail': str(e)}, status=400)
        return Response({
            'entry_id': entry.id,
            'position': entry.position,
            'status': entry.status,
            'joined_at': entry.joined_at,
            'waitlist_size': service.waitlist_size(product),
        }, status=201)

    def delete(self, request, product_id):
        product = self._product(product_id)
        ok = service.leave(request.user, product)
        return Response({'left': ok}, status=200 if ok else 404)

    def get(self, request, product_id):
        product = self._product(product_id)
        entry = WaitlistEntry.objects.filter(
            user=request.user, product=product,
            status=WaitlistStatus.WAITING,
        ).first()
        return Response({
            'is_subscribed': entry is not None,
            'position': entry.position if entry else None,
            'waitlist_size': service.waitlist_size(product),
        })


class MyWaitlistView(APIView):
    """GET /waitlist/me/ — my full waitlist (active + recent notifications)"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        rows = (
            WaitlistEntry.objects
            .filter(user=request.user)
            .select_related('product')
            .order_by('-joined_at')[:100]
            .values('id', 'product_id', 'status', 'position',
                    'joined_at', 'notified_at', 'converted_at')
        )
        return Response({'results': list(rows)})
