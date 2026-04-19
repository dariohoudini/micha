"""
apps/ai_engine/content_service.py

AI Content Generation for MICHA Express.
Uses GPT-4o-mini to:
1. Generate product descriptions from basic seller input
2. Translate PT ↔ EN for SADC market expansion
3. Improve existing descriptions (grammar, tone, SEO)
4. Generate SEO-optimised titles
5. Summarise product reviews

Cost: ~$0.001 per product description (GPT-4o-mini)
At 100 new products/day: ~$3/month
"""
import logging
import json
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CHAT_MODEL = 'gpt-4o-mini'


def get_openai_client():
    try:
        from openai import OpenAI
        return OpenAI(api_key=settings.OPENAI_API_KEY)
    except Exception as e:
        logger.error(f"OpenAI client error: {e}")
        return None


class ContentGenerationService:
    """
    Generates and improves product content using GPT-4o-mini.
    """

    @classmethod
    def generate_description(cls, product_data: dict, language: str = 'pt') -> dict:
        """
        Generates a professional product description from basic seller input.

        product_data = {
            'name': 'Vestido Capulana',
            'category': 'Moda',
            'price': 8500,
            'raw_notes': 'azul, M e L, tecido capulana, tradicional angolana',
            'seller_province': 'Luanda',
        }

        Returns:
        {
            'title': 'Vestido Capulana Tradicional Angolana — Azul',
            'description': '...',
            'short_description': '...',
            'tags': ['capulana', 'vestido', 'angola', 'tradicional', 'azul'],
            'generated': True,
        }
        """
        cache_key = f"content_gen:{hash(str(product_data))}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        client = get_openai_client()
        if not client:
            return cls._fallback_content(product_data)

        if language == 'pt':
            system = """És um especialista em copywriting para eCommerce angolano.
Cria descrições de produtos profissionais, apelativas e optimizadas para SEO em Português de Angola.
Responde APENAS com JSON válido.

Formato:
{
  "title": "título optimizado (max 80 chars)",
  "description": "descrição detalhada (150-300 palavras)",
  "short_description": "resumo curto (max 50 palavras)",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "highlights": ["ponto1", "ponto2", "ponto3"]
}

Tom: Profissional mas acessível. Destaca qualidade, origem angolana quando relevante, e benefícios práticos."""
        else:
            system = """You are an eCommerce copywriting expert for the SADC market.
Create professional, engaging, SEO-optimised product descriptions in English.
Respond ONLY with valid JSON.

Format:
{
  "title": "optimised title (max 80 chars)",
  "description": "detailed description (150-300 words)",
  "short_description": "short summary (max 50 words)",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "highlights": ["point1", "point2", "point3"]
}

Tone: Professional but accessible. Highlight quality, Angolan/African origin when relevant, practical benefits."""

        prompt = f"""Produto: {product_data.get('name', '')}
Categoria: {product_data.get('category', '')}
Preço: {product_data.get('price', '')} Kz
Notas do vendedor: {product_data.get('raw_notes', '')}
Província: {product_data.get('seller_province', 'Luanda')}"""

        try:
            response = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': prompt},
                ],
                temperature=0.7,
                max_tokens=600,
                response_format={'type': 'json_object'},
            )
            result = json.loads(response.choices[0].message.content)
            result['generated'] = True
            result['language'] = language
            cache.set(cache_key, result, timeout=86400)
            return result

        except Exception as e:
            logger.error(f"Content generation failed: {e}")
            return cls._fallback_content(product_data)

    @classmethod
    def translate_product(cls, product_data: dict, target_language: str) -> dict:
        """
        Translates product content between PT and EN.
        Used for SADC market expansion.

        product_data = {
            'title': '...',
            'description': '...',
            'short_description': '...',
            'tags': [...],
        }
        """
        if not product_data.get('description'):
            return product_data

        cache_key = f"translate:{hash(str(product_data))}:{target_language}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        client = get_openai_client()
        if not client:
            return product_data

        lang_name = 'English' if target_language == 'en' else 'Português'
        source_lang = 'PT' if target_language == 'en' else 'EN'

        system = f"""Translate this {source_lang} eCommerce product content to {lang_name}.
Keep the professional tone. Adapt culturally for the target market.
Preserve all product specifics (sizes, materials, features).
Respond ONLY with valid JSON in the same structure as input."""

        try:
            response = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': json.dumps(product_data, ensure_ascii=False)},
                ],
                temperature=0.3,
                max_tokens=600,
                response_format={'type': 'json_object'},
            )
            result = json.loads(response.choices[0].message.content)
            result['translated'] = True
            result['language'] = target_language
            cache.set(cache_key, result, timeout=86400)
            return result

        except Exception as e:
            logger.error(f"Translation failed: {e}")
            return product_data

    @classmethod
    def improve_description(cls, existing_description: str, category: str,
                           language: str = 'pt') -> dict:
        """
        Improves an existing seller-written description.
        Fixes grammar, improves tone, adds missing details.
        """
        client = get_openai_client()
        if not client:
            return {'improved': existing_description, 'was_improved': False}

        if language == 'pt':
            prompt = f"""Melhora esta descrição de produto para uma loja online angolana.
Categoria: {category}
Descrição original: {existing_description}

Corrige gramática, melhora o tom, torna mais apelativo.
Mantém todas as informações originais.
Responde com JSON: {{"improved": "descrição melhorada", "changes": ["mudança1", "mudança2"]}}"""
        else:
            prompt = f"""Improve this product description for an online store.
Category: {category}
Original: {existing_description}

Fix grammar, improve tone, make it more appealing.
Keep all original information.
Respond with JSON: {{"improved": "improved description", "changes": ["change1", "change2"]}}"""

        try:
            response = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.5,
                max_tokens=400,
                response_format={'type': 'json_object'},
            )
            result = json.loads(response.choices[0].message.content)
            result['was_improved'] = True
            return result
        except Exception as e:
            logger.error(f"Description improvement failed: {e}")
            return {'improved': existing_description, 'was_improved': False}

    @classmethod
    def summarise_reviews(cls, reviews: list, product_name: str,
                         language: str = 'pt') -> dict:
        """
        Generates AI summary of product reviews.
        "Most buyers say: good quality, fast delivery. Some mention: sizing runs small."

        reviews = [{'rating': 5, 'text': '...'}, ...]
        """
        if not reviews:
            return {'summary': None, 'sentiment': 'neutral', 'highlights': []}

        if language == 'pt':
            system = """Analisa estas avaliações de produto e cria um resumo útil para compradores.
Responde com JSON:
{
  "summary": "resumo em 1-2 frases (ex: 'A maioria dos compradores destaca a boa qualidade...')",
  "sentiment": "positive|neutral|negative",
  "pros": ["ponto positivo 1", "ponto positivo 2"],
  "cons": ["ponto negativo 1"],
  "highlights": ["destaque 1", "destaque 2"]
}"""
        else:
            system = """Analyze these product reviews and create a useful summary for buyers.
Respond with JSON:
{
  "summary": "1-2 sentence summary (e.g., 'Most buyers highlight good quality...')",
  "sentiment": "positive|neutral|negative",
  "pros": ["pro 1", "pro 2"],
  "cons": ["con 1"],
  "highlights": ["highlight 1", "highlight 2"]
}"""

        review_text = "\n".join([
            f"★{r.get('rating', 0)}: {r.get('text', '')}"
            for r in reviews[:20]  # Max 20 reviews
        ])

        try:
            client = get_openai_client()
            if not client:
                return {'summary': None, 'sentiment': 'neutral', 'highlights': []}

            response = client.chat.completions.create(
                model=CHAT_MODEL,
                messages=[
                    {'role': 'system', 'content': system},
                    {'role': 'user', 'content': f"Produto: {product_name}\n\nAvaliações:\n{review_text}"},
                ],
                temperature=0.3,
                max_tokens=300,
                response_format={'type': 'json_object'},
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.error(f"Review summarisation failed: {e}")
            return {'summary': None, 'sentiment': 'neutral', 'highlights': []}

    @classmethod
    def _fallback_content(cls, product_data: dict) -> dict:
        """Returns basic content when OpenAI is unavailable."""
        name = product_data.get('name', 'Produto')
        category = product_data.get('category', '')
        return {
            'title': name,
            'description': f"{name}. {product_data.get('raw_notes', '')}",
            'short_description': name,
            'tags': [category.lower()] if category else [],
            'highlights': [],
            'generated': False,
        }
