"""
apps/ai_engine/models.py — MICHA Express AI Engine v2

Architecture:
- pgvector VectorField for real semantic similarity search
- Multi-language support (PT + EN + 10 SADC languages)
- Province-aware pricing for Angola's 18 provinces
- SADC country support (Angola, Zimbabwe, Zambia, Botswana, Namibia, SA, Mozambique)
- OpenAI text-embedding-3-small (1536-dim, cheapest + best quality)
- Full behavioral event graph for collaborative filtering
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid

try:
    from pgvector.django import VectorField
    PGVECTOR_AVAILABLE = True
except ImportError:
    # Fallback to JSONField during development — migrate to VectorField in production
    VectorField = None
    PGVECTOR_AVAILABLE = False


def get_embedding_field(dimensions=1536):
    """Returns VectorField if pgvector available, else JSONField."""
    if PGVECTOR_AVAILABLE and VectorField:
        return VectorField(dimensions=dimensions, null=True, blank=True)
    return models.JSONField(null=True, blank=True)


# ── SADC Countries & Angola Provinces ────────────────────────────────────────

SADC_COUNTRIES = [
    ('AO', 'Angola'),
    ('ZW', 'Zimbabwe'),
    ('ZM', 'Zambia'),
    ('BW', 'Botswana'),
    ('NA', 'Namibia'),
    ('ZA', 'South Africa'),
    ('MZ', 'Mozambique'),
    ('TZ', 'Tanzania'),
    ('MW', 'Malawi'),
    ('LS', 'Lesotho'),
]

ANGOLA_PROVINCES = [
    ('Luanda', 'Luanda'),
    ('Benguela', 'Benguela'),
    ('Huambo', 'Huambo'),
    ('Huíla', 'Huíla'),
    ('Cabinda', 'Cabinda'),
    ('Uíge', 'Uíge'),
    ('Namibe', 'Namibe'),
    ('Malanje', 'Malanje'),
    ('Bié', 'Bié'),
    ('Moxico', 'Moxico'),
    ('Cunene', 'Cunene'),
    ('Cuando Cubango', 'Cuando Cubango'),
    ('Lunda Norte', 'Lunda Norte'),
    ('Lunda Sul', 'Lunda Sul'),
    ('Kwanza Norte', 'Kwanza Norte'),
    ('Kwanza Sul', 'Kwanza Sul'),
    ('Bengo', 'Bengo'),
    ('Zaire', 'Zaire'),
]

# Province purchasing power index (Luanda = 1.0, others relative)
PROVINCE_PURCHASING_POWER = {
    'Luanda': 1.0, 'Cabinda': 0.85, 'Benguela': 0.75,
    'Huambo': 0.65, 'Huíla': 0.60, 'Namibe': 0.58,
    'Malanje': 0.52, 'Uíge': 0.50, 'Kwanza Norte': 0.48,
    'Kwanza Sul': 0.48, 'Bié': 0.45, 'Lunda Norte': 0.55,
    'Lunda Sul': 0.52, 'Moxico': 0.42, 'Cunene': 0.44,
    'Cuando Cubango': 0.40, 'Bengo': 0.55, 'Zaire': 0.48,
}


class UserTasteProfile(models.Model):
    """
    Central AI taste profile per user.
    Embedding computed by OpenAI text-embedding-3-small from:
    - Quiz answers
    - Purchase history summary
    - Browsing patterns
    Updated incrementally by Celery on significant events.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_taste_profile'
    )

    # ── Quiz answers ──────────────────────────────────────────────────────────
    preferred_categories = models.JSONField(default=list)
    budget_min = models.PositiveIntegerField(default=0, help_text="Kz")
    budget_max = models.PositiveIntegerField(default=999999, help_text="Kz")
    shopping_for = models.CharField(
        max_length=20,
        choices=[('self','Self'),('family','Family'),('business','Business'),('gifts','Gifts')],
        default='self'
    )
    province = models.CharField(max_length=50, choices=ANGOLA_PROVINCES, default='Luanda')
    country = models.CharField(max_length=2, choices=SADC_COUNTRIES, default='AO')
    style_tags = models.JSONField(default=list)
    preferred_language = models.CharField(
        max_length=5,
        choices=[('pt','Portuguese'),('en','English')],
        default='pt'
    )

    # ── Learned signals ───────────────────────────────────────────────────────
    category_scores = models.JSONField(
        default=dict,
        help_text="{'Moda': 0.85, 'Tech': 0.2} — learned from behavior"
    )
    brand_scores = models.JSONField(default=dict)
    seller_affinity = models.JSONField(
        default=dict,
        help_text="{'seller_id': score} — users tend to rebuy from same sellers"
    )
    avg_purchase_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    price_sensitivity = models.FloatField(
        default=0.5,
        help_text="0=insensitive, 1=very price sensitive. Learned from browse vs purchase gap."
    )
    # Province purchasing power applied to recommendations
    purchasing_power_index = models.FloatField(default=1.0)

    # ── OpenAI embedding (1536-dim) ───────────────────────────────────────────
    # Stores user taste as a semantic vector
    # In production with pgvector: VectorField(dimensions=1536)
    # In dev with SQLite: JSONField
    embedding = models.JSONField(null=True, blank=True)
    embedding_text = models.TextField(
        blank=True,
        help_text="The text that was embedded — for debugging and re-embedding"
    )
    embedding_updated_at = models.DateTimeField(null=True, blank=True)
    embedding_model = models.CharField(
        max_length=50, default='text-embedding-3-small'
    )

    # ── Engagement stats ──────────────────────────────────────────────────────
    total_views = models.PositiveIntegerField(default=0)
    total_searches = models.PositiveIntegerField(default=0)
    total_purchases = models.PositiveIntegerField(default=0)
    total_wishlist_adds = models.PositiveIntegerField(default=0)
    total_chat_starts = models.PositiveIntegerField(default=0)
    avg_session_duration_seconds = models.FloatField(default=0)
    days_since_last_active = models.PositiveIntegerField(default=0)

    # ── Quiz & profile health ─────────────────────────────────────────────────
    quiz_completed = models.BooleanField(default=False)
    quiz_completed_at = models.DateTimeField(null=True, blank=True)
    profile_confidence = models.FloatField(
        default=0.0,
        help_text="0=cold start, 1=fully warmed up. Determines algorithm choice."
    )
    # Which algorithm is serving this user
    active_algorithm = models.CharField(
        max_length=20,
        choices=[
            ('cold_start', 'Cold start — popularity-based'),
            ('quiz_seeded', 'Quiz seeded — category boosted'),
            ('behavioral', 'Behavioral — full ML'),
            ('hybrid', 'Hybrid — ML + popularity blend'),
        ],
        default='cold_start'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_user_taste_profiles'
        indexes = [
            models.Index(fields=['country', 'province']),
            models.Index(fields=['active_algorithm']),
            models.Index(fields=['profile_confidence']),
        ]

    def __str__(self):
        return f"TasteProfile({self.user.email}, {self.profile_confidence:.2f}, {self.active_algorithm})"

    def get_effective_budget_range(self):
        """
        Returns budget range considering:
        1. Quiz answer
        2. Learned from purchase history
        3. Province purchasing power adjustment
        """
        if self.avg_purchase_price > 0:
            learned_max = float(self.avg_purchase_price) * 3.0
            effective_max = max(float(self.budget_max), learned_max)
        else:
            effective_max = float(self.budget_max)

        # Adjust for province purchasing power
        ppi = self.purchasing_power_index
        return (
            float(self.budget_min) * ppi,
            effective_max * ppi
        )

    def get_embedding_input_text(self):
        """
        Builds text representation of taste profile for OpenAI embedding.
        This is what gets sent to text-embedding-3-small.
        """
        parts = []

        if self.preferred_categories:
            parts.append(f"Interested in: {', '.join(self.preferred_categories)}")

        if self.style_tags:
            parts.append(f"Style: {', '.join(self.style_tags)}")

        if self.budget_max < 10000:
            parts.append("Budget-conscious shopper")
        elif self.budget_max > 50000:
            parts.append("Premium shopper")

        if self.shopping_for != 'self':
            parts.append(f"Shopping for: {self.shopping_for}")

        # Add top categories by score
        top_cats = sorted(
            self.category_scores.items(),
            key=lambda x: x[1], reverse=True
        )[:5]
        if top_cats:
            cat_str = ', '.join([f"{cat}({score:.1f})" for cat, score in top_cats])
            parts.append(f"Top interests: {cat_str}")

        lang = "Portuguese" if self.preferred_language == 'pt' else "English"
        parts.append(f"Language: {lang}, Country: {self.country}")

        return ". ".join(parts)

    def update_algorithm(self):
        """Selects the right algorithm based on profile maturity."""
        if self.profile_confidence < 0.1:
            self.active_algorithm = 'cold_start'
        elif self.profile_confidence < 0.3:
            self.active_algorithm = 'quiz_seeded'
        elif self.profile_confidence < 0.6:
            self.active_algorithm = 'hybrid'
        else:
            self.active_algorithm = 'behavioral'


class BehavioralEvent(models.Model):
    """
    Complete behavioral event log.
    This is the training data for the recommendation model.
    High-volume — index carefully.
    """
    EVENT_TYPES = [
        # Positive signals
        ('view',           'Product view',          0.5),
        ('dwell_10',       'Dwell 10s+',            0.8),
        ('dwell_30',       'Dwell 30s+',            1.2),
        ('dwell_60',       'Dwell 60s+',            1.5),
        ('scroll_images',  'Scrolled all images',   1.0),
        ('read_reviews',   'Read reviews',          1.0),
        ('wishlist_add',   'Added to wishlist',     1.5),
        ('cart_add',       'Added to cart',         2.0),
        ('checkout_start', 'Started checkout',      3.0),
        ('purchase',       'Purchased',             5.0),
        ('review',         'Left review',           3.0),
        ('share',          'Shared product',        2.0),
        ('chat_start',     'Messaged seller',       1.5),
        ('click_rec',      'Clicked recommendation',1.0),
        ('search_click',   'Clicked search result', 1.2),
        # Negative signals
        ('wishlist_remove','Removed from wishlist', -0.5),
        ('cart_remove',    'Removed from cart',    -0.3),
        ('return',         'Returned product',     -2.0),
        ('bad_review',     'Left 1-2 star review', -2.5),
        ('bounce',         'Quick bounce <5s',     -0.3),
    ]

    SIGNAL_WEIGHTS = {e[0]: e[2] for e in EVENT_TYPES}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_behavioral_events'
    )
    event_type = models.CharField(max_length=20)
    product_id = models.UUIDField(null=True, blank=True, db_index=True)
    seller_id = models.UUIDField(null=True, blank=True, db_index=True)
    category = models.CharField(max_length=50, blank=True, db_index=True)
    subcategory = models.CharField(max_length=50, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    signal_weight = models.FloatField(default=1.0)

    # Context — where did this happen
    source = models.CharField(
        max_length=30, blank=True,
        choices=[
            ('home_feed','Home feed'),
            ('search','Search results'),
            ('recommendation','AI recommendation'),
            ('similar','Similar products'),
            ('direct','Direct navigation'),
            ('notification','Push notification'),
            ('flash_sale','Flash sale'),
            ('share','Shared link'),
        ]
    )
    session_id = models.CharField(max_length=100, blank=True, db_index=True)
    dwell_seconds = models.PositiveIntegerField(null=True, blank=True)
    scroll_depth_pct = models.PositiveSmallIntegerField(null=True, blank=True)

    # Did this lead to a conversion
    converted = models.BooleanField(
        null=True,
        help_text="True if event led to purchase in same session"
    )

    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'ai_behavioral_events'
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['user', 'event_type']),
            models.Index(fields=['product_id', 'event_type']),
            models.Index(fields=['session_id']),
            models.Index(fields=['category', 'event_type']),
            models.Index(fields=['-created_at']),  # For recent events queries
        ]

    def save(self, *args, **kwargs):
        self.signal_weight = self.SIGNAL_WEIGHTS.get(self.event_type, 1.0)
        super().save(*args, **kwargs)


