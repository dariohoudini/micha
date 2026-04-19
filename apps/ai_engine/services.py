"""
apps/ai_engine/services.py — MICHA Express AI Engine v2

Real AI services using:
- OpenAI text-embedding-3-small for semantic embeddings
- GPT-4o-mini for NLP search parsing + AI chat assistant
- Cosine similarity for product recommendations
- Province-aware scoring for Angola
- Multi-language support (PT + EN + SADC)
"""
import math
import logging
import json
from datetime import timedelta
from typing import Optional
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# ── OpenAI client singleton ───────────────────────────────────────────────────

_openai_client = None

def get_openai_client():
    global _openai_client
    if _openai_client is None:
        try:
            from openai import OpenAI
            _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        except Exception as e:
            logger.error(f"OpenAI client init failed: {e}")
            return None
    return _openai_client


# ── Constants ─────────────────────────────────────────────────────────────────

EMBEDDING_MODEL = 'text-embedding-3-small'
EMBEDDING_DIMENSIONS = 1536
CHAT_MODEL = 'gpt-4o-mini'
CACHE_TTL_HOURS = 6
MAX_RECOMMENDATIONS = 50
MIN_EVENTS_FOR_BEHAVIORAL = 10


# ── Embedding Service ─────────────────────────────────────────────────────────

