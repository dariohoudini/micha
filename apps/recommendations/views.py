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
        except Exception:
            pass
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

        # Flash sales — homepage's hottest cache key. EVERY anonymous
        # visit hits it; Black Friday will stampede when it expires.
        # Single-flight + SWR ensures one DB hit per cycle even under
        # ten-thousand-rps homepage load.
        from apps.core.cache_kit import cached_call

        def _build_flash_data():
            try:
                from apps.promotions.models import FlashSale
                flash_qs = FlashSale.objects.filter(
                    is_active=True, start_time__lte=now, end_time__gte=now,
                ).select_related('product')[:8]
                if not flash_qs.exists():
                    return None
                return {
                    'end_time': flash_qs.first().end_time.isoformat(),
                    'product_ids': [f.product_id for f in flash_qs],
                }
            except Exception:
                return None

        flash_data = cached_call(
            'homepage:flash_sales', _build_flash_data,
            ttl=300, swr_ttl=300,
            # No active flash sales is the common case during quiet
            # hours — short negative cache so we don't query 10k/s
            # during the lull either.
            negative_ttl=30,
        )

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
    Personalised feed filtered by user province for Angola relevance.
    Products from sellers in the same province shown first.
    """
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
    """
    POST /api/v1/recommendations/track/
    Records interaction AND immediately triggers taste profile update.
    Hyper-personalisation: feed updates within seconds of user action.
    """
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
    """GET/POST /api/v1/recommendations/viewing/<product_id>/

    Returns AliExpress-style social proof signals:
      viewing_now   - distinct sessions that pinged in the last 30s
      sold_recent   - orders (any status) containing this product in last 7 days
      in_carts      - distinct carts currently containing this product
      low_stock     - product.quantity if <= 10 else None
    """
    permission_classes = [permissions.AllowAny]
    WINDOW_SECONDS = 30
    SOLD_DAYS = 7

    def post(self, request, product_id):
        from apps.recommendations.models import StockUrgencySignal
        key = request.session.session_key or request.META.get('REMOTE_ADDR', 'anon')
        StockUrgencySignal.objects.update_or_create(product_id=product_id, session_key=key)
        return Response({'detail': 'ok'})

    def get(self, request, product_id):
        from apps.recommendations.models import StockUrgencySignal
        from apps.products.models import Product

        viewing_threshold = timezone.now() - timedelta(seconds=self.WINDOW_SECONDS)
        viewing_now = StockUrgencySignal.objects.filter(
            product_id=product_id, last_seen__gte=viewing_threshold
        ).count()

        sold_threshold = timezone.now() - timedelta(days=self.SOLD_DAYS)
        sold_recent = 0
        try:
            from apps.orders.models import OrderItem
            sold_recent = OrderItem.objects.filter(
                product_id=product_id,
                order__created_at__gte=sold_threshold,
            ).values('order_id').distinct().count()
        except Exception:
            pass

        in_carts = 0
        try:
            from apps.cart.models import CartItem
            in_carts = CartItem.objects.filter(
                product_id=product_id,
            ).values('cart_id').distinct().count()
        except Exception:
            pass

        low_stock = None
        try:
            qty = Product.objects.filter(pk=product_id).values_list('quantity', flat=True).first()
            if qty is not None and qty <= 10:
                low_stock = qty
        except Exception:
            pass

        return Response({
            'product_id': product_id,
            'viewing_now': viewing_now,
            'sold_recent': sold_recent,
            'sold_recent_days': self.SOLD_DAYS,
            'in_carts': in_carts,
            'low_stock': low_stock,
        })


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


class RecentlyViewedView(APIView):
    """GET /api/v1/recommendations/recently-viewed/?exclude=<id>&limit=N

    Last N distinct products viewed by the current user.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get(self, request):
        from apps.recommendations.models import ProductInteraction
        from apps.products.models import Product

        exclude_id = request.query_params.get('exclude')
        try:
            limit = min(int(request.query_params.get('limit', 12)), 24)
        except (TypeError, ValueError):
            limit = 12

        ix = ProductInteraction.objects.filter(
            user=request.user, type='view'
        ).order_by('-created_at').values_list('product_id', flat=True)

        seen = []
        for pid in ix.iterator():
            if exclude_id and str(pid) == str(exclude_id):
                continue
            if pid not in seen:
                seen.append(pid)
                if len(seen) >= limit:
                    break

        if not seen:
            return Response({'results': []})

        products = list(Product.objects.filter(
            pk__in=seen, is_active=True, is_archived=False
        ).select_related('store', 'category').prefetch_related('images'))
        by_id = {p.id: p for p in products}
        ordered = [by_id[pid] for pid in seen if pid in by_id]
        return Response({
            'results': SlimProductSerializer(ordered, many=True, context={'request': request}).data,
        })


class FrequentlyBoughtTogetherView(APIView):
    """GET /api/v1/recommendations/frequently-bought/<int:product_id>/

    Up to 8 other products that most often appear in orders alongside
    the given product. Cached 30 min.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request, product_id):
        from django.db.models import Count
        from apps.products.models import Product
        from apps.orders.models import OrderItem

        cache_key = f'fbt:{product_id}:v1'
        cached = cache.get(cache_key)
        if cached is not None:
            return Response({'results': cached})

        order_ids = OrderItem.objects.filter(
            product_id=product_id,
        ).values_list('order_id', flat=True).distinct()
        if not order_ids:
            cache.set(cache_key, [], timeout=600)
            return Response({'results': []})

        co_qs = (
            OrderItem.objects.filter(order_id__in=list(order_ids))
            .exclude(product_id=product_id)
            .values('product_id')
            .annotate(count=Count('order_id', distinct=True))
            .order_by('-count')[:24]
        )
        co_ids = [row['product_id'] for row in co_qs]
        if not co_ids:
            cache.set(cache_key, [], timeout=600)
            return Response({'results': []})

        products = list(Product.objects.filter(
            pk__in=co_ids, is_active=True, is_archived=False
        ).select_related('store', 'category').prefetch_related('images'))[:8]

        rank = {pid: i for i, pid in enumerate(co_ids)}
        products.sort(key=lambda p: rank.get(p.id, 999))

        data = SlimProductSerializer(products, many=True, context={'request': request}).data
        cache.set(cache_key, data, timeout=1800)
        return Response({'results': data})
