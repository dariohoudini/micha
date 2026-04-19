"""
Recommendation Views — Fixed for Scale
FIX: PersonalisedFeedView now reads from pre-computed Redis cache.
No more annotate(Sum()) correlated subquery disaster.
"""
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, serializers
from middleware.pagination import StandardPagination
from apps.users.permissions import IsNotSuspended


class SlimProductSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    slug = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    discount_percentage = serializers.FloatField()
    quantity = serializers.IntegerField()
    views = serializers.IntegerField()
    is_featured = serializers.BooleanField()
    condition = serializers.CharField()
    created_at = serializers.DateTimeField()
    store_name = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()
    thumbnail = serializers.SerializerMethodField()

    def get_store_name(self, obj):
        try: return obj.store.name
        except: return ''

    def get_category_name(self, obj):
        try: return obj.category.name if obj.category else ''
        except: return ''

    def get_thumbnail(self, obj):
        try:
            img = obj.images.first()
            if img and img.image:
                req = self.context.get('request')
                return req.build_absolute_uri(img.image.url) if req else img.image.url
        except: pass
        return None


class HomepageFeedView(APIView):
    """
    GET /api/v1/recommendations/homepage/
    Sections: flash sales, personalised, featured, trending, new arrivals.
    All sections use cached data — no live DB aggregation.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from apps.products.models import Product

        now = timezone.now()
        sections = []

        # Flash sales — cached 5 min
        flash_cache_key = 'homepage:flash_sales'
        flash_data = cache.get(flash_cache_key)
        if flash_data is None:
            try:
                from apps.promotions.models import FlashSale
                flash_qs = FlashSale.objects.filter(
                    is_active=True, start_time__lte=now, end_time__gte=now
                ).select_related('product')[:8]
                if flash_qs.exists():
                    flash_data = {
                        'end_time': flash_qs.first().end_time.isoformat(),
                        'product_ids': [f.product_id for f in flash_qs],
                    }
                    cache.set(flash_cache_key, flash_data, timeout=300)
            except Exception:
                flash_data = None

        if flash_data:
            products = Product.objects.filter(
                id__in=flash_data['product_ids'], is_active=True
            ).select_related('store', 'category').prefetch_related('images')
            sections.append({
                'id': 'flash_sales',
                'title': 'Flash sales',
                'show_countdown': True,
                'end_time': flash_data['end_time'],
                'products': SlimProductSerializer(products, many=True, context={'request': request}).data,
            })

        # Personalised feed (reads from pre-computed cache)
        if request.user.is_authenticated:
            from apps.recommendations.tasks import get_cached_feed
            personalised_qs = get_cached_feed(request.user.id)[:12]
            if personalised_qs:
                sections.append({
                    'id': 'for_you',
                    'title': 'Picked for you',
                    'subtitle': 'Based on your browsing',
                    'is_personalised': True,
                    'products': SlimProductSerializer(personalised_qs, many=True, context={'request': request}).data,
                })

        # Trending — cached 10 min
        trending_key = 'homepage:trending'
        trending_data = cache.get(trending_key)
        if trending_data is None:
            trending_qs = Product.objects.filter(
                is_active=True, is_archived=False
            ).order_by('-views').values_list('id', flat=True)[:16]
            trending_data = list(trending_qs)
            cache.set(trending_key, trending_data, timeout=600)

        trending_products = Product.objects.filter(
            id__in=trending_data, is_active=True
        ).select_related('store', 'category').prefetch_related('images')
        sections.append({
            'id': 'trending',
            'title': 'Trending now',
            'products': SlimProductSerializer(trending_products, many=True, context={'request': request}).data,
        })

        # New arrivals — cached 10 min
        new_key = 'homepage:new_arrivals'
        new_ids = cache.get(new_key)
        if new_ids is None:
            new_ids = list(Product.objects.filter(
                is_active=True, is_archived=False
            ).order_by('-created_at').values_list('id', flat=True)[:16])
            cache.set(new_key, new_ids, timeout=600)

        new_products = Product.objects.filter(
            id__in=new_ids, is_active=True
        ).select_related('store', 'category').prefetch_related('images')
        sections.append({
            'id': 'new_arrivals',
            'title': 'New arrivals',
            'products': SlimProductSerializer(new_products, many=True, context={'request': request}).data,
        })

        # Featured — cached 30 min
        featured_key = 'homepage:featured'
        featured_ids = cache.get(featured_key)
        if featured_ids is None:
            featured_ids = list(Product.objects.filter(
                is_active=True, is_featured=True
            ).order_by('-created_at').values_list('id', flat=True)[:8])
            cache.set(featured_key, featured_ids, timeout=1800)

        if featured_ids:
            featured_products = Product.objects.filter(
                id__in=featured_ids, is_active=True
            ).select_related('store', 'category').prefetch_related('images')
            sections.append({
                'id': 'featured',
                'title': 'Featured products',
                'products': SlimProductSerializer(featured_products, many=True, context={'request': request}).data,
            })

        return Response({'sections': sections, 'total': len(sections)})


class PersonalisedFeedView(APIView):
    """
    GET /api/v1/recommendations/feed/?page=1
    Reads from pre-computed Redis cache — no live DB query.
    Falls back to trending for new users.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get(self, request):
        from apps.recommendations.tasks import get_cached_feed

        page = max(1, int(request.query_params.get('page', 1)))
        page_size = 20
        offset = (page - 1) * page_size

        qs = get_cached_feed(request.user.id)
        products = list(qs[offset: offset + page_size])
        total = qs.count()

        return Response({
            'page': page,
            'page_size': page_size,
            'total': total,
            'total_pages': max(1, -(-total // page_size)),
            'is_personalised': bool(cache.get(f'feed:user:{request.user.id}')),
            'results': SlimProductSerializer(products, many=True, context={'request': request}).data,
        })


class TrackInteractionView(APIView):
    """POST /api/v1/recommendations/track/"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from apps.recommendations.models import ProductInteraction
        from apps.products.models import Product

        product_id = request.data.get('product_id')
        interaction_type = request.data.get('type', 'view')
        valid_types = ('view', 'wishlist', 'cart', 'purchase', 'review', 'share')

        if interaction_type not in valid_types:
            return Response({'error': 'validation_error', 'detail': f'type must be one of: {", ".join(valid_types)}'}, status=400)

        if not product_id:
            return Response({'error': 'validation_error', 'detail': 'product_id required.'}, status=400)

        try:
            product = Product.objects.get(pk=product_id, is_active=True)
        except Product.DoesNotExist:
            return Response({'error': 'not_found', 'detail': 'Product not found.'}, status=404)

        ProductInteraction.track(request.user, product, interaction_type)

        # Invalidate user's pre-computed feed so it gets refreshed
        if interaction_type in ('purchase', 'wishlist'):
            cache.delete(f'feed:user:{request.user.id}')

        return Response({'detail': 'Tracked.'})


class StockUrgencyView(APIView):
    """GET/POST /api/v1/recommendations/viewing/<product_id>/"""
    permission_classes = [permissions.AllowAny]
    WINDOW_SECONDS = 30

    def post(self, request, product_id):
        from apps.recommendations.models import StockUrgencySignal
        key = request.session.session_key or request.META.get('REMOTE_ADDR', 'anon')
        StockUrgencySignal.objects.update_or_create(product_id=product_id, session_key=key)
        return Response({'detail': 'ok'})

    def get(self, request, product_id):
        from apps.recommendations.models import StockUrgencySignal
        threshold = timezone.now() - timedelta(seconds=self.WINDOW_SECONDS)
        count = StockUrgencySignal.objects.filter(
            product_id=product_id, last_seen__gte=threshold
        ).count()
        return Response({'product_id': product_id, 'viewing_now': count})


class UserInterestView(APIView):
    """GET /api/v1/recommendations/interests/"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from apps.recommendations.models import UserInterest
        interests = UserInterest.objects.filter(
            user=request.user, score__gt=0
        ).select_related('category').order_by('-score')[:10]
        return Response({
            'interests': [
                {
                    'category': i.category.name,
                    'score': round(i.score, 1),
                    'views': i.view_count,
                    'wishlists': i.wishlist_count,
                    'purchases': i.purchase_count,
                }
                for i in interests
            ]
        })


class PriceAlertView(APIView):
    """GET/POST /api/v1/recommendations/price-alerts/"""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get(self, request):
        from apps.recommendations.models import PriceAlert
        alerts = PriceAlert.objects.filter(user=request.user, is_triggered=False).select_related('product')
        return Response([{
            'id': a.id,
            'product_id': a.product_id,
            'product_title': a.product.title,
            'current_price': str(a.product.price),
            'target_price': str(a.target_price),
        } for a in alerts])

    def post(self, request):
        from apps.recommendations.models import PriceAlert
        from apps.products.models import Product
        product_id = request.data.get('product_id')
        target_price = request.data.get('target_price')
        if not product_id or target_price is None:
            return Response({'error': 'validation_error', 'detail': 'product_id and target_price required.'}, status=400)
        product = get_object_or_404(Product, pk=product_id, is_active=True)
        alert, created = PriceAlert.objects.get_or_create(
            user=request.user, product=product,
            defaults={'target_price': target_price, 'original_price': product.price}
        )
        return Response({'detail': 'Price alert set.' if created else 'Already exists.'}, status=201 if created else 200)


class BackInStockView(APIView):
    """POST /api/v1/recommendations/back-in-stock/"""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request):
        from apps.recommendations.models import BackInStockAlert
        from apps.products.models import Product
        product_id = request.data.get('product_id')
        if not product_id:
            return Response({'error': 'validation_error', 'detail': 'product_id required.'}, status=400)
        product = get_object_or_404(Product, pk=product_id)
        if product.quantity > 0:
            return Response({'error': 'in_stock', 'detail': 'Product is already in stock.'}, status=400)
        _, created = BackInStockAlert.objects.get_or_create(user=request.user, product=product)
        return Response({'detail': "You'll be notified when this is back." if created else 'Already subscribed.'}, status=201 if created else 200)