class ProductEmbedding(models.Model):
    """
    OpenAI embedding per product.
    Text encoded: "{name}. {description}. Category: {category}. Tags: {tags}"
    1536 dimensions from text-embedding-3-small.
    Used for:
    - Similarity search (cosine distance in pgvector)
    - User-product affinity scoring
    - Cold-start recommendations
    """
    product_id = models.UUIDField(primary_key=True)

    # OpenAI embedding — 1536 dims
    embedding = models.JSONField(default=list)
    embedding_model = models.CharField(max_length=50, default='text-embedding-3-small')
    embedding_text = models.TextField(blank=True, help_text="Input text that was embedded")

    # Cached product metadata for fast scoring without joining products table
    name = models.CharField(max_length=255, blank=True)
    category = models.CharField(max_length=50, db_index=True)
    subcategory = models.CharField(max_length=50, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    tags = models.JSONField(default=list)
    seller_id = models.UUIDField(null=True, blank=True, db_index=True)
    province = models.CharField(max_length=50, blank=True)

    # Popularity signals (refreshed from products app daily)
    total_sales = models.PositiveIntegerField(default=0)
    total_views = models.PositiveIntegerField(default=0)
    avg_rating = models.FloatField(default=0.0)
    popularity_score = models.FloatField(default=0.0)

    # Freshness
    is_express = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_product_embeddings'
        indexes = [
            models.Index(fields=['category', 'is_active']),
            models.Index(fields=['-popularity_score']),
            models.Index(fields=['price']),
        ]

    def get_embedding_input_text(self):
        tags_str = ', '.join(self.tags) if self.tags else ''
        return (
            f"{self.name}. "
            f"Category: {self.category}. "
            f"Price: {self.price} Kz. "
            f"Tags: {tags_str}."
        )


class RecommendationCache(models.Model):
    """
    Pre-computed personalised recommendation lists.
    Served at zero ML inference time — just a DB read.
    Refreshed by Celery every 6h or on significant behavioral event.
    """
    FEED_TYPES = [
        ('home_feed',    'Home feed'),
        ('similar',      'Similar products'),
        ('trending',     'Trending for you'),
        ('flash_target', 'Flash sale target'),
        ('cross_sell',   'Cross-sell'),
        ('recently_viewed_similar', 'Based on recently viewed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_recommendation_caches'
    )
    feed_type = models.CharField(max_length=30, choices=FEED_TYPES)
    # For similar products: the reference product_id
    context_id = models.UUIDField(null=True, blank=True)

    # Ordered product UUIDs + their scores
    product_ids = models.JSONField(default=list)
    scores = models.JSONField(default=list)
    score_breakdown = models.JSONField(
        default=dict,
        help_text="Per-product score breakdown for debugging: {product_id: {category: 0.4, price: 0.3, ...}}"
    )

    # Metadata
    is_cold_start = models.BooleanField(default=False)
    algorithm_version = models.CharField(max_length=20, default='v2')
    computed_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    # Track quality for A/B
    ctr = models.FloatField(default=0.0, help_text="Click-through rate — measured after serving")
    cvr = models.FloatField(default=0.0, help_text="Conversion rate")

    class Meta:
        db_table = 'ai_recommendation_caches'
        unique_together = [('user', 'feed_type', 'context_id')]
        indexes = [
            models.Index(fields=['user', 'feed_type']),
            models.Index(fields=['expires_at']),
        ]


class SimilarProductsCache(models.Model):
    """
    Product-to-product cosine similarity.
    Not user-specific — computed nightly for all active products.
    """
    product_id = models.UUIDField(primary_key=True)
    similar_product_ids = models.JSONField(default=list)
    similarity_scores = models.JSONField(default=list)
    algorithm = models.CharField(max_length=20, default='cosine_openai')
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_similar_products_cache'


class SearchQuery(models.Model):
    """
    Every search query — the raw training data for search improvement.
    GPT-4o-mini parses intent. Results fed back for click-through learning.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='ai_search_queries'
    )
    raw_query = models.CharField(max_length=500, db_index=True)
    normalized_query = models.CharField(max_length=500, blank=True)
    detected_language = models.CharField(max_length=5, default='pt')

    # GPT-4o-mini parsed intent
    parsed_intent = models.JSONField(
        default=dict,
        help_text="Full GPT parsed output: {category, price_max, occasion, style, keywords}"
    )
    detected_category = models.CharField(max_length=50, blank=True, db_index=True)
    detected_price_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    detected_price_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    detected_occasion = models.CharField(max_length=100, blank=True)
    detected_style = models.CharField(max_length=100, blank=True)

    # Result quality signals
    results_count = models.PositiveIntegerField(default=0)
    clicked_product_ids = models.JSONField(default=list)
    purchased_after_search = models.BooleanField(default=False)
    zero_results = models.BooleanField(default=False)

    session_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'ai_search_queries'
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['detected_category']),
            models.Index(fields=['zero_results']),
        ]


class AIConversation(models.Model):
    """
    AI chat assistant conversations.
    GPT-4o-mini responds to buyer questions about products, sizing, availability.
    Full conversation history stored for context.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_conversations'
    )
    # Product context if chat started from product page
    product_id = models.UUIDField(null=True, blank=True)
    product_name = models.CharField(max_length=255, blank=True)

    # Full conversation history in OpenAI format
    messages = models.JSONField(
        default=list,
        help_text="[{role: user|assistant, content: str}, ...]"
    )
    total_tokens_used = models.PositiveIntegerField(default=0)
    total_cost_usd = models.DecimalField(max_digits=8, decimal_places=6, default=0)

    # Outcome tracking
    led_to_purchase = models.BooleanField(default=False)
    led_to_cart_add = models.BooleanField(default=False)
    user_rating = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="1-5 stars from user feedback on AI response"
    )

    language = models.CharField(max_length=5, default='pt')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_conversations'
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['product_id']),
        ]

    def get_system_prompt(self):
        """Returns GPT-4o-mini system prompt in the right language."""
        if self.language == 'pt':
            base = """És o assistente de compras da MICHA Express, o maior marketplace de Angola.
És simpático, útil e conheces bem os produtos disponíveis.
Respondes sempre em Português de Angola.
Ajudas com: escolha de tamanhos, comparação de produtos, informações de entrega, e recomendações personalizadas.
Nunca inventas informações que não tens. Se não souberes, dizes honestamente."""
        else:
            base = """You are the MICHA Express shopping assistant, the largest marketplace in Angola serving SADC countries.
You are friendly, helpful and knowledgeable about available products.
You help with: size selection, product comparisons, delivery information, and personalised recommendations.
Never make up information you don't have. If you don't know something, say so honestly."""

        if self.product_name:
            if self.language == 'pt':
                base += f"\n\nO utilizador está a ver: {self.product_name}"
            else:
                base += f"\n\nThe user is viewing: {self.product_name}"

        return base


