"""
apps/ai_engine/views.py — MICHA Express AI Engine v2
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework import status
from django.utils import timezone
from django.core.cache import cache

from .services import (
    TasteProfileService, RecommendationService, SmartSearchService,
    PriceDropService, SizeRecommendationService, FlashSaleTargetingService,
    AIChatService, EmbeddingService,
)
from .serializers import (
    OnboardingQuizSerializer, TasteProfileSerializer,
    SizeProfileSerializer, NotificationPreferenceSerializer,
)
from .models import (
    UserTasteProfile, SizeProfile, NotificationPreference,
    AIConversation, SearchQuery,
)


class OnboardingQuizView(APIView):
    """
    POST /api/ai/onboarding-quiz/   — Submit quiz, seed profile
    GET  /api/ai/onboarding-quiz/   — Check completion status
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = OnboardingQuizSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        profile = TasteProfileService.update_from_onboarding(
            user=request.user,
            quiz_data=serializer.validated_data,
        )
        return Response({
            'message': 'Perfil criado com sucesso!' if request.data.get('language') != 'en'
                       else 'Profile created successfully!',
            'quiz_completed': True,
            'profile_confidence': profile.profile_confidence,
            'algorithm': profile.active_algorithm,
        })

    def get(self, request):
        try:
            profile = UserTasteProfile.objects.get(user=request.user)
            return Response({
                'quiz_completed': profile.quiz_completed,
                'profile_confidence': profile.profile_confidence,
                'algorithm': profile.active_algorithm,
                'preferred_categories': profile.preferred_categories,
            })
        except UserTasteProfile.DoesNotExist:
            return Response({'quiz_completed': False, 'profile_confidence': 0.0})


class PersonalisedFeedView(APIView):
    """
    GET /api/ai/feed/?limit=20&offset=0
    Returns personalised product IDs ranked by AI score.
    Frontend fetches full product data from /api/products/?ids=...
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = min(int(request.query_params.get('limit', 20)), 50)
        offset = int(request.query_params.get('offset', 0))

        result = RecommendationService.get_home_feed(
            user=request.user, limit=limit, offset=offset,
        )

        # Track feed load as view event
        TasteProfileService.record_event(
            user=request.user,
            event_type='view',
            source='home_feed',
        )

        # Get profile info for frontend
        try:
            profile = UserTasteProfile.objects.get(user=request.user)
            profile_data = {
                'confidence': profile.profile_confidence,
                'algorithm': profile.active_algorithm,
                'quiz_completed': profile.quiz_completed,
            }
        except UserTasteProfile.DoesNotExist:
            profile_data = {'confidence': 0.0, 'algorithm': 'cold_start', 'quiz_completed': False}

        return Response({**result, 'profile': profile_data})


class SimilarProductsView(APIView):
    """GET /api/ai/similar/<product_id>/?limit=10"""
    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        limit = min(int(request.query_params.get('limit', 10)), 20)
        result = RecommendationService.get_similar_products(
            product_id=product_id,
            user=request.user,
            limit=limit,
        )
        return Response(result)


class TrackEventView(APIView):
    """
    POST /api/ai/event/
    Fire-and-forget behavioral tracking. Always returns 200.

    Body: {
        event_type: str,
        product_id: uuid (optional),
        seller_id: uuid (optional),
        category: str (optional),
        price: number (optional),
        source: str (optional),
        dwell_seconds: int (optional),
        session_id: str (optional),
    }
    """
    permission_classes = [IsAuthenticated]

    ALLOWED_EVENTS = {
        'view', 'dwell_10', 'dwell_30', 'dwell_60',
        'scroll_images', 'read_reviews',
        'wishlist_add', 'wishlist_remove',
        'cart_add', 'cart_remove',
        'share', 'click_rec', 'search_click',
        'checkout_start', 'bounce',
    }

    def post(self, request):
        event_type = request.data.get('event_type', '')
        if event_type not in self.ALLOWED_EVENTS:
            return Response({'status': 'ignored', 'reason': 'unknown event type'})

        TasteProfileService.record_event(
            user=request.user,
            event_type=event_type,
            product_id=request.data.get('product_id'),
            seller_id=request.data.get('seller_id'),
            category=request.data.get('category', ''),
            price=request.data.get('price'),
            source=request.data.get('source', ''),
            session_id=request.data.get('session_id', ''),
            dwell_seconds=request.data.get('dwell_seconds'),
            scroll_depth_pct=request.data.get('scroll_depth_pct'),
        )
        return Response({'status': 'ok'})


class SmartSearchView(APIView):
    """
    GET /api/ai/search/?q=vestido+para+casamento+barato&limit=20

    GPT-4o-mini powered NLP search.
    Returns:
    - Parsed intent (category, price range, occasion, etc.)
    - Ranked product results
    - Zero-results suggestions if no matches
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.query_params.get('q', '').strip()
        if not query or len(query) < 2:
            return Response({'error': 'Query must be at least 2 characters'}, status=400)
        if len(query) > 200:
            return Response({'error': 'Query too long'}, status=400)

        limit = min(int(request.query_params.get('limit', 20)), 50)

        # NLP parse
        parsed = SmartSearchService.parse_query(query, user=request.user)
        filters = {
            'category': parsed.get('category'),
            'price_max': parsed.get('price_max') or parsed.get('user_price_max'),
            'price_min': parsed.get('price_min'),
        }
        filters = {k: v for k, v in filters.items() if v is not None}

        # Execute search
        products, total = self._search_products(query, filters, parsed, request.user, limit)

        return Response({
            'query': {
                'raw': query,
                'language': parsed.get('language', 'pt'),
                'parsed': {
                    'category': parsed.get('category'),
                    'price_max': parsed.get('price_max'),
                    'price_min': parsed.get('price_min'),
                    'occasion': parsed.get('occasion'),
                    'style': parsed.get('style'),
                    'color': parsed.get('color'),
                    'keywords': parsed.get('keywords', []),
                },
                'parse_method': parsed.get('parse_method', 'unknown'),
            },
            'products': products,
            'total': total,
            'zero_results': total == 0,
            'suggestions': self._get_suggestions(parsed) if total == 0 else [],
        })

    def _search_products(self, query, filters, parsed, user, limit):
        try:
            from apps.products.models import Product
            from django.db.models import Q

            qs = Product.objects.filter(is_active=True)

            if filters.get('category'):
                qs = qs.filter(category=filters['category'])
            if filters.get('price_max'):
                qs = qs.filter(price__lte=filters['price_max'])
            if filters.get('price_min'):
                qs = qs.filter(price__gte=filters['price_min'])

            keywords = parsed.get('keywords', [])
            if keywords:
                q_filter = Q()
                for kw in keywords[:5]:
                    q_filter |= Q(name__icontains=kw) | Q(description__icontains=kw)
                qs = qs.filter(q_filter)

            total = qs.count()
            products = list(qs.values('id', 'name', 'price', 'category')[:limit])
            return products, total
        except Exception as e:
            return [], 0

    def _get_suggestions(self, parsed) -> list:
        """When zero results, suggest broader searches."""
        suggestions = []
        if parsed.get('price_max'):
            suggestions.append({'type': 'remove_price_filter', 'label': 'Remover filtro de preço'})
        if parsed.get('category'):
            suggestions.append({'type': 'broader_category', 'label': 'Ver toda a categoria'})
        return suggestions


