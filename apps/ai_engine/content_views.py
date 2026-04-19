"""
apps/ai_engine/content_views.py

AI Content Generation API endpoints.
Add these to ai_engine/urls.py
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


class GenerateProductDescriptionView(APIView):
    """
    POST /api/ai/content/generate-description/

    Generates professional product description from seller's basic notes.
    Sellers use this in the New Product form — one-click AI description.

    Body:
    {
        "name": "Vestido Capulana",
        "category": "Moda",
        "price": 8500,
        "raw_notes": "azul, tamanhos M e L, tecido angolano",
        "language": "pt"
    }
    """
    permission_classes = [IsAuthenticated]

    # Rate limit: 20 generations per hour per seller
    MAX_GENERATIONS_PER_HOUR = 20

    def post(self, request):
        # Rate limiting
        rate_key = f"content_gen_rate:{request.user.id}"
        count = cache.get(rate_key, 0)
        if count >= self.MAX_GENERATIONS_PER_HOUR:
            return Response({
                'error': 'Limite de gerações por hora atingido. Tente novamente em breve.'
            }, status=429)
        cache.set(rate_key, count + 1, timeout=3600)

        from .content_service import ContentGenerationService

        name = request.data.get('name', '').strip()
        if not name:
            return Response({'error': 'Product name is required'}, status=400)

        result = ContentGenerationService.generate_description(
            product_data={
                'name': name,
                'category': request.data.get('category', ''),
                'price': request.data.get('price', 0),
                'raw_notes': request.data.get('raw_notes', ''),
                'seller_province': getattr(
                    request.user, 'province',
                    getattr(request.user, 'ai_taste_profile', None) and
                    request.user.ai_taste_profile.province or 'Luanda'
                ),
            },
            language=request.data.get('language', 'pt'),
        )

        return Response(result)


class TranslateProductView(APIView):
    """
    POST /api/ai/content/translate/

    Translates product content between PT and EN.
    Used when expanding to English-speaking SADC countries.

    Body:
    {
        "title": "...",
        "description": "...",
        "short_description": "...",
        "tags": [...],
        "target_language": "en"
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .content_service import ContentGenerationService

        target_lang = request.data.get('target_language', 'en')
        if target_lang not in ('pt', 'en'):
            return Response({'error': 'target_language must be pt or en'}, status=400)

        product_data = {
            'title': request.data.get('title', ''),
            'description': request.data.get('description', ''),
            'short_description': request.data.get('short_description', ''),
            'tags': request.data.get('tags', []),
        }

        result = ContentGenerationService.translate_product(product_data, target_lang)
        return Response(result)


class ImproveDescriptionView(APIView):
    """
    POST /api/ai/content/improve/

    Improves an existing seller-written description.

    Body:
    {
        "description": "...",
        "category": "Moda",
        "language": "pt"
    }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .content_service import ContentGenerationService

        description = request.data.get('description', '').strip()
        if not description or len(description) < 10:
            return Response({'error': 'Description must be at least 10 characters'}, status=400)
        if len(description) > 2000:
            return Response({'error': 'Description too long (max 2000 chars)'}, status=400)

        result = ContentGenerationService.improve_description(
            existing_description=description,
            category=request.data.get('category', ''),
            language=request.data.get('language', 'pt'),
        )
        return Response(result)


class SummariseReviewsView(APIView):
    """
    GET /api/ai/content/reviews-summary/<product_id>/

    Returns AI summary of product reviews.
    Called on product detail page.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, product_id):
        from django.core.cache import cache
        from .content_service import ContentGenerationService

        # Cache summary for 6 hours — reviews don't change that fast
        cache_key = f"review_summary:{product_id}"
        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        # Get reviews from your reviews app
        reviews = []
        try:
            from apps.reviews.models import Review
            review_qs = Review.objects.filter(
                product_id=product_id
            ).values('rating', 'text')[:20]
            reviews = list(review_qs)
        except Exception:
            pass

        if not reviews:
            return Response({'summary': None, 'sentiment': 'neutral', 'highlights': []})

        # Get product name
        product_name = ''
        try:
            from apps.products.models import Product
            product = Product.objects.get(id=product_id)
            product_name = product.name
        except Exception:
            pass

        language = request.query_params.get('language', 'pt')
        result = ContentGenerationService.summarise_reviews(reviews, product_name, language)

        cache.set(cache_key, result, timeout=21600)  # 6 hour cache
        return Response(result)


# ─────────────────────────────────────────────────────────────────────────────
# Add these to apps/ai_engine/urls.py:
#
# from .content_views import (
#     GenerateProductDescriptionView,
#     TranslateProductView,
#     ImproveDescriptionView,
#     SummariseReviewsView,
# )
#
# urlpatterns += [
#     path('content/generate-description/', GenerateProductDescriptionView.as_view()),
#     path('content/translate/', TranslateProductView.as_view()),
#     path('content/improve/', ImproveDescriptionView.as_view()),
#     path('content/reviews-summary/<uuid:product_id>/', SummariseReviewsView.as_view()),
# ]
# ─────────────────────────────────────────────────────────────────────────────
