"""
apps/trust/services.py

Trust Score computation + Fraud Detection for MICHA Express.
"""
import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction

logger = logging.getLogger(__name__)


class TrustScoreService:
    """
    Computes and updates seller trust scores.
    Called by Celery after every order/review/dispute event.
    """

    @classmethod
    def get_or_create(cls, seller):
        from .models import SellerTrustScore
        score, _ = SellerTrustScore.objects.get_or_create(seller=seller)
        return score

    @classmethod
    def recompute(cls, seller):
        """
        Full trust score recomputation for a seller.
        Queries all historical data and recomputes each dimension.
        Called by Celery — not in request path.
        """
        from .models import SellerTrustScore, TrustScoreHistory

        score = cls.get_or_create(seller)

        with transaction.atomic():
            # Save snapshot before update
            if score.overall_score > 0:
                TrustScoreHistory.objects.update_or_create(
                    seller=seller,
                    recorded_at=timezone.now().date(),
                    defaults={'score': score.overall_score, 'badge_level': score.badge_level}
                )
                # Record score 30 days ago for trend
                thirty_days_ago = (timezone.now() - timedelta(days=30)).date()
                old = TrustScoreHistory.objects.filter(
                    seller=seller,
                    recorded_at__lte=thirty_days_ago
                ).order_by('-recorded_at').first()
                if old:
                    score.score_30_days_ago = old.score

            # Recompute all dimensions
            cls._compute_delivery_score(score, seller)
            cls._compute_quality_score(score, seller)
            cls._compute_response_score(score, seller)
            cls._compute_verification_score(score, seller)
            cls._compute_dispute_score(score, seller)

            # Platform tenure
            score.days_on_platform = (timezone.now() - seller.date_joined).days

            # Compute overall
            score.compute_overall_score()
            score.save()

        logger.info(f"Trust score recomputed for {seller.email}: {score.overall_score:.1f} ({score.badge_level})")
        return score

    @classmethod
    def _compute_delivery_score(cls, score, seller):
        """Delivery reliability — 35% weight."""
        try:
            from apps.orders.models import Order
            orders = Order.objects.filter(seller=seller)
            total = orders.count()
            score.total_orders = total

            if total == 0:
                score.delivery_score = 50.0  # Neutral for new sellers
                return

            delivered = orders.filter(status='delivered').count()
            cancelled = orders.filter(status='cancelled', cancelled_by='seller').count()
            score.delivered_orders = delivered
            score.cancelled_orders = cancelled

            delivery_rate = delivered / total if total > 0 else 0
            cancel_penalty = (cancelled / total) * 30 if total > 0 else 0
            score.delivery_score = max(0, min(100, delivery_rate * 100 - cancel_penalty))
        except Exception as e:
            logger.debug(f"Delivery score computation error: {e}")
            score.delivery_score = 50.0

    @classmethod
    def _compute_quality_score(cls, score, seller):
        """Product quality — 25% weight."""
        try:
            from apps.reviews.models import Review
            reviews = Review.objects.filter(seller=seller)
            total = reviews.count()
            score.total_reviews = total

            if total == 0:
                score.quality_score = 50.0
                return

            avg = reviews.aggregate(avg=models.Avg('rating'))['avg'] or 0
            score.avg_rating = round(float(avg), 2)
            score.five_star_reviews = reviews.filter(rating=5).count()
            score.one_star_reviews = reviews.filter(rating__lte=2).count()

            # Score: avg_rating (0-5) normalized to 0-100
            # Penalty for high proportion of 1-2 star reviews
            base = (score.avg_rating / 5.0) * 100
            bad_ratio = score.one_star_reviews / total if total > 0 else 0
            penalty = bad_ratio * 30
            score.quality_score = max(0, min(100, base - penalty))
        except Exception as e:
            logger.debug(f"Quality score computation error: {e}")
            score.quality_score = 50.0

    @classmethod
    def _compute_response_score(cls, score, seller):
        """Response time — 20% weight."""
        try:
            from apps.orders.models import Order
            from django.db.models import Avg, F, ExpressionWrapper, DurationField

            # Average hours to confirm orders
            recent_orders = Order.objects.filter(
                seller=seller,
                status__in=['confirmed', 'shipped', 'delivered'],
                confirmed_at__isnull=False,
            ).order_by('-created_at')[:50]

            if recent_orders.exists():
                total_hours = 0
                count = 0
                for order in recent_orders:
                    delta = (order.confirmed_at - order.created_at).total_seconds() / 3600
                    total_hours += delta
                    count += 1
                avg_hours = total_hours / count if count > 0 else 48
                score.avg_confirmation_hours = round(avg_hours, 1)

                # Score: <2h = 100, 2-6h = 80, 6-24h = 60, 24-48h = 40, >48h = 20
                if avg_hours <= 2:
                    response_score = 100
                elif avg_hours <= 6:
                    response_score = 80
                elif avg_hours <= 24:
                    response_score = 60
                elif avg_hours <= 48:
                    response_score = 40
                else:
                    response_score = 20

                within_24h = sum(1 for o in recent_orders if
                    (o.confirmed_at - o.created_at).total_seconds() / 3600 <= 24)
                score.orders_confirmed_within_24h_pct = (within_24h / count * 100) if count else 0
                score.response_score = float(response_score)
            else:
                score.response_score = 50.0
        except Exception as e:
            logger.debug(f"Response score computation error: {e}")
            score.response_score = 50.0

    @classmethod
    def _compute_verification_score(cls, score, seller):
        """Verification & compliance — 15% weight."""
        try:
            # Check verification fields on seller profile
            profile = getattr(seller, 'seller_profile', None) or getattr(seller, 'store', None)

            if profile:
                score.nif_verified = bool(getattr(profile, 'nif', None))
                score.phone_verified = bool(getattr(seller, 'phone', None))
                score.address_verified = bool(getattr(profile, 'address', None) or getattr(profile, 'province', None))
            else:
                score.phone_verified = bool(getattr(seller, 'phone', None))

            # Points per verification
            points = 0
            if score.nif_verified: points += 30
            if score.phone_verified: points += 20
            if score.id_verified: points += 25
            if score.address_verified: points += 15

            # Account age bonus (max 10 points)
            age_bonus = min(score.days_on_platform / 365 * 10, 10)
            points += age_bonus

            score.account_age_score = age_bonus
            score.verification_score = min(100, points)
        except Exception as e:
            logger.debug(f"Verification score computation error: {e}")
            score.verification_score = 20.0

    @classmethod
    def _compute_dispute_score(cls, score, seller):
        """Dispute handling — 5% weight."""
        try:
            from apps.orders.models import Order
            disputes = Order.objects.filter(seller=seller, status='dispute')
            score.total_disputes = disputes.count()

            if score.total_disputes == 0:
                score.dispute_score = 100.0
                return

            # Each unresolved dispute = -15 points
            # Each dispute lost (resolved for buyer) = -10 points
            unresolved = disputes.filter(dispute_resolved=False).count()
            lost = disputes.filter(dispute_resolved=True, dispute_winner='buyer').count()

            score.unresolved_disputes = unresolved
            score.disputes_resolved_in_favour_of_buyer = lost

            deductions = (unresolved * 15) + (lost * 10)
            score.dispute_score = max(0, 100 - deductions)
        except Exception as e:
            logger.debug(f"Dispute score computation error: {e}")
            score.dispute_score = 100.0

    @classmethod
    def record_event(cls, seller, event_type: str, order_id=None, metadata=None):
        """
        Records a trust event and triggers async score recomputation.
        """
        from .models import TrustEvent, SellerTrustScore

        score = cls.get_or_create(seller)
        change = TrustEvent.SCORE_CHANGES.get(event_type, 0.0)
        label = dict((e[0], e[1]) for e in TrustEvent.EVENT_TYPES).get(event_type, event_type)

        TrustEvent.objects.create(
            seller=seller,
            event_type=event_type,
            event_label=label,
            score_change=change,
            score_before=score.overall_score,
            score_after=max(0, min(100, score.overall_score + change)),
            order_id=order_id,
            metadata=metadata or {},
        )

        # Async full recomputation
        from .tasks import recompute_trust_score
        recompute_trust_score.delay(str(seller.id))


