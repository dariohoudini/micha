"""
apps/trust/models.py

Seller Trust Score — MICHA Express's Angola killer feature.

The trust problem is the #1 barrier to eCommerce adoption in Africa.
Buyers don't trust sellers they've never met.
This system builds verifiable, AI-computed trust scores that:
- Are transparent (buyers can see WHY a score is what it is)
- Are hard to game (based on real transaction outcomes)
- Update in real-time (score changes after every delivery/complaint)
- Are Angola-specific (weights tuned for local market realities)

Score range: 0-100
- 90-100: Vendedor de Elite (gold badge)
- 75-89:  Vendedor de Confiança (silver badge)
- 60-74:  Bom Vendedor (bronze badge)
- 40-59:  Vendedor Verificado (basic badge)
- 0-39:   Em avaliação (no badge)
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid


class SellerTrustScore(models.Model):
    """
    Composite trust score per seller.
    Recomputed by Celery after every significant event.
    Each dimension is scored 0-100, then weighted into overall score.
    """
    BADGE_LEVELS = [
        ('elite',    'Vendedor de Elite',      '#C9A84C'),  # Gold
        ('trusted',  'Vendedor de Confiança',  '#9E9E9E'),  # Silver
        ('good',     'Bom Vendedor',           '#CD7F32'),  # Bronze
        ('verified', 'Vendedor Verificado',    '#2196F3'),  # Blue
        ('new',      'Em avaliação',           '#9E9E9E'),  # Grey
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trust_score'
    )

    # ── Overall score ─────────────────────────────────────────────────────────
    overall_score = models.FloatField(default=0.0, help_text="0-100 composite score")
    badge_level = models.CharField(max_length=20, default='new')
    badge_label = models.CharField(max_length=50, default='Em avaliação')
    badge_color = models.CharField(max_length=10, default='#9E9E9E')

    # ── Dimension scores (each 0-100) ─────────────────────────────────────────

    # 1. Delivery reliability (35% weight) — most important in Angola
    # Tracks: on-time delivery rate, order cancellation rate
    delivery_score = models.FloatField(default=0.0)
    total_orders = models.PositiveIntegerField(default=0)
    delivered_orders = models.PositiveIntegerField(default=0)
    cancelled_orders = models.PositiveIntegerField(default=0)
    on_time_deliveries = models.PositiveIntegerField(default=0)
    avg_delivery_days = models.FloatField(null=True, blank=True)

    # 2. Product quality (25% weight)
    # Tracks: avg rating, return rate, complaint rate
    quality_score = models.FloatField(default=0.0)
    avg_rating = models.FloatField(default=0.0)
    total_reviews = models.PositiveIntegerField(default=0)
    five_star_reviews = models.PositiveIntegerField(default=0)
    one_star_reviews = models.PositiveIntegerField(default=0)
    return_rate_pct = models.FloatField(default=0.0)

    # 3. Response time (20% weight) — critical for buyer confidence
    # Tracks: avg time to confirm order, avg time to respond to chat
    response_score = models.FloatField(default=0.0)
    avg_confirmation_hours = models.FloatField(null=True, blank=True)
    avg_chat_response_minutes = models.FloatField(null=True, blank=True)
    orders_confirmed_within_24h_pct = models.FloatField(default=0.0)

    # 4. Verification & compliance (15% weight)
    # Tracks: identity verified, NIF provided, address verified, active duration
    verification_score = models.FloatField(default=0.0)
    nif_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)
    address_verified = models.BooleanField(default=False)
    id_verified = models.BooleanField(default=False)
    days_on_platform = models.PositiveIntegerField(default=0)
    account_age_score = models.FloatField(default=0.0)

    # 5. Dispute & complaint handling (5% weight)
    dispute_score = models.FloatField(default=100.0)  # Starts at 100, goes down
    total_disputes = models.PositiveIntegerField(default=0)
    disputes_resolved_in_favour_of_buyer = models.PositiveIntegerField(default=0)
    unresolved_disputes = models.PositiveIntegerField(default=0)
    fraud_flags = models.PositiveIntegerField(default=0)

    # ── Trend tracking ────────────────────────────────────────────────────────
    score_30_days_ago = models.FloatField(null=True, blank=True)
    score_trend = models.CharField(
        max_length=10,
        choices=[('up','↑ A subir'), ('down','↓ A descer'), ('stable','→ Estável')],
        default='stable'
    )

    # ── Meta ──────────────────────────────────────────────────────────────────
    last_computed_at = models.DateTimeField(auto_now=True)
    computation_version = models.CharField(max_length=10, default='v1')
    # Minimum orders before score is shown publicly
    score_is_public = models.BooleanField(default=False)
    min_orders_for_public = 3  # Score hidden until seller has 3+ orders

    class Meta:
        db_table = 'trust_seller_scores'
        indexes = [
            models.Index(fields=['-overall_score']),
            models.Index(fields=['badge_level']),
        ]

    def __str__(self):
        return f"TrustScore({self.seller.email}, {self.overall_score:.1f}, {self.badge_level})"

    # Dimension weights — tuned for Angola market
    WEIGHTS = {
        'delivery':     0.35,  # Most important — delivery is the #1 trust issue
        'quality':      0.25,
        'response':     0.20,  # Quick response = more trust in informal markets
        'verification': 0.15,
        'dispute':      0.05,
    }

    def compute_overall_score(self):
        """Weighted average of all dimension scores."""
        raw = (
            self.delivery_score     * self.WEIGHTS['delivery'] +
            self.quality_score      * self.WEIGHTS['quality'] +
            self.response_score     * self.WEIGHTS['response'] +
            self.verification_score * self.WEIGHTS['verification'] +
            self.dispute_score      * self.WEIGHTS['dispute']
        )
        self.overall_score = round(raw, 1)

        # Apply fraud penalty — hard floor
        if self.fraud_flags >= 3:
            self.overall_score = min(self.overall_score, 20.0)
        elif self.fraud_flags >= 1:
            self.overall_score = min(self.overall_score, 50.0)

        self._update_badge()
        self._update_trend()
        self.score_is_public = self.total_orders >= self.min_orders_for_public

    def _update_badge(self):
        score = self.overall_score
        if score >= 90:
            self.badge_level, self.badge_label, self.badge_color = 'elite', 'Vendedor de Elite', '#C9A84C'
        elif score >= 75:
            self.badge_level, self.badge_label, self.badge_color = 'trusted', 'Vendedor de Confiança', '#9E9E9E'
        elif score >= 60:
            self.badge_level, self.badge_label, self.badge_color = 'good', 'Bom Vendedor', '#CD7F32'
        elif score >= 40:
            self.badge_level, self.badge_label, self.badge_color = 'verified', 'Vendedor Verificado', '#2196F3'
        else:
            self.badge_level, self.badge_label, self.badge_color = 'new', 'Em avaliação', '#9E9E9E'

    def _update_trend(self):
        if self.score_30_days_ago is None:
            self.score_trend = 'stable'
        elif self.overall_score > self.score_30_days_ago + 2:
            self.score_trend = 'up'
        elif self.overall_score < self.score_30_days_ago - 2:
            self.score_trend = 'down'
        else:
            self.score_trend = 'stable'

    def get_score_breakdown(self) -> dict:
        """
        Returns human-readable score breakdown.
        Shown to buyers on seller profile page.
        """
        return {
            'overall': self.overall_score,
            'badge': {
                'level': self.badge_level,
                'label': self.badge_label,
                'color': self.badge_color,
            },
            'dimensions': [
                {
                    'name': 'Fiabilidade de entrega',
                    'score': self.delivery_score,
                    'weight_pct': 35,
                    'detail': f"{self.delivered_orders}/{self.total_orders} entregas concluídas",
                    'icon': 'delivery',
                },
                {
                    'name': 'Qualidade dos produtos',
                    'score': self.quality_score,
                    'weight_pct': 25,
                    'detail': f"★ {self.avg_rating:.1f} ({self.total_reviews} avaliações)",
                    'icon': 'star',
                },
                {
                    'name': 'Tempo de resposta',
                    'score': self.response_score,
                    'weight_pct': 20,
                    'detail': f"Confirma pedidos em {self.avg_confirmation_hours:.0f}h" if self.avg_confirmation_hours else "Sem dados",
                    'icon': 'clock',
                },
                {
                    'name': 'Verificação',
                    'score': self.verification_score,
                    'weight_pct': 15,
                    'detail': self._verification_detail(),
                    'icon': 'shield',
                },
                {
                    'name': 'Resolução de disputas',
                    'score': self.dispute_score,
                    'weight_pct': 5,
                    'detail': f"{self.total_disputes} disputas no total",
                    'icon': 'dispute',
                },
            ],
            'trend': self.score_trend,
            'public': self.score_is_public,
            'last_updated': self.last_computed_at.isoformat() if self.last_computed_at else None,
        }

    def _verification_detail(self) -> str:
        verified = []
        if self.nif_verified: verified.append('NIF')
        if self.phone_verified: verified.append('Telefone')
        if self.id_verified: verified.append('BI')
        if self.address_verified: verified.append('Morada')
        return f"Verificado: {', '.join(verified)}" if verified else "Sem verificações"


class TrustScoreHistory(models.Model):
    """
    Daily snapshots of trust scores for trend analysis.
    Kept for 1 year.
    """
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trust_score_history'
    )
    score = models.FloatField()
    badge_level = models.CharField(max_length=20)
    recorded_at = models.DateField(auto_now_add=True)

    class Meta:
        db_table = 'trust_score_history'
        unique_together = [('seller', 'recorded_at')]
        indexes = [models.Index(fields=['seller', '-recorded_at'])]


class TrustEvent(models.Model):
    """
    Every event that affects trust score.
    Audit trail — sellers can see what changed their score.
    """
    EVENT_TYPES = [
        ('order_delivered',     'Pedido entregue',          +5.0),
        ('order_cancelled',     'Pedido cancelado pelo vendedor', -8.0),
        ('five_star_review',    'Avaliação de 5 estrelas',  +3.0),
        ('one_star_review',     'Avaliação de 1 estrela',  -5.0),
        ('dispute_lost',        'Disputa perdida',         -15.0),
        ('dispute_won',         'Disputa ganha',           +2.0),
        ('fraud_flag',          'Sinalização de fraude',   -30.0),
        ('nif_verified',        'NIF verificado',          +10.0),
        ('id_verified',         'BI verificado',           +8.0),
        ('fast_confirmation',   'Confirmação rápida (<2h)',  +1.0),
        ('slow_confirmation',   'Confirmação lenta (>48h)', -2.0),
        ('product_return',      'Devolução de produto',    -3.0),
    ]

    SCORE_CHANGES = {e[0]: e[2] for e in EVENT_TYPES}

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='trust_events'
    )
    event_type = models.CharField(max_length=50)
    event_label = models.CharField(max_length=100)
    score_change = models.FloatField(default=0.0)
    score_before = models.FloatField()
    score_after = models.FloatField()
    order_id = models.UUIDField(null=True, blank=True)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'trust_events'
        indexes = [
            models.Index(fields=['seller', '-created_at']),
        ]