class EmbeddingService:
    """
    Generates OpenAI text embeddings.
    Cost: $0.02 per 1M tokens = ~$0.00002 per embedding.
    At 10K products: ~$0.02 total. At 10K users: ~$0.02 total.
    """

    @classmethod
    def embed_text(cls, text: str) -> Optional[list]:
        """
        Embeds text using OpenAI text-embedding-3-small.
        Returns 1536-dim float list or None on failure.
        """
        client = get_openai_client()
        if not client:
            return cls._fallback_embedding(text)

        # Check cache first — avoid re-embedding identical text
        cache_key = f"embed:{hash(text)}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        try:
            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=text[:8191],  # OpenAI token limit
                encoding_format='float',
            )
            embedding = response.data[0].embedding

            # Cache for 24h — same text = same embedding
            cache.set(cache_key, embedding, timeout=86400)
            return embedding

        except Exception as e:
            logger.error(f"OpenAI embedding failed: {e}")
            return cls._fallback_embedding(text)

    @classmethod
    def embed_batch(cls, texts: list) -> list:
        """
        Batch embedding — more efficient than one at a time.
        OpenAI allows up to 2048 texts per batch request.
        """
        client = get_openai_client()
        if not client:
            return [cls._fallback_embedding(t) for t in texts]

        try:
            # Split into chunks of 100
            all_embeddings = []
            for i in range(0, len(texts), 100):
                chunk = [t[:8191] for t in texts[i:i+100]]
                response = client.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=chunk,
                    encoding_format='float',
                )
                all_embeddings.extend([d.embedding for d in response.data])
            return all_embeddings
        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            return [cls._fallback_embedding(t) for t in texts]

    @staticmethod
    def cosine_similarity(vec_a: list, vec_b: list) -> float:
        """Cosine similarity between two embedding vectors. Range: -1 to 1."""
        if not vec_a or not vec_b:
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        mag_a = math.sqrt(sum(a * a for a in vec_a))
        mag_b = math.sqrt(sum(b * b for b in vec_b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    @staticmethod
    def _fallback_embedding(text: str) -> list:
        """
        Deterministic pseudo-random embedding when OpenAI unavailable.
        NOT semantically meaningful — used for development only.
        """
        import hashlib, struct
        h = hashlib.sha256(text.encode()).digest()
        values = []
        seed = h
        while len(values) < EMBEDDING_DIMENSIONS:
            seed = hashlib.sha256(seed).digest()
            for i in range(0, len(seed) - 3, 4):
                raw = struct.unpack('f', seed[i:i+4])[0]
                if raw == raw and abs(raw) < 1e10:
                    values.append(raw)
        values = values[:EMBEDDING_DIMENSIONS]
        magnitude = math.sqrt(sum(v * v for v in values)) or 1.0
        return [v / magnitude for v in values]


# ── Taste Profile Service ─────────────────────────────────────────────────────

class TasteProfileService:
    """
    Manages user taste profiles.
    Combines quiz data + behavioral signals + OpenAI embeddings.
    """

    @classmethod
    def get_or_create_profile(cls, user):
        from .models import UserTasteProfile, NotificationPreference
        from .models import PROVINCE_PURCHASING_POWER

        profile, created = UserTasteProfile.objects.get_or_create(
            user=user,
            defaults={'profile_confidence': 0.0}
        )
        if created:
            NotificationPreference.objects.get_or_create(user=user)

        return profile

    @classmethod
    def update_from_onboarding(cls, user, quiz_data: dict):
        """
        Seeds profile from onboarding quiz.
        Immediately embeds the profile with OpenAI for instant personalization.
        """
        from .models import UserTasteProfile, PROVINCE_PURCHASING_POWER

        profile = cls.get_or_create_profile(user)

        with transaction.atomic():
            profile.preferred_categories = quiz_data.get('categories', [])
            profile.budget_min = quiz_data.get('budget_min', 0)
            profile.budget_max = quiz_data.get('budget_max', 999999)
            profile.shopping_for = quiz_data.get('shopping_for', 'self')
            profile.province = quiz_data.get('province', 'Luanda')
            profile.country = quiz_data.get('country', 'AO')
            profile.style_tags = quiz_data.get('style_tags', [])
            profile.preferred_language = quiz_data.get('language', 'pt')
            profile.quiz_completed = True
            profile.quiz_completed_at = timezone.now()

            # Seed category scores from quiz (0.7 = strong interest)
            for cat in profile.preferred_categories:
                profile.category_scores[cat] = 0.7

            # Apply province purchasing power
            ppi = PROVINCE_PURCHASING_POWER.get(profile.province, 0.5)
            profile.purchasing_power_index = ppi

            # Profile confidence jumps to 0.3 from quiz — much better than 0.0
            profile.profile_confidence = 0.3
            profile.update_algorithm()
            profile.save()

        # Generate OpenAI embedding for instant personalization
        from .tasks import embed_user_profile
        embed_user_profile.delay(str(user.id))

        # Immediately rebuild recommendations
        from .tasks import rebuild_user_recommendations
        rebuild_user_recommendations.delay(str(user.id))

        logger.info(f"Profile seeded from quiz for user {user.id}, province={profile.province}")
        return profile

    @classmethod
    def record_event(cls, user, event_type: str, **kwargs):
        """
        Records behavioral event and triggers async profile update.
        Non-blocking — returns immediately.
        """
        from .models import BehavioralEvent

        event = BehavioralEvent.objects.create(
            user=user,
            event_type=event_type,
            **kwargs
        )

        # Async profile update
        from .tasks import update_taste_profile_incremental
        update_taste_profile_incremental.delay(str(user.id), str(event.id))

        return event

    @classmethod
    def compute_profile_update(cls, user_id: str, event_id: str):
        """
        Called by Celery. Updates category scores using exponential moving average.
        Triggers embedding refresh if profile changed significantly.
        """
        from django.contrib.auth import get_user_model
        from .models import BehavioralEvent, PROVINCE_PURCHASING_POWER

        User = get_user_model()
        try:
            user = User.objects.get(id=user_id)
            event = BehavioralEvent.objects.get(id=event_id)
            profile = cls.get_or_create_profile(user)
        except Exception as e:
            logger.error(f"Profile update failed: {e}")
            return

        with transaction.atomic():
            alpha = 0.1  # EMA learning rate
            if event.category:
                current = profile.category_scores.get(event.category, 0.0)
                if event.signal_weight > 0:
                    normalized = min(event.signal_weight / 5.0, 1.0)
                    new_score = current + alpha * (normalized - current)
                else:
                    new_score = current * 0.85  # Decay on negative signal
                profile.category_scores[event.category] = round(new_score, 4)

            # Update purchase price stats
            if event.event_type == 'purchase' and event.price:
                if float(profile.avg_purchase_price) == 0:
                    profile.avg_purchase_price = event.price
                else:
                    profile.avg_purchase_price = (
                        float(profile.avg_purchase_price) * 0.8 +
                        float(event.price) * 0.2
                    )

            # Recalculate confidence
            from .models import BehavioralEvent as BE
            event_count = BE.objects.filter(user=user).count()
            profile.profile_confidence = min(
                0.3 + (event_count / 50) * 0.7,  # Full confidence at 50 events
                1.0
            )
            profile.update_algorithm()
            profile.save()

        # Trigger recommendation rebuild on high-signal events
        if abs(event.signal_weight) >= 2.0:
            from .tasks import rebuild_user_recommendations, embed_user_profile
            rebuild_user_recommendations.apply_async(
                args=[user_id], countdown=30
            )
            # Re-embed if many high-signal events (profile shifted significantly)
            if event_count % 10 == 0:
                embed_user_profile.delay(user_id)


# ── Recommendation Service ────────────────────────────────────────────────────

class RecommendationService:
    """
    Serves pre-computed recommendations from cache.
    Falls back gracefully at each stage.
    """

    @classmethod
    def get_home_feed(cls, user, limit: int = 20, offset: int = 0) -> dict:
        from .models import RecommendationCache

        try:
            cache_obj = RecommendationCache.objects.get(
                user=user,
                feed_type='home_feed',
                context_id=None,
                expires_at__gt=timezone.now()
            )
            product_ids = cache_obj.product_ids[offset:offset + limit]
            scores = cache_obj.scores[offset:offset + limit]

            return {
                'product_ids': [str(p) for p in product_ids],
                'scores': scores,
                'personalised': not cache_obj.is_cold_start,
                'algorithm': cache_obj.algorithm_version,
                'total': len(cache_obj.product_ids),
            }
        except RecommendationCache.DoesNotExist:
            # Cache miss — trigger async rebuild, return trending fallback
            from .tasks import rebuild_user_recommendations
            rebuild_user_recommendations.delay(str(user.id))
            return cls._trending_fallback(limit, offset)

    @classmethod
    def get_similar_products(cls, product_id, user=None, limit: int = 10) -> dict:
        from .models import SimilarProductsCache

        try:
            cache_obj = SimilarProductsCache.objects.get(product_id=product_id)
            ids = cache_obj.similar_product_ids[:limit * 2]  # Get extra for re-ranking
            scores = cache_obj.similarity_scores[:limit * 2]

            if user:
                ids, scores = cls._rerank_by_taste(user, ids, scores, limit)
            else:
                ids = ids[:limit]
                scores = scores[:limit]

            return {'product_ids': [str(i) for i in ids], 'scores': scores}
        except SimilarProductsCache.DoesNotExist:
            # Compute on demand if cache miss
            from .tasks import compute_single_product_similarity
            compute_single_product_similarity.delay(str(product_id))
            return {'product_ids': [], 'scores': []}

    @classmethod
    def _rerank_by_taste(cls, user, product_ids, scores, limit):
        """
        Re-ranks similar products by user taste affinity.
        Uses cosine similarity between user embedding and product embedding.
        """
        from .models import UserTasteProfile, ProductEmbedding

        try:
            profile = UserTasteProfile.objects.get(user=user)
            if not profile.embedding:
                return product_ids[:limit], scores[:limit]

            # Score each product by user-product embedding similarity
            user_emb = profile.embedding
            reranked = []

            product_embeddings = {
                str(pe.product_id): pe.embedding
                for pe in ProductEmbedding.objects.filter(
                    product_id__in=product_ids
                )
            }

            for pid, base_score in zip(product_ids, scores):
                prod_emb = product_embeddings.get(str(pid))
                if prod_emb:
                    taste_score = EmbeddingService.cosine_similarity(user_emb, prod_emb)
                    # Blend: 60% taste, 40% similarity
                    final_score = taste_score * 0.6 + base_score * 0.4
                else:
                    final_score = base_score * 0.4
                reranked.append((pid, final_score))

            reranked.sort(key=lambda x: x[1], reverse=True)
            reranked = reranked[:limit]
            return [p for p, _ in reranked], [s for _, s in reranked]

        except Exception as e:
            logger.error(f"Re-ranking failed: {e}")
            return product_ids[:limit], scores[:limit]

    @classmethod
    def compute_home_feed(cls, user):
        """
        Full feed computation. Called by Celery only.

        Scoring formula (weights sum to 1.0):
        - User-product embedding similarity:  0.35
        - Category affinity score:            0.25
        - Price fit (budget range match):     0.20
        - Popularity score:                   0.12
        - Province relevance:                 0.05
        - Freshness (recently added):         0.03
        """
        from .models import (
            UserTasteProfile, ProductEmbedding,
            RecommendationCache, BehavioralEvent
        )
        from datetime import timedelta

        profile = TasteProfileService.get_or_create_profile(user)
        is_cold_start = profile.profile_confidence < 0.1

        # Get products already purchased — exclude from feed
        purchased_ids = set(
            str(e.product_id)
            for e in BehavioralEvent.objects.filter(
                user=user, event_type='purchase', product_id__isnull=False
            ).values('product_id')
        )

        products = ProductEmbedding.objects.filter(is_active=True)
        budget_min, budget_max = profile.get_effective_budget_range()
        user_emb = profile.embedding

        product_scores = {}
        seven_days_ago = timezone.now() - timedelta(days=7)

        for prod in products:
            pid = str(prod.product_id)
            if pid in purchased_ids:
                continue

            score = 0.0
            breakdown = {}

            # 1. Embedding similarity (35%)
            if user_emb and prod.embedding:
                sim = EmbeddingService.cosine_similarity(user_emb, prod.embedding)
                emb_score = max(sim, 0) * 0.35
                score += emb_score
                breakdown['embedding'] = round(emb_score, 4)

            # 2. Category affinity (25%)
            cat_score = profile.category_scores.get(prod.category, 0.0)
            # Boost preferred categories from quiz
            if prod.category in profile.preferred_categories and cat_score < 0.3:
                cat_score = 0.3  # Minimum floor from quiz
            cat_contribution = cat_score * 0.25
            score += cat_contribution
            breakdown['category'] = round(cat_contribution, 4)

            # 3. Price fit (20%)
            price = float(prod.price)
            if budget_min <= price <= budget_max:
                price_score = 0.20
            elif price < budget_min:
                price_score = 0.10  # Too cheap — minor penalty
            else:
                # Over budget — penalty scales with distance
                overage = (price - budget_max) / max(budget_max, 1)
                price_score = max(0, 0.20 - overage * 0.20)
            score += price_score
            breakdown['price'] = round(price_score, 4)

            # 4. Popularity (12%)
            pop_score = min(prod.popularity_score, 1.0) * 0.12
            score += pop_score
            breakdown['popularity'] = round(pop_score, 4)

            # 5. Province relevance (5%) — seller in same province = boost
            if prod.province and prod.province == profile.province:
                score += 0.05
                breakdown['province'] = 0.05

            # 6. Freshness (3%) — recently added products get a small boost
            if prod.computed_at and prod.computed_at >= seven_days_ago:
                score += 0.03
                breakdown['freshness'] = 0.03

            product_scores[pid] = (round(score, 4), breakdown)

        # Sort by score
        sorted_items = sorted(product_scores.items(), key=lambda x: x[1][0], reverse=True)
        product_ids = [pid for pid, _ in sorted_items[:MAX_RECOMMENDATIONS]]
        scores = [data[0] for _, data in sorted_items[:MAX_RECOMMENDATIONS]]
        score_breakdowns = {pid: data[1] for pid, data in sorted_items[:MAX_RECOMMENDATIONS]}

        cache_obj, _ = RecommendationCache.objects.update_or_create(
            user=user,
            feed_type='home_feed',
            context_id=None,
            defaults={
                'product_ids': product_ids,
                'scores': scores,
                'score_breakdown': score_breakdowns,
                'is_cold_start': is_cold_start,
                'expires_at': timezone.now() + timedelta(hours=CACHE_TTL_HOURS),
                'algorithm_version': 'v2_openai',
            }
        )
        return cache_obj

    @classmethod
    def compute_similar_products(cls, product_id):
        """
        Computes top-20 similar products using OpenAI embedding cosine similarity.
        """
        from .models import ProductEmbedding, SimilarProductsCache

        try:
            source = ProductEmbedding.objects.get(product_id=product_id)
        except ProductEmbedding.DoesNotExist:
            return None

        if not source.embedding:
            return None

        all_products = ProductEmbedding.objects.filter(
            is_active=True
        ).exclude(product_id=product_id)

        similarities = []
        for other in all_products:
            if other.embedding:
                sim = EmbeddingService.cosine_similarity(source.embedding, other.embedding)
                similarities.append((str(other.product_id), sim))

        similarities.sort(key=lambda x: x[1], reverse=True)
        top_20 = similarities[:20]

        cache_obj, _ = SimilarProductsCache.objects.update_or_create(
            product_id=product_id,
            defaults={
                'similar_product_ids': [pid for pid, _ in top_20],
                'similarity_scores': [round(s, 4) for _, s in top_20],
                'algorithm': 'cosine_openai',
            }
        )
        return cache_obj

    @classmethod
    def _trending_fallback(cls, limit, offset) -> dict:
        """Returns most popular products when no personalised feed available."""
        from .models import ProductEmbedding
        products = ProductEmbedding.objects.filter(
            is_active=True
        ).order_by('-popularity_score')[offset:offset+limit]

        return {
            'product_ids': [str(p.product_id) for p in products],
            'scores': [p.popularity_score for p in products],
            'personalised': False,
            'algorithm': 'trending_fallback',
            'total': ProductEmbedding.objects.filter(is_active=True).count(),
        }


# ── Smart Search Service ──────────────────────────────────────────────────────

class SmartSearchService:
    """
    GPT-4o-mini powered NLP search.
    Understands Portuguese and English queries including SADC-specific context.
    """

    SYSTEM_PROMPT_PT = """Analisa esta pesquisa de um utilizador numa loja online angolana.
Responde APENAS com JSON válido, sem mais texto.

Formato:
{
  "category": "categoria ou null",
  "price_min": numero ou null,
  "price_max": numero ou null,
  "occasion": "ocasião ou null",
  "style": "estilo ou null",
  "color": "cor ou null",
  "size": "tamanho ou null",
  "keywords": ["palavra1", "palavra2"],
  "language": "pt"
}

Categorias válidas: Moda, Tecnologia, Casa & Jardim, Beleza, Alimentação, Desporto, Crianças, Acessórios, Calçado, Electrónica

Preços em Kwanzas (Kz). "barato" < 10000 Kz, "económico" < 20000 Kz, "premium" > 50000 Kz.
"""

    SYSTEM_PROMPT_EN = """Analyze this search query from a user on an Angolan/SADC online marketplace.
Respond ONLY with valid JSON, no other text.

Format:
{
  "category": "category or null",
  "price_min": number or null,
  "price_max": number or null,
  "occasion": "occasion or null",
  "style": "style or null",
  "color": "color or null",
  "size": "size or null",
  "keywords": ["word1", "word2"],
  "language": "en"
}

Valid categories: Moda, Tecnologia, Casa & Jardim, Beleza, Alimentação, Desporto, Crianças, Acessórios, Calçado, Electrónica

Prices in Angolan Kwanza (Kz). "cheap" < 10000 Kz, "affordable" < 20000 Kz, "premium" > 50000 Kz.
"""

    @classmethod
    def parse_query(cls, query: str, user=None) -> dict:
        """
        Parses query using GPT-4o-mini for true NLP understanding.
        Falls back to rule-based parsing if GPT unavailable.
        """
        # Detect language
        lang = cls._detect_language(query)

        # Check cache — same query same result
        cache_key = f"search_parse:{hash(query.lower())}"
        cached = cache.get(cache_key)
        if cached:
            result = cached
        else:
            result = cls._parse_with_gpt(query, lang)
            cache.set(cache_key, result, timeout=3600)  # 1h cache

        # Personalise with user taste profile
        if user:
            result = cls._personalise_parsed_query(result, user)

        # Log for analytics
        from .tasks import log_search_query
        log_search_query.delay(
            query,
            result,
            str(user.id) if user else None
        )

        return result

    @classmethod
    def _parse_with_gpt(cls, query: str, lang: str) -> dict:
        """Uses GPT-4o-mini to parse search intent."""
        client = get_openai_client()
        if not client:
            return cls._rule_based_parse(query)

        system_prompt = cls.SYSTEM_PROMPT_PT if lang == 'pt' else cls.SYSTEM_PROMPT_EN

        try:
            response = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': query},
                ],
                temperature=0.0,  # Deterministic
                max_tokens=200,
                response_format={'type': 'json_object'},
            )
            parsed = json.loads(response.choices[0].message.content)
            parsed['raw'] = query
            parsed['parse_method'] = 'gpt4o_mini'
            return parsed

        except Exception as e:
            logger.error(f"GPT search parse failed: {e}")
            return cls._rule_based_parse(query)

    @classmethod
    def _detect_language(cls, text: str) -> str:
        """Detects PT vs EN. Defaults to PT for Angola market."""
        try:
            from langdetect import detect
            lang = detect(text)
            return 'en' if lang == 'en' else 'pt'
        except Exception:
            # Simple heuristic: common PT words
            pt_words = {'para', 'com', 'uma', 'vestido', 'preço', 'barato', 'bonito'}
            words = set(text.lower().split())
            return 'pt' if words & pt_words else 'en'

    @classmethod
    def _rule_based_parse(cls, query: str) -> dict:
        """
        Fallback rule-based parser. Less accurate than GPT but zero cost.
        """
        q = query.lower()

        PRICE_RULES_PT = {
            'barato': ('max', 10000), 'económico': ('max', 15000),
            'acessível': ('max', 20000), 'caro': ('min', 50000),
            'premium': ('min', 50000), 'luxo': ('min', 100000),
        }
        PRICE_RULES_EN = {
            'cheap': ('max', 10000), 'affordable': ('max', 20000),
            'budget': ('max', 15000), 'expensive': ('min', 50000),
            'premium': ('min', 50000), 'luxury': ('min', 100000),
        }
        CATEGORY_MAP = {
            'vestido': 'Moda', 'camisa': 'Moda', 'calças': 'Moda', 'roupa': 'Moda',
            'dress': 'Moda', 'shirt': 'Moda', 'clothes': 'Moda',
            'sapatos': 'Calçado', 'shoes': 'Calçado', 'ténis': 'Calçado',
            'telefone': 'Tecnologia', 'phone': 'Tecnologia', 'smartphone': 'Tecnologia',
            'perfume': 'Beleza', 'creme': 'Beleza', 'makeup': 'Beleza',
            'sofá': 'Casa & Jardim', 'sofa': 'Casa & Jardim',
        }

        result = {
            'raw': query, 'category': None, 'price_min': None,
            'price_max': None, 'occasion': None, 'style': None,
            'color': None, 'size': None, 'keywords': [],
            'parse_method': 'rule_based',
        }

        all_price_rules = {**PRICE_RULES_PT, **PRICE_RULES_EN}
        for word in q.split():
            if word in CATEGORY_MAP and not result['category']:
                result['category'] = CATEGORY_MAP[word]
            if word in all_price_rules:
                direction, amount = all_price_rules[word]
                if direction == 'max':
                    result['price_max'] = amount
                else:
                    result['price_min'] = amount
            if len(word) > 3:
                result['keywords'].append(word)

        return result

    @classmethod
    def _personalise_parsed_query(cls, parsed: dict, user) -> dict:
        """Applies user taste profile to boost query relevance."""
        from .models import UserTasteProfile
        try:
            profile = UserTasteProfile.objects.get(user=user)
            if not parsed.get('price_max') and profile.budget_max < 999999:
                parsed['user_price_max'] = float(profile.budget_max)
            parsed['preferred_categories'] = profile.preferred_categories
            parsed['province'] = profile.province
        except UserTasteProfile.DoesNotExist:
            pass
        return parsed