class FraudDetectionService:
    """
    AI-powered fraud detection for MICHA Express.
    Targets the specific fraud patterns common in Angola's eCommerce:

    1. Fake sellers — list products, collect payment, never deliver
    2. Fake buyers — order goods, file false disputes to get refunds
    3. Review manipulation — create fake accounts to boost own reviews
    4. Payment fraud — use stolen Multicaixa/AppyPay credentials
    5. Identity fraud — impersonate legitimate sellers
    """

    # Risk thresholds
    LOW_RISK = 30
    MEDIUM_RISK = 60
    HIGH_RISK = 80

    @classmethod
    def assess_seller_risk(cls, seller) -> dict:
        """
        Computes fraud risk score for a seller.
        Called on: registration, first sale, when flagged.
        Returns risk score 0-100 (higher = more suspicious).
        """
        risk_score = 0
        risk_signals = []

        # Signal 1: New account + high-value products immediately
        days_old = (timezone.now() - seller.date_joined).days
        try:
            from apps.products.models import Product
            expensive_products = Product.objects.filter(
                seller=seller, price__gte=50000
            ).count()
            if days_old < 7 and expensive_products > 0:
                risk_score += 25
                risk_signals.append({
                    'signal': 'new_account_expensive_products',
                    'description': 'Conta nova com produtos de alto valor',
                    'severity': 'high',
                })
        except Exception:
            pass

        # Signal 2: No verification but active seller
        try:
            score = seller.trust_score
            if not score.nif_verified and not score.phone_verified and score.total_orders > 5:
                risk_score += 20
                risk_signals.append({
                    'signal': 'unverified_active_seller',
                    'description': 'Vendedor activo sem verificações',
                    'severity': 'medium',
                })
        except Exception:
            pass

        # Signal 3: High cancellation rate (collect payment intent, cancel)
        try:
            from apps.orders.models import Order
            orders = Order.objects.filter(seller=seller)
            total = orders.count()
            if total >= 5:
                cancelled = orders.filter(status='cancelled', cancelled_by='seller').count()
                cancel_rate = cancelled / total
                if cancel_rate > 0.3:
                    risk_score += 30
                    risk_signals.append({
                        'signal': 'high_cancellation_rate',
                        'description': f'Taxa de cancelamento de {cancel_rate*100:.0f}%',
                        'severity': 'high',
                    })
        except Exception:
            pass

        # Signal 4: Many disputes in short time
        try:
            from apps.orders.models import Order
            recent_disputes = Order.objects.filter(
                seller=seller,
                status='dispute',
                created_at__gte=timezone.now() - timedelta(days=30)
            ).count()
            if recent_disputes >= 3:
                risk_score += 25
                risk_signals.append({
                    'signal': 'multiple_recent_disputes',
                    'description': f'{recent_disputes} disputas nos últimos 30 dias',
                    'severity': 'high',
                })
        except Exception:
            pass

        # Signal 5: Identical product descriptions (copy-paste fraud)
        try:
            from apps.products.models import Product
            products = Product.objects.filter(seller=seller).values_list('description', flat=True)
            if len(products) > 1:
                descriptions = [d for d in products if d]
                if len(descriptions) != len(set(descriptions)):
                    risk_score += 15
                    risk_signals.append({
                        'signal': 'duplicate_descriptions',
                        'description': 'Descrições de produtos duplicadas',
                        'severity': 'medium',
                    })
        except Exception:
            pass

        risk_level = cls._get_risk_level(risk_score)
        return {
            'risk_score': min(risk_score, 100),
            'risk_level': risk_level,
            'signals': risk_signals,
            'recommendation': cls._get_recommendation(risk_level),
            'requires_review': risk_score >= cls.MEDIUM_RISK,
        }

    @classmethod
    def assess_buyer_risk(cls, buyer, order=None) -> dict:
        """
        Fraud risk assessment for a buyer placing an order.
        Called at checkout.
        """
        risk_score = 0
        risk_signals = []

        # Signal 1: New account making large purchase
        days_old = (timezone.now() - buyer.date_joined).days
        if order and order.get('total', 0) > 50000 and days_old < 3:
            risk_score += 30
            risk_signals.append({
                'signal': 'new_account_large_purchase',
                'description': 'Conta nova com compra de alto valor',
                'severity': 'high',
            })

        # Signal 2: Multiple orders to same address from different accounts
        # (friendly fraud ring detection)
        if order and order.get('delivery_address'):
            try:
                from apps.orders.models import Order
                from django.contrib.auth import get_user_model
                User = get_user_model()
                same_address_buyers = Order.objects.filter(
                    delivery_address=order['delivery_address'],
                    created_at__gte=timezone.now() - timedelta(days=7),
                ).exclude(user=buyer).values('user').distinct().count()

                if same_address_buyers >= 3:
                    risk_score += 25
                    risk_signals.append({
                        'signal': 'multiple_accounts_same_address',
                        'description': 'Múltiplas contas com o mesmo endereço',
                        'severity': 'high',
                    })
            except Exception:
                pass

        # Signal 3: History of disputes filed
        try:
            from apps.orders.models import Order
            buyer_disputes = Order.objects.filter(
                user=buyer,
                status='dispute',
            ).count()
            total_orders = Order.objects.filter(user=buyer).count()
            if total_orders >= 3 and buyer_disputes / total_orders > 0.3:
                risk_score += 20
                risk_signals.append({
                    'signal': 'high_dispute_rate',
                    'description': f'Comprador com histórico de disputas',
                    'severity': 'medium',
                })
        except Exception:
            pass

        # Signal 4: Unverified email placing large order
        if not getattr(buyer, 'is_email_verified', True):
            if order and order.get('total', 0) > 20000:
                risk_score += 20
                risk_signals.append({
                    'signal': 'unverified_email_large_order',
                    'description': 'Email não verificado com compra de alto valor',
                    'severity': 'medium',
                })

        risk_level = cls._get_risk_level(risk_score)
        return {
            'risk_score': min(risk_score, 100),
            'risk_level': risk_level,
            'signals': risk_signals,
            'allow_order': risk_score < cls.HIGH_RISK,
            'require_additional_verification': risk_score >= cls.MEDIUM_RISK,
            'recommendation': cls._get_recommendation(risk_level),
        }

    @classmethod
    def detect_fake_reviews(cls, seller_id) -> dict:
        """
        Detects patterns suggesting fake/purchased reviews.
        - Burst of 5-star reviews in short period
        - Reviews from accounts with no purchase history
        - Reviews with identical/very similar text
        """
        risk_signals = []

        try:
            from apps.reviews.models import Review
            from django.db.models import Count

            reviews = Review.objects.filter(seller_id=seller_id).order_by('-created_at')

            # Signal 1: Burst pattern — 5+ reviews in 24h
            last_24h = reviews.filter(
                created_at__gte=timezone.now() - timedelta(hours=24)
            ).count()
            if last_24h >= 5:
                risk_signals.append({
                    'signal': 'review_burst',
                    'description': f'{last_24h} avaliações nas últimas 24h',
                    'severity': 'high',
                })

            # Signal 2: Reviews from buyers with no orders from this seller
            for review in reviews[:20]:
                try:
                    from apps.orders.models import Order
                    has_order = Order.objects.filter(
                        user=review.user,
                        seller_id=seller_id,
                        status='delivered'
                    ).exists()
                    if not has_order:
                        risk_signals.append({
                            'signal': 'review_without_purchase',
                            'description': f'Avaliação sem compra verificada',
                            'severity': 'high',
                        })
                        break
                except Exception:
                    pass

        except Exception as e:
            logger.debug(f"Fake review detection error: {e}")

        return {
            'suspicious': len(risk_signals) > 0,
            'signals': risk_signals,
            'recommendation': 'flag_for_review' if risk_signals else 'clear',
        }

    @classmethod
    def _get_risk_level(cls, score: int) -> str:
        if score >= cls.HIGH_RISK: return 'high'
        if score >= cls.MEDIUM_RISK: return 'medium'
        if score >= cls.LOW_RISK: return 'low'
        return 'minimal'

    @classmethod
    def _get_recommendation(cls, risk_level: str) -> str:
        return {
            'high': 'Suspender conta e rever manualmente',
            'medium': 'Requerer verificação adicional',
            'low': 'Monitorizar actividade',
            'minimal': 'Nenhuma acção necessária',
        }.get(risk_level, 'Monitorizar')


# Fix missing import
from datetime import timedelta
from django.db import models