class PriceDropAlert(models.Model):
    """Price watch on wishlisted products."""
    STATUS = [
        ('watching',  'Watching'),
        ('triggered', 'Alert sent'),
        ('dismissed', 'Dismissed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_price_drop_alerts'
    )
    product_id = models.UUIDField(db_index=True)
    product_name = models.CharField(max_length=255, blank=True)
    price_when_added = models.DecimalField(max_digits=12, decimal_places=2)
    current_price = models.DecimalField(max_digits=12, decimal_places=2)
    lowest_seen_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    alert_threshold_pct = models.FloatField(default=10.0)
    status = models.CharField(max_length=20, choices=STATUS, default='watching')
    triggered_at = models.DateTimeField(null=True, blank=True)
    times_triggered = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_price_drop_alerts'
        unique_together = [('user', 'product_id')]
        indexes = [
            models.Index(fields=['status', 'product_id']),
        ]

    def should_trigger(self, new_price: float) -> bool:
        if float(self.price_when_added) == 0:
            return False
        drop_pct = ((float(self.price_when_added) - new_price) / float(self.price_when_added)) * 100
        return drop_pct >= self.alert_threshold_pct


class SizeProfile(models.Model):
    """User measurements + AI-inferred sizes to reduce returns."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_size_profile'
    )
    height_cm = models.PositiveSmallIntegerField(null=True, blank=True)
    weight_kg = models.PositiveSmallIntegerField(null=True, blank=True)
    chest_cm = models.PositiveSmallIntegerField(null=True, blank=True)
    waist_cm = models.PositiveSmallIntegerField(null=True, blank=True)
    hips_cm = models.PositiveSmallIntegerField(null=True, blank=True)
    clothing_size = models.CharField(
        max_length=5, blank=True,
        choices=[('XS','XS'),('S','S'),('M','M'),('L','L'),('XL','XL'),('XXL','XXL')]
    )
    shoe_size_eu = models.PositiveSmallIntegerField(null=True, blank=True)
    fit_preference = models.CharField(
        max_length=20, blank=True,
        choices=[('slim','Slim fit'),('regular','Regular fit'),('loose','Loose fit')]
    )
    # AI-inferred from purchase history — {category: {size, confidence, purchase_count}}
    inferred_sizes = models.JSONField(default=dict)
    # Return history — used to improve future recommendations
    return_reasons = models.JSONField(
        default=list,
        help_text="[{product_id, reason: too_small|too_large|wrong_fit, date}]"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'ai_size_profiles'


class NotificationPreference(models.Model):
    """Per-user notification controls — prevents AI spam."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_notification_preferences'
    )
    push_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    price_drops = models.BooleanField(default=True)
    flash_sales = models.BooleanField(default=True)
    new_recommendations = models.BooleanField(default=True)
    order_updates = models.BooleanField(default=True)
    chat_messages = models.BooleanField(default=True)
    quiet_hours_start = models.TimeField(null=True, blank=True)
    quiet_hours_end = models.TimeField(null=True, blank=True)
    max_daily_recommendations = models.PositiveSmallIntegerField(default=3)
    max_daily_flash_sales = models.PositiveSmallIntegerField(default=2)
    daily_notification_count = models.PositiveSmallIntegerField(default=0)
    notification_count_reset_at = models.DateField(null=True, blank=True)

    class Meta:
        db_table = 'ai_notification_preferences'

    def can_notify(self, notification_type: str) -> bool:
        from datetime import date
        if not self.push_enabled:
            return False
        today = date.today()
        if self.notification_count_reset_at != today:
            self.daily_notification_count = 0
            self.notification_count_reset_at = today
            self.save(update_fields=['daily_notification_count', 'notification_count_reset_at'])
        if self.quiet_hours_start and self.quiet_hours_end:
            from datetime import datetime
            now = datetime.now().time()
            if self.quiet_hours_start <= now or now <= self.quiet_hours_end:
                return False
        type_map = {
            'price_drop': self.price_drops,
            'flash_sale': self.flash_sales,
            'recommendation': self.new_recommendations,
        }
        return type_map.get(notification_type, True)


class ABTestAssignment(models.Model):
    """
    A/B test assignments for algorithm experiments.
    Ensures consistent user experience within a test.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_ab_assignments'
    )
    experiment_name = models.CharField(max_length=100)
    variant = models.CharField(max_length=50)
    assigned_at = models.DateTimeField(auto_now_add=True)
    converted = models.BooleanField(default=False)
    converted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'ai_ab_test_assignments'
        unique_together = [('user', 'experiment_name')]