class AIChatView(APIView):
    """
    POST /api/ai/chat/start/         — Start new conversation
    POST /api/ai/chat/<id>/message/  — Send message to existing conversation
    GET  /api/ai/chat/<id>/          — Get conversation history
    """
    permission_classes = [IsAuthenticated]

    def post_start(self, request):
        product_id = request.data.get('product_id')
        product_name = request.data.get('product_name', '')
        language = request.data.get('language', 'pt')

        conv = AIChatService.get_or_create_conversation(
            user=request.user,
            product_id=product_id,
            product_name=product_name,
            language=language,
        )

        # Send initial greeting
        greeting = (
            "Olá! Sou o assistente de compras da MICHA Express. Como posso ajudá-lo?"
            if language == 'pt' else
            "Hello! I'm the MICHA Express shopping assistant. How can I help you?"
        )

        return Response({
            'conversation_id': str(conv.id),
            'greeting': greeting,
            'product_context': product_name or None,
        })

    def post_message(self, request, conversation_id):
        user_message = request.data.get('message', '').strip()
        if not user_message:
            return Response({'error': 'Message cannot be empty'}, status=400)
        if len(user_message) > 1000:
            return Response({'error': 'Message too long'}, status=400)

        # Rate limit: 20 messages per minute
        rate_key = f"chat_rate:{request.user.id}"
        count = cache.get(rate_key, 0)
        if count >= 20:
            return Response({'error': 'Too many messages. Please wait a moment.'}, status=429)
        cache.set(rate_key, count + 1, timeout=60)

        result = AIChatService.send_message(conversation_id, user_message)

        # Track that user engaged with AI chat
        TasteProfileService.record_event(
            user=request.user,
            event_type='chat_start',
            source='ai_assistant',
        )

        return Response(result)


class AIChatStartView(AIChatView):
    def post(self, request):
        return self.post_start(request)


class AIChatMessageView(AIChatView):
    def post(self, request, conversation_id):
        return self.post_message(request, conversation_id)

    def get(self, request, conversation_id):
        try:
            conv = AIConversation.objects.get(id=conversation_id, user=request.user)
            return Response({
                'conversation_id': str(conv.id),
                'messages': conv.messages,
                'product_name': conv.product_name,
                'created_at': conv.created_at,
            })
        except AIConversation.DoesNotExist:
            return Response({'error': 'Conversation not found'}, status=404)