# ── AI Chat Assistant Service ─────────────────────────────────────────────────

class AIChatService:
    """
    GPT-4o-mini powered shopping assistant.
    Handles: size questions, product comparisons, delivery info, recommendations.
    Tracks cost per conversation.
    """

    MAX_CONTEXT_MESSAGES = 20  # Keep last 20 messages to control token cost

    @classmethod
    def get_or_create_conversation(cls, user, product_id=None, product_name=None, language='pt'):
        from .models import AIConversation
        # Get most recent active conversation, or create new
        conv = AIConversation.objects.filter(
            user=user,
            product_id=product_id,
        ).order_by('-created_at').first()

        # Start new conversation if old one is more than 1 hour old
        if not conv or (timezone.now() - conv.updated_at).seconds > 3600:
            conv = AIConversation.objects.create(
                user=user,
                product_id=product_id,
                product_name=product_name or '',
                messages=[],
                language=language,
            )
        return conv

    @classmethod
    def send_message(cls, conversation_id: str, user_message: str) -> dict:
        """
        Sends a message to GPT-4o-mini and returns the response.
        Maintains conversation context.
        Tracks token usage and cost.
        """
        from .models import AIConversation

        try:
            conv = AIConversation.objects.get(id=conversation_id)
        except AIConversation.DoesNotExist:
            return {'error': 'Conversation not found'}

        client = get_openai_client()
        if not client:
            return cls._fallback_response(user_message, conv.language)

        # Build message history (keep last N messages for context window)
        messages = [{'role': 'system', 'content': conv.get_system_prompt()}]
        messages.extend(conv.messages[-cls.MAX_CONTEXT_MESSAGES:])
        messages.append({'role': 'user', 'content': user_message})

        try:
            response = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=500,
            )

            assistant_message = response.choices[0].message.content
            tokens_used = response.usage.total_tokens

            # Cost: GPT-4o-mini is $0.15/1M input + $0.60/1M output tokens
            cost = (
                response.usage.prompt_tokens * 0.00000015 +
                response.usage.completion_tokens * 0.00000060
            )

            # Update conversation history
            conv.messages.append({'role': 'user', 'content': user_message})
            conv.messages.append({'role': 'assistant', 'content': assistant_message})
            conv.total_tokens_used += tokens_used
            conv.total_cost_usd = float(conv.total_cost_usd) + cost
            conv.save()

            return {
                'message': assistant_message,
                'conversation_id': str(conv.id),
                'tokens_used': tokens_used,
            }

        except Exception as e:
            logger.error(f"GPT chat failed: {e}")
            return cls._fallback_response(user_message, conv.language)

    @classmethod
    def _fallback_response(cls, user_message: str, language: str) -> dict:
        """Returns a helpful fallback when GPT is unavailable."""
        if language == 'pt':
            message = "Peço desculpa, o assistente não está disponível agora. Por favor, entre em contacto com o vendedor directamente ou consulte a secção de ajuda."
        else:
            message = "Sorry, the assistant is temporarily unavailable. Please contact the seller directly or check our help section."
        return {'message': message, 'conversation_id': None, 'fallback': True}


