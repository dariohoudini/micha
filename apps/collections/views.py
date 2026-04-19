from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, serializers, generics

from .models import (
    ProductCollection, ProductOfTheDay, SellerSpotlight,
    PlatformAnnouncement, PriceHistory,
)
from apps.users.permissions import IsAdminOrSuperuser


class CollectionSerializer(serializers.ModelSerializer):
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = ProductCollection
        fields = [
            'id', 'name', 'slug', 'description', 'banner_image',
            'is_featured', 'valid_from', 'valid_until', 'product_count',
        ]

    def get_product_count(self, obj):
        return obj.products.filter(is_active=True, is_archived=False).count()


class CollectionListView(generics.ListAPIView):
    """GET /api/collections/ — All live collections."""
    serializer_class = CollectionSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return [c for c in ProductCollection.objects.filter(is_active=True) if c.is_live]


class CollectionDetailView(APIView):
    """GET /api/collections/<slug>/ — Collection + its products."""
    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        from apps.recommendations.views import SlimProductSerializer
        col = get_object_or_404(ProductCollection, slug=slug, is_active=True)
        if not col.is_live:
            return Response({'detail': 'Collection not currently active.'}, status=404)
        products = col.products.filter(is_active=True, is_archived=False)
        return Response({
            'id': col.id,
            'name': col.name,
            'description': col.description,
            'banner_image': col.banner_image.url if col.banner_image else None,
            'valid_until': col.valid_until,
            'product_count': products.count(),
            'products': SlimProductSerializer(
                products, many=True, context={'request': request}
            ).data,
        })


class AdminCollectionCreateView(generics.CreateAPIView):
    """POST /api/collections/admin/ — Create collection."""
    serializer_class = CollectionSerializer
    permission_classes = [IsAdminOrSuperuser]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ProductOfTheDayView(APIView):
    """GET /api/collections/product-of-day/ — Today's featured product."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from apps.recommendations.views import SlimProductSerializer
        today = timezone.now().date()
        try:
            potd = ProductOfTheDay.objects.select_related('product').get(date=today)
            return Response({
                'date': str(potd.date),
                'headline': potd.headline,
                'product': SlimProductSerializer(potd.product, context={'request': request}).data,
            })
        except ProductOfTheDay.DoesNotExist:
            from apps.products.models import Product
            product = Product.objects.filter(
                is_active=True, is_featured=True
            ).order_by('-views').first()
            if product:
                return Response({
                    'date': str(today),
                    'headline': 'Featured today',
                    'product': SlimProductSerializer(product, context={'request': request}).data,
                })
            return Response({'detail': 'No featured product for today.'}, status=404)


class AdminSetProductOfDayView(APIView):
    """POST /api/collections/admin/product-of-day/ — { product_id, date?, headline? }"""
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request):
        from apps.products.models import Product
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({'detail': 'product_id required.'}, status=400)
        product = get_object_or_404(Product, pk=product_id, is_active=True)
        date_str = request.data.get('date', str(timezone.now().date()))
        potd, created = ProductOfTheDay.objects.update_or_create(
            date=date_str,
            defaults={
                'product': product,
                'headline': request.data.get('headline', ''),
                'created_by': request.user,
            },
        )
        return Response({
            'detail': f"Product of the day {'set' if created else 'updated'}.",
            'date': str(potd.date),
            'product': product.title,
        })


class SellerSpotlightView(APIView):
    """GET /api/collections/seller-spotlight/ — Active seller spotlights."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        today = timezone.now().date()
        spotlights = SellerSpotlight.objects.filter(
            is_active=True,
            valid_from__lte=today,
        ).filter(
            models.Q(valid_until__isnull=True) | models.Q(valid_until__gte=today)
        ).select_related('seller', 'seller__profile')[:5]

        data = []
        for s in spotlights:
            name = ''
            try:
                name = s.seller.profile.full_name
            except Exception:
                name = s.seller.email
            data.append({
                'seller_id': s.seller_id,
                'seller_name': name,
                'headline': s.headline,
                'description': s.description,
            })
        return Response({'spotlights': data})


class PlatformAnnouncementView(APIView):
    """GET /api/collections/announcements/ — Active platform banners."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        announcements = [
            {
                'id': a.id, 'title': a.title, 'message': a.message,
                'type': a.type, 'cta_text': a.cta_text, 'cta_link': a.cta_link,
            }
            for a in PlatformAnnouncement.objects.all()
            if a.is_live
        ][:3]
        return Response({'announcements': announcements})


class PriceHistoryView(APIView):
    """GET /api/collections/price-history/<product_id>/?days=90 — Price chart data."""
    permission_classes = [permissions.AllowAny]

    def get(self, request, product_id):
        days = int(request.query_params.get('days', 90))
        from apps.products.models import Product
        product = get_object_or_404(Product, pk=product_id)
        history = PriceHistory.objects.filter(
            product=product
        ).order_by('recorded_at')[:days]
        return Response({
            'product_id': product_id,
            'product_title': product.title,
            'current_price': str(product.price),
            'history': [
                {'price': str(h.price), 'date': str(h.recorded_at.date())}
                for h in history
            ],
        })


# Fix missing import
from django.db import models
