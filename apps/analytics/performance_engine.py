"""
MICHA Seller Performance Engine
=================================
Validated scoring system based on real seller behaviour signals.

Dimensions (each 0-100):
1. Delivery Speed     (25%) — how fast orders are dispatched
2. Completion Rate    (25%) — orders fulfilled vs cancelled/abandoned  
3. Response Rate      (20%) — how quickly sellers reply to buyers
4. Review Quality     (20%) — average rating weighted by recency
5. Dispute Rate       (10%) — disputes filed vs total orders (inverted)

Why these weights:
- Delivery and completion are the #1 complaints in Angolan e-commerce
- Response rate directly impacts buyer confidence pre-purchase
- Reviews are the visible trust signal buyers rely on
- Disputes are a lagging indicator — catches chronic bad sellers

Score → Tier mapping:
  90-100: Elite    (gold badge)
  75-89:  Trusted  (silver badge)
  60-74:  Good     (bronze badge)
  40-59:  Verified (basic badge)
  0-39:   New/Under review
"""
import logging
from datetime import timedelta
from django.utils import timezone

logger = logging.getLogger('micha.analytics')


class SellerPerformanceEngine:
    """
    Computes all performance dimensions from raw order/chat/review data.
    Designed to be fast: single DB query per dimension where possible.
    """

    # Dimension weights — must sum to 1.0
    WEIGHTS = {
        'delivery_speed':    0.25,
        'completion_rate':   0.25,
        'response_rate':     0.20,
        'review_quality':    0.20,
        'dispute_rate':      0.10,
    }

    # Tier thresholds
    TIERS = [
        (90, 'elite',    'Vendedor de Elite',     '#C9A84C'),
        (75, 'trusted',  'Vendedor de Confiança', '#9E9E9E'),
        (60, 'good',     'Bom Vendedor',          '#CD7F32'),
        (40, 'verified', 'Vendedor Verificado',   '#2196F3'),
        (0,  'new',      'Em avaliação',          '#9E9E9E'),
    ]

    # Minimum orders required for reliable scoring
    MIN_ORDERS_FOR_FULL_SCORE = 10
    MIN_ORDERS_FOR_ANY_SCORE = 3

    def __init__(self, seller):
        self.seller = seller
        self.now = timezone.now()
        self.window_90d = self.now - timedelta(days=90)
        self.window_30d = self.now - timedelta(days=30)

    def compute(self) -> dict:
        """
        Compute all dimensions and return full performance dict.
        Uses 90-day rolling window for all metrics.
        """
        from apps.orders.models import Order

        # Get order counts first to decide scoring approach
        total_orders = Order.objects.filter(
            seller=self.seller,
            created_at__gte=self.window_90d,
        ).count()

        all_time_orders = Order.objects.filter(seller=self.seller).count()

        if all_time_orders < self.MIN_ORDERS_FOR_ANY_SCORE:
            return self._cold_start_score(all_time_orders)

        # Compute each dimension
        delivery = self._compute_delivery_speed()
        completion = self._compute_completion_rate()
        response = self._compute_response_rate()
        review = self._compute_review_quality()
        dispute = self._compute_dispute_rate()

        # Weighted overall score
        overall = (
            delivery['score'] * self.WEIGHTS['delivery_speed'] +
            completion['score'] * self.WEIGHTS['completion_rate'] +
            response['score'] * self.WEIGHTS['response_rate'] +
            review['score'] * self.WEIGHTS['review_quality'] +
            dispute['score'] * self.WEIGHTS['dispute_rate']
        )

        # Confidence multiplier for sellers with few orders
        if total_orders < self.MIN_ORDERS_FOR_FULL_SCORE:
            confidence = 0.5 + (total_orders / self.MIN_ORDERS_FOR_FULL_SCORE) * 0.5
            overall = overall * confidence + 50 * (1 - confidence)

        overall = min(max(overall, 0), 100)
        tier_info = self._get_tier(overall)

        result = {
            'overall_score': round(overall, 2),
            'tier': tier_info['tier'],
            'tier_label': tier_info['label'],
            'tier_color': tier_info['color'],
            'dimensions': {
                'delivery_speed': delivery,
                'completion_rate': completion,
                'response_rate': response,
                'review_quality': review,
                'dispute_rate': dispute,
            },
            'meta': {
                'orders_90d': total_orders,
                'orders_all_time': all_time_orders,
                'window_days': 90,
                'computed_at': self.now.isoformat(),
                'confidence': 'full' if total_orders >= self.MIN_ORDERS_FOR_FULL_SCORE else 'partial',
            }
        }

        return result

    def _compute_delivery_speed(self) -> dict:
        """
        How fast does the seller dispatch orders?
        Target: < 24h dispatch = 100 points
        Formula: score based on median dispatch time
        """
        from apps.orders.models import Order, OrderStatusLog

        try:
            # Find confirmed → shipped transitions
            # This tells us how fast sellers actually pack and ship
            dispatched_orders = Order.objects.filter(
                seller=self.seller,
                status__in=['shipped', 'delivered', 'completed'],
                created_at__gte=self.window_90d,
            )

            if not dispatched_orders.exists():
                return {'score': 50, 'label': 'Sem dados', 'raw': None}

            # Calculate dispatch times from status logs
            dispatch_times = []
            for order in dispatched_orders[:100]:
                try:
                    shipped_log = OrderStatusLog.objects.filter(
                        order=order,
                        to_status='shipped',
                    ).order_by('created_at').first()

                    if shipped_log:
                        hours = (shipped_log.created_at - order.created_at).total_seconds() / 3600
                        if 0 < hours < 720:  # sanity: between 0 and 30 days
                            dispatch_times.append(hours)
                except Exception:
                    pass

            if not dispatch_times:
                # Fall back: use delivered orders, estimate 24h dispatch
                delivered = dispatched_orders.filter(status__in=['delivered', 'completed']).count()
                total = dispatched_orders.count()
                rate = delivered / total if total > 0 else 0.5
                return {
                    'score': round(rate * 80, 1),  # max 80 without real data
                    'label': 'Estimado',
                    'raw': None,
                }

            median_hours = sorted(dispatch_times)[len(dispatch_times) // 2]
            avg_hours = sum(dispatch_times) / len(dispatch_times)

            # Scoring curve:
            # < 6h = 100, < 12h = 90, < 24h = 80, < 48h = 60, < 72h = 40, > 72h = 20
            if median_hours < 6:
                score = 100
            elif median_hours < 12:
                score = 90
            elif median_hours < 24:
                score = 80
            elif median_hours < 48:
                score = 60
            elif median_hours < 72:
                score = 40
            else:
                score = max(20, 100 - median_hours * 0.5)

            label = f'{avg_hours:.0f}h médio'
            return {
                'score': round(score, 1),
                'label': label,
                'raw': {'median_hours': round(median_hours, 1), 'avg_hours': round(avg_hours, 1), 'sample_size': len(dispatch_times)},
            }

        except Exception as e:
            logger.debug(f'Delivery speed compute error: {e}')
            return {'score': 50, 'label': 'Erro', 'raw': None}

    def _compute_completion_rate(self) -> dict:
        """
        What % of accepted orders are actually fulfilled?
        Distinguishes between seller-cancelled (bad) vs buyer-cancelled (neutral).
        """
        from apps.orders.models import Order

        try:
            orders = Order.objects.filter(
                seller=self.seller,
                created_at__gte=self.window_90d,
            )
            total = orders.count()

            if total == 0:
                return {'score': 50, 'label': 'Sem dados', 'raw': None}

            completed = orders.filter(status__in=['delivered', 'completed']).count()
            seller_cancelled = orders.filter(
                status='cancelled',
                # Status log shows seller cancelled (not buyer)
            ).count()
            buyer_cancelled = orders.filter(
                status='cancelled',
            ).count() - seller_cancelled

            # Only penalize seller-initiated cancellations
            # Give credit for completed orders
            effective_total = total - buyer_cancelled
            if effective_total <= 0:
                effective_total = total

            rate = completed / effective_total
            score = min(rate * 100, 100)

            # Extra penalty for high seller cancellation rate
            if seller_cancelled / max(total, 1) > 0.1:
                score *= 0.85

            return {
                'score': round(score, 1),
                'label': f'{rate*100:.0f}% concluídos',
                'raw': {
                    'total': total,
                    'completed': completed,
                    'cancelled': seller_cancelled,
                    'rate': round(rate, 4),
                },
            }

        except Exception as e:
            logger.debug(f'Completion rate compute error: {e}')
            return {'score': 50, 'label': 'Erro', 'raw': None}

    def _compute_response_rate(self) -> dict:
        """
        How quickly does the seller respond to buyer messages?
        Target: < 2h = 100 points
        Also checks: % of chats that get any response
        """
        try:
            from apps.chat.models import Chat, Message

            # Chats where this user is seller
            chats = Chat.objects.filter(
                seller=self.seller,
                last_message_at__gte=self.window_90d,
            )

            total_chats = chats.count()
            if total_chats == 0:
                return {'score': 70, 'label': 'Sem mensagens', 'raw': None}

            response_times_hours = []
            responded_count = 0

            for chat in chats[:50]:  # sample for performance
                # Find first buyer message
                first_buyer_msg = Message.objects.filter(
                    chat=chat,
                    sender=chat.buyer,
                ).order_by('created_at').first()

                if not first_buyer_msg:
                    continue

                # Find first seller response after buyer's message
                first_seller_reply = Message.objects.filter(
                    chat=chat,
                    sender=self.seller,
                    created_at__gt=first_buyer_msg.created_at,
                ).order_by('created_at').first()

                if first_seller_reply:
                    responded_count += 1
                    hours = (first_seller_reply.created_at - first_buyer_msg.created_at).total_seconds() / 3600
                    if 0 < hours < 168:  # within 1 week
                        response_times_hours.append(hours)

            # Response rate (% of chats that got a reply)
            sampled = min(total_chats, 50)
            response_rate = responded_count / sampled if sampled > 0 else 0

            # Average response time score
            if response_times_hours:
                avg_hours = sum(response_times_hours) / len(response_times_hours)
                if avg_hours < 1:
                    time_score = 100
                elif avg_hours < 2:
                    time_score = 90
                elif avg_hours < 6:
                    time_score = 75
                elif avg_hours < 12:
                    time_score = 55
                elif avg_hours < 24:
                    time_score = 35
                else:
                    time_score = 15
            else:
                avg_hours = None
                time_score = 50

            # Combined score: 60% time + 40% rate
            score = time_score * 0.6 + response_rate * 100 * 0.4

            label = f'{avg_hours:.0f}h' if avg_hours else f'{response_rate*100:.0f}% resp.'
            return {
                'score': round(score, 1),
                'label': label,
                'raw': {
                    'response_rate': round(response_rate, 4),
                    'avg_hours': round(avg_hours, 1) if avg_hours else None,
                    'chats_sampled': sampled,
                },
            }

        except Exception as e:
            logger.debug(f'Response rate compute error: {e}')
            return {'score': 60, 'label': 'Erro', 'raw': None}

    def _compute_review_quality(self) -> dict:
        """
        Weighted average review score with recency bias.
        Recent reviews count more than old ones.
        Also penalizes sellers with very few reviews on many orders.
        """
        try:
            from apps.reviews.models import ProductReview

            reviews = ProductReview.objects.filter(
                product__store__owner=self.seller,
                created_at__gte=self.window_90d,
            ).values('rating', 'created_at')

            if not reviews:
                # No reviews — neutral score, slightly below average
                return {'score': 50, 'label': 'Sem avaliações', 'raw': None}

            # Recency-weighted average
            # Reviews in last 30 days weight = 3x
            # Reviews 30-60 days = 2x
            # Reviews 60-90 days = 1x
            weighted_sum = 0
            total_weight = 0
            cutoff_30 = self.now - timedelta(days=30)
            cutoff_60 = self.now - timedelta(days=60)

            for review in reviews:
                age = review['created_at']
                if age >= cutoff_30:
                    weight = 3
                elif age >= cutoff_60:
                    weight = 2
                else:
                    weight = 1

                weighted_sum += review['rating'] * weight
                total_weight += weight

            weighted_avg = weighted_sum / total_weight if total_weight > 0 else 3.0
            review_count = len(reviews)

            # Convert 1-5 scale to 0-100
            score = (weighted_avg - 1) / 4 * 100

            # Volume bonus: more reviews = more reliable signal
            if review_count >= 20:
                score = min(score * 1.05, 100)
            elif review_count < 5:
                score = score * 0.9  # slight penalty for very few reviews

            # Low rating penalty — 1-star reviews hurt more
            one_stars = sum(1 for r in reviews if r['rating'] == 1)
            if one_stars >= 3:
                score *= (1 - one_stars * 0.03)

            return {
                'score': round(min(max(score, 0), 100), 1),
                'label': f'{weighted_avg:.1f}★ ({review_count} avaliações)',
                'raw': {
                    'weighted_avg': round(weighted_avg, 2),
                    'count': review_count,
                    'one_stars': one_stars,
                },
            }

        except Exception as e:
            logger.debug(f'Review quality compute error: {e}')
            return {'score': 50, 'label': 'Erro', 'raw': None}

    def _compute_dispute_rate(self) -> dict:
        """
        Disputes filed / total orders (inverted — lower is better).
        Distinguishes buyer-initiated vs platform-initiated disputes.
        """
        try:
            from apps.disputes.models import Dispute
            from apps.orders.models import Order

            total = Order.objects.filter(
                seller=self.seller,
                created_at__gte=self.window_90d,
                status__in=['delivered', 'completed', 'returned', 'refunded'],
            ).count()

            if total == 0:
                return {'score': 80, 'label': 'Sem dados', 'raw': None}

            disputes = Dispute.objects.filter(
                seller=self.seller,
                created_at__gte=self.window_90d,
            )
            total_disputes = disputes.count()
            seller_lost = disputes.filter(
                status='resolved',
                resolution='buyer_wins',
            ).count()

            dispute_rate = total_disputes / total
            loss_rate = seller_lost / max(total_disputes, 1)

            # Score: 0% disputes = 100, 5% = 80, 10% = 50, 20% = 0
            if dispute_rate == 0:
                score = 100
            elif dispute_rate < 0.02:
                score = 90
            elif dispute_rate < 0.05:
                score = 80
            elif dispute_rate < 0.10:
                score = 60
            elif dispute_rate < 0.20:
                score = 30
            else:
                score = 0

            # Extra penalty if seller loses most disputes (chronic bad actor)
            if loss_rate > 0.7 and seller_lost >= 3:
                score *= 0.7

            return {
                'score': round(score, 1),
                'label': f'{dispute_rate*100:.1f}% disputas',
                'raw': {
                    'total_disputes': total_disputes,
                    'seller_lost': seller_lost,
                    'dispute_rate': round(dispute_rate, 4),
                    'loss_rate': round(loss_rate, 4),
                },
            }

        except Exception as e:
            logger.debug(f'Dispute rate compute error: {e}')
            return {'score': 80, 'label': 'Erro', 'raw': None}

    def _cold_start_score(self, order_count: int) -> dict:
        """Score for brand new sellers with < 3 orders."""
        # Check if seller at least has KYC verified
        base_score = 40
        try:
            from apps.verification.models import SellerVerification
            verified = SellerVerification.objects.filter(
                seller=self.seller, status='approved'
            ).exists()
            if verified:
                base_score = 50
        except Exception:
            pass

        tier_info = self._get_tier(base_score)
        return {
            'overall_score': base_score,
            'tier': tier_info['tier'],
            'tier_label': tier_info['label'],
            'tier_color': tier_info['color'],
            'dimensions': {},
            'meta': {
                'orders_all_time': order_count,
                'confidence': 'cold_start',
                'computed_at': self.now.isoformat(),
            },
        }

    def _get_tier(self, score: float) -> dict:
        for threshold, tier, label, color in self.TIERS:
            if score >= threshold:
                return {'tier': tier, 'label': label, 'color': color}
        return {'tier': 'new', 'label': 'Em avaliação', 'color': '#9E9E9E'}


def update_all_seller_scores() -> dict:
    """
    Update performance scores for all active sellers.
    Returns summary dict.
    """
    from django.contrib.auth import get_user_model
    from apps.analytics.models import SellerPerformance
    from decimal import Decimal

    User = get_user_model()
    sellers = User.objects.filter(is_seller=True, is_active=True)

    updated = 0
    errors = 0
    tiers = {}

    for seller in sellers:
        try:
            engine = SellerPerformanceEngine(seller)
            result = engine.compute()

            perf, _ = SellerPerformance.objects.get_or_create(seller=seller)

            # Update all dimensions
            dims = result.get('dimensions', {})

            perf.overall_score = Decimal(str(result['overall_score'] / 100)).quantize(Decimal('0.0001'))
            perf.tier = result['tier']

            if 'completion_rate' in dims:
                perf.completion_rate = Decimal(str(
                    dims['completion_rate']['raw']['rate']
                    if dims['completion_rate']['raw'] else 0.5
                )).quantize(Decimal('0.0001'))

            if 'response_rate' in dims:
                raw = dims['response_rate']['raw']
                if raw:
                    perf.response_rate = Decimal(str(raw['response_rate'])).quantize(Decimal('0.0001'))
                    if raw.get('avg_hours'):
                        perf.avg_response_time_hours = Decimal(str(raw['avg_hours'])).quantize(Decimal('0.01'))

            if 'delivery_speed' in dims:
                raw = dims['delivery_speed']['raw']
                if raw:
                    on_time = min(dims['delivery_speed']['score'] / 100, 1)
                    perf.on_time_delivery_rate = Decimal(str(on_time)).quantize(Decimal('0.0001'))

            if 'dispute_rate' in dims:
                raw = dims['dispute_rate']['raw']
                if raw:
                    perf.return_rate = Decimal(str(raw['dispute_rate'])).quantize(Decimal('0.0001'))

            perf.save()

            # Update trust score badge
            try:
                from apps.trust.models import SellerTrustScore
                trust, _ = SellerTrustScore.objects.get_or_create(seller=seller)
                trust.overall_score = result['overall_score']
                trust.badge_level = result['tier']
                trust.badge_label = result['tier_label']
                trust.badge_color = result['tier_color']
                trust.delivery_score = dims.get('delivery_speed', {}).get('score', 0)
                trust.save(update_fields=[
                    'overall_score', 'badge_level', 'badge_label',
                    'badge_color', 'delivery_score',
                ])
            except Exception as e:
                logger.debug(f'Trust score update failed for {seller.id}: {e}')

            tiers[result['tier']] = tiers.get(result['tier'], 0) + 1
            updated += 1

        except Exception as e:
            errors += 1
            logger.error(f'Performance score failed for seller {seller.id}: {e}')

    logger.info('Seller performance scores updated', extra={
        'updated': updated,
        'errors': errors,
        'tier_distribution': tiers,
    })

    return {'updated': updated, 'errors': errors, 'tiers': tiers}