# ── Price Drop Service ────────────────────────────────────────────────────────

class PriceDropService:
    @classmethod
    def watch_product(cls, user, product_id, current_price, product_name='', threshold_pct=10.0):
        from .models import PriceDropAlert
        alert, created = PriceDropAlert.objects.get_or_create(
            user=user, product_id=product_id,
            defaults={
                'price_when_added': current_price,
                'current_price': current_price,
                'lowest_seen_price': current_price,
                'product_name': product_name,
                'alert_threshold_pct': threshold_pct,
            }
        )
        return alert

    @classmethod
    def unwatch_product(cls, user, product_id):
        from .models import PriceDropAlert
        PriceDropAlert.objects.filter(user=user, product_id=product_id).delete()

    @classmethod
    def check_price_and_notify(cls, product_id, new_price: float):
        from .models import PriceDropAlert
        alerts = PriceDropAlert.objects.filter(
            product_id=product_id, status='watching'
        ).select_related('user', 'user__ai_notification_preferences')

        triggered = []
        for alert in alerts:
            # Update lowest seen price
            if alert.lowest_seen_price is None or new_price < float(alert.lowest_seen_price):
                alert.lowest_seen_price = new_price

            if alert.should_trigger(new_price):
                prefs = getattr(alert.user, 'ai_notification_preferences', None)
                if prefs and prefs.can_notify('price_drop'):
                    cls._send_notification(alert, new_price)
                    alert.status = 'triggered'
                    alert.triggered_at = timezone.now()
                    alert.times_triggered += 1

            alert.current_price = new_price
            alert.save()
            triggered.append(alert)

        return triggered

    @classmethod
    def _send_notification(cls, alert, new_price):
        from .tasks import send_push_notification
        drop_pct = int(
            ((float(alert.price_when_added) - new_price) / float(alert.price_when_added)) * 100
        )
        send_push_notification.delay(
            user_id=str(alert.user.id),
            title=f"Descida de preço -{drop_pct}%! 🎉",
            body=f"{alert.product_name or 'Produto'} na sua lista de desejos baixou de preço!",
            data={
                'type': 'price_drop',
                'product_id': str(alert.product_id),
                'new_price': new_price,
                'old_price': float(alert.price_when_added),
                'drop_pct': drop_pct,
            }
        )


