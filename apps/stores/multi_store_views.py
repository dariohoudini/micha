"""
apps/stores/multi_store_views.py

Multi-store management API endpoints.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from django.utils.text import slugify
from django.utils import timezone
from datetime import timedelta
import uuid


class MyStoresView(APIView):
    """
    GET  /api/v1/stores/my-stores/     — List all seller's stores
    POST /api/v1/stores/my-stores/     — Create new store
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .multi_store_models import Store, SellerActiveStore

        stores = Store.objects.filter(seller=request.user, is_active=True)

        # Get active store session
        try:
            active_id = str(request.user.active_store_session.active_store_id)
        except Exception:
            active_id = None

        data = []
        for store in stores:
            data.append({
                'id': str(store.id),
                'name': store.name,
                'slug': store.slug,
                'tagline': store.tagline,
                'logo': request.build_absolute_uri(store.logo.url) if store.logo else None,
                'banner': request.build_absolute_uri(store.banner.url) if store.banner else None,
                'primary_color': store.primary_color,
                'province': store.province,
                'primary_category': store.primary_category,
                'is_primary': store.is_primary,
                'is_active_session': str(store.id) == active_id,
                'stats': {
                    'total_products': store.total_products,
                    'total_sales': store.total_sales,
                    'total_revenue': float(store.total_revenue),
                    'avg_rating': store.avg_rating,
                    'total_reviews': store.total_reviews,
                },
                'created_at': store.created_at,
            })

        return Response({
            'stores': data,
            'total': len(data),
            'active_store_id': active_id,
            'can_create_more': Store.can_create_store(request.user)[0],
        })

    def post(self, request):
        from .multi_store_models import Store

        # Check subscription limit
        can_create, reason = Store.can_create_store(request.user)
        if not can_create:
            return Response({'error': reason}, status=status.HTTP_403_FORBIDDEN)

        name = request.data.get('name', '').strip()
        if not name or len(name) < 3:
            return Response({'error': 'Nome da loja deve ter pelo menos 3 caracteres.'}, status=400)

        # Generate unique slug
        base_slug = slugify(name)
        slug = base_slug
        counter = 1
        while Store.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1

        is_first_store = not Store.objects.filter(seller=request.user).exists()

        store = Store.objects.create(
            seller=request.user,
            name=name,
            slug=slug,
            tagline=request.data.get('tagline', ''),
            province=request.data.get('province', 'Luanda'),
            primary_category=request.data.get('primary_category', ''),
            is_primary=is_first_store,
        )

        # Auto-switch to new store
        from .multi_store_models import SellerActiveStore
        SellerActiveStore.objects.update_or_create(
            seller=request.user,
            defaults={'active_store': store}
        )

        return Response({
            'id': str(store.id),
            'name': store.name,
            'slug': store.slug,
            'message': f"Loja '{store.name}' criada com sucesso!",
        }, status=status.HTTP_201_CREATED)


class SwitchStoreView(APIView):
    """
    POST /api/v1/stores/switch/<store_id>/
    Switches the seller's active store session.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, store_id):
        from .multi_store_models import Store, SellerActiveStore

        try:
            store = Store.objects.get(id=store_id, seller=request.user, is_active=True)
        except Store.DoesNotExist:
            return Response({'error': 'Loja não encontrada.'}, status=404)

        SellerActiveStore.objects.update_or_create(
            seller=request.user,
            defaults={'active_store': store}
        )

        return Response({
            'active_store_id': str(store.id),
            'active_store_name': store.name,
            'message': f"A gerir: {store.name}",
        })


class StoreDetailView(APIView):
    """
    GET   /api/v1/stores/<store_id>/settings/  — Get store settings
    PATCH /api/v1/stores/<store_id>/settings/  — Update store settings
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, store_id):
        from .multi_store_models import Store
        try:
            store = Store.objects.get(id=store_id, seller=request.user)
        except Store.DoesNotExist:
            return Response({'error': 'Loja não encontrada.'}, status=404)

        return Response({
            'id': str(store.id),
            'name': store.name,
            'slug': store.slug,
            'tagline': store.tagline,
            'description': store.description,
            'province': store.province,
            'address': store.address,
            'phone': store.phone,
            'whatsapp': store.whatsapp,
            'primary_category': store.primary_category,
            'primary_color': store.primary_color,
            'return_policy': store.return_policy,
            'shipping_policy': store.shipping_policy,
            'logo': request.build_absolute_uri(store.logo.url) if store.logo else None,
            'banner': request.build_absolute_uri(store.banner.url) if store.banner else None,
        })

    def patch(self, request, store_id):
        from .multi_store_models import Store
        try:
            store = Store.objects.get(id=store_id, seller=request.user)
        except Store.DoesNotExist:
            return Response({'error': 'Loja não encontrada.'}, status=404)

        # Allowlist — only permit safe store-profile fields. Internal
        # / privilege fields (owner, is_verified_seller, commission_rate,
        # etc.) MUST NOT be settable via this endpoint regardless of
        # what the client posts. This is the only authoritative list.
        ALLOWED_STORE_FIELDS = {
            'name', 'tagline', 'description', 'province', 'address',
            'phone', 'whatsapp', 'primary_category', 'primary_color',
            'return_policy', 'shipping_policy', 'city', 'is_open',
        }
        for field, value in request.data.items():
            if field not in ALLOWED_STORE_FIELDS:
                continue
            setattr(store, field, value)

        if 'logo' in request.FILES:
            store.logo = request.FILES['logo']
        if 'banner' in request.FILES:
            store.banner = request.FILES['banner']

        store.save()
        return Response({'message': 'Loja actualizada com sucesso.'})


class StoreAnalyticsView(APIView):
    """
    GET /api/v1/stores/<store_id>/analytics/?period=7
    Per-store analytics data.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, store_id):
        from .multi_store_models import Store, StoreAnalyticsSnapshot
        from django.db.models import Sum, Avg

        try:
            store = Store.objects.get(id=store_id, seller=request.user)
        except Store.DoesNotExist:
            return Response({'error': 'Loja não encontrada.'}, status=404)

        period = int(request.query_params.get('period', 7))
        since = timezone.now().date() - timedelta(days=period)

        snapshots = StoreAnalyticsSnapshot.objects.filter(
            store=store, date__gte=since
        ).order_by('date')

        chart_data = [{
            'date': s.date.isoformat(),
            'day': s.date.strftime('%a'),
            'revenue': float(s.revenue),
            'orders': s.orders,
        } for s in snapshots]

        totals = snapshots.aggregate(
            total_revenue=Sum('revenue'),
            total_orders=Sum('orders'),
            total_views=Sum('page_views'),
        )

        return Response({
            'store': {'id': str(store.id), 'name': store.name},
            'period': period,
            'chart': chart_data,
            'totals': {
                'revenue': float(totals['total_revenue'] or 0),
                'orders': totals['total_orders'] or 0,
                'views': totals['total_views'] or 0,
                'avg_rating': store.avg_rating,
                'total_reviews': store.total_reviews,
            },
        })