class WatchPriceView(APIView):
    """
    POST   /api/ai/price-watch/              — Start watching
    DELETE /api/ai/price-watch/<product_id>/ — Stop watching
    GET    /api/ai/price-watch/              — List active watches
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import PriceDropAlert
        alerts = PriceDropAlert.objects.filter(
            user=request.user, status='watching'
        ).values('product_id', 'product_name', 'price_when_added', 'current_price', 'alert_threshold_pct')
        return Response(list(alerts))

    def post(self, request):
        product_id = request.data.get('product_id')
        price = request.data.get('price')
        product_name = request.data.get('product_name', '')
        threshold = float(request.data.get('threshold_pct', 10.0))

        if not product_id or not price:
            return Response({'error': 'product_id and price required'}, status=400)

        alert = PriceDropService.watch_product(
            user=request.user,
            product_id=product_id,
            current_price=price,
            product_name=product_name,
            threshold_pct=threshold,
        )
        return Response({
            'watching': True,
            'threshold_pct': alert.alert_threshold_pct,
            'price_when_added': float(alert.price_when_added),
        })

    def delete(self, request, product_id):
        PriceDropService.unwatch_product(request.user, product_id)
        return Response({'watching': False})


class SizeRecommendationView(APIView):
    """GET /api/ai/size/?category=Moda&product_id=uuid"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        category = request.query_params.get('category', 'Moda')
        product_id = request.query_params.get('product_id')
        result = SizeRecommendationService.get_recommendation(
            user=request.user,
            category=category,
            product_id=product_id,
        )
        return Response(result)


class SizeProfileView(APIView):
    """GET/PUT /api/ai/size-profile/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile, _ = SizeProfile.objects.get_or_create(user=request.user)
        return Response(SizeProfileSerializer(profile).data)

    def put(self, request):
        profile, _ = SizeProfile.objects.get_or_create(user=request.user)
        serializer = SizeProfileSerializer(profile, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)


class TasteProfileView(APIView):
    """GET /api/ai/taste-profile/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            profile = UserTasteProfile.objects.get(user=request.user)
            return Response(TasteProfileSerializer(profile).data)
        except UserTasteProfile.DoesNotExist:
            return Response({'quiz_completed': False})


class NotificationPreferenceView(APIView):
    """GET/PUT /api/ai/notification-preferences/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
        return Response(NotificationPreferenceSerializer(prefs).data)

    def put(self, request):
        prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
        serializer = NotificationPreferenceSerializer(prefs, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)


# ── Admin-only endpoints ──────────────────────────────────────────────────────

class FlashSaleTargetView(APIView):
    """
    POST /api/ai/admin/flash-sale-target/
    Gets target user IDs for a flash sale notification.
    Admin only.
    """
    permission_classes = [IsAdminUser]

    def post(self, request):
        category = request.data.get('category')
        if not category:
            return Response({'error': 'category required'}, status=400)

        max_users = min(int(request.data.get('max_users', 5000)), 10000)
        user_ids = FlashSaleTargetingService.get_target_users(category, max_users)

        return Response({
            'category': category,
            'target_count': len(user_ids),
            'user_ids': user_ids,
        })


class AIStatsView(APIView):
    """
    GET /api/ai/admin/stats/
    Platform-wide AI metrics. Admin only.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        from .models import (
            UserTasteProfile, BehavioralEvent, ProductEmbedding,
            RecommendationCache, SearchQuery, AIConversation, PriceDropAlert
        )
        from django.db.models import Avg

        return Response({
            'profiles': {
                'total': UserTasteProfile.objects.count(),
                'quiz_completed': UserTasteProfile.objects.filter(quiz_completed=True).count(),
                'avg_confidence': UserTasteProfile.objects.aggregate(a=Avg('profile_confidence'))['a'] or 0,
                'by_algorithm': dict(
                    UserTasteProfile.objects.values('active_algorithm')
                    .annotate(count=models.Count('id'))
                    .values_list('active_algorithm', 'count')
                ),
            },
            'events': {
                'total_today': BehavioralEvent.objects.filter(
                    created_at__date=timezone.now().date()
                ).count(),
            },
            'products_embedded': ProductEmbedding.objects.filter(is_active=True).count(),
            'search_queries_today': SearchQuery.objects.filter(
                created_at__date=timezone.now().date()
            ).count(),
            'ai_conversations_total': AIConversation.objects.count(),
            'price_alerts_watching': PriceDropAlert.objects.filter(status='watching').count(),
        })


# Fix missing import
from django.db import models