# ── Size Recommendation Service ───────────────────────────────────────────────

class SizeRecommendationService:

    SIZE_ORDER = ['XS', 'S', 'M', 'L', 'XL', 'XXL']

    @classmethod
    def get_recommendation(cls, user, category: str, product_sizing=None) -> dict:
        from .models import SizeProfile
        try:
            profile = SizeProfile.objects.get(user=user)
        except SizeProfile.DoesNotExist:
            return {'recommended_size': None, 'confidence': 0.0, 'prompt_setup': True,
                    'explanation': 'Configure o seu perfil de tamanhos para recomendações.'}

        # 1. User-provided size (highest confidence)
        if category == 'Moda' and profile.clothing_size:
            return {
                'recommended_size': profile.clothing_size,
                'confidence': 1.0,
                'source': 'user_provided',
                'explanation': 'Baseado no tamanho que configurou no seu perfil.',
                'alternatives': cls._get_adjacent_sizes(profile.clothing_size),
                'fit_note': cls._get_fit_note(profile.fit_preference),
            }

        # 2. AI-inferred from purchase history
        if category in profile.inferred_sizes:
            inferred = profile.inferred_sizes[category]
            return {
                'recommended_size': inferred['size'],
                'confidence': inferred.get('confidence', 0.7),
                'source': 'purchase_history',
                'explanation': f"Baseado nas suas {inferred.get('purchase_count', '')} compras anteriores.",
                'alternatives': cls._get_adjacent_sizes(inferred['size']),
                'fit_note': cls._get_fit_note(profile.fit_preference),
            }

        return {
            'recommended_size': None, 'confidence': 0.0, 'prompt_setup': True,
            'explanation': 'Sem dados suficientes. Adicione o seu tamanho no perfil.',
        }

    @classmethod
    def update_from_purchase(cls, user, category: str, size: str):
        from .models import SizeProfile
        profile, _ = SizeProfile.objects.get_or_create(user=user)
        cat_data = profile.inferred_sizes.get(category, {'freq': {}})
        freq = cat_data.get('freq', {})
        freq[size] = freq.get(size, 0) + 1
        best = max(freq, key=freq.get)
        total = sum(freq.values())
        profile.inferred_sizes[category] = {
            'size': best,
            'confidence': round(freq[best] / total, 2),
            'purchase_count': total,
            'freq': freq,
        }
        profile.save()

    @classmethod
    def _get_adjacent_sizes(cls, size: str) -> list:
        try:
            idx = cls.SIZE_ORDER.index(size)
            adj = []
            if idx > 0: adj.append(cls.SIZE_ORDER[idx - 1])
            if idx < len(cls.SIZE_ORDER) - 1: adj.append(cls.SIZE_ORDER[idx + 1])
            return adj
        except ValueError:
            return []

    @staticmethod
    def _get_fit_note(fit_preference: str) -> Optional[str]:
        notes = {
            'slim': 'Prefere corte justo — considere o seu tamanho normal.',
            'loose': 'Prefere corte largo — pode considerar um tamanho menor.',
        }
        return notes.get(fit_preference)


# ── Flash Sale Targeting ──────────────────────────────────────────────────────

class FlashSaleTargetingService:

    @classmethod
    def get_target_users(cls, category: str, max_users: int = 5000) -> list:
        """
        Returns user IDs with genuine interest in a category.
        Sorted by interest score — most interested users first.
        """
        from .models import UserTasteProfile

        profiles = UserTasteProfile.objects.filter(
            quiz_completed=True,
        ).select_related('user', 'user__ai_notification_preferences')

        scored_users = []
        for profile in profiles:
            # Check category interest
            cat_score = profile.category_scores.get(category, 0.0)
            quiz_interest = 0.3 if category in profile.preferred_categories else 0.0
            total_interest = max(cat_score, quiz_interest)

            if total_interest < 0.2:
                continue

            # Check notification preference
            prefs = getattr(profile.user, 'ai_notification_preferences', None)
            if not prefs or not prefs.can_notify('flash_sale'):
                continue

            scored_users.append((str(profile.user.id), total_interest))

        # Sort by interest score
        scored_users.sort(key=lambda x: x[1], reverse=True)
        return [uid for uid, _ in scored_users[:max_users]]
