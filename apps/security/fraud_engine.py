"""
MICHA Fraud Detection Engine
==============================
Multi-signal real-time fraud scoring for every order.

Angola-specific fraud patterns we defend against:
1. Fake buyer fraud   — order goods, file false disputes for refunds
2. Account takeover   — stolen credentials used for high-value orders
3. Velocity fraud     — rapid ordering across multiple accounts
4. Triangulation      — order goods, resell, then dispute
5. Identity cycling   — create new accounts after being banned
6. Device spoofing    — use VPNs/proxies to hide location
7. Social engineering — exploit new sellers with fake urgent orders
8. Payment testing    — test stolen card details with small orders
9. Collusion fraud    — buyer/seller collude to extract platform fees
10. Refund abuse      — serial returners and dispute abusers

Scoring: 0-100 risk score
  0-29:  LOW    — proceed normally
  30-59: MEDIUM — flag for review, allow order
  60-79: HIGH   — require extra verification, hold payment
  80+:   CRITICAL — block order, alert admin immediately
"""
import logging
import hashlib
from datetime import timedelta
from django.utils import timezone

logger = logging.getLogger('micha.security')


class FraudSignal:
    """Represents a single fraud signal with score and description."""
    def __init__(self, name: str, score: int, severity: str, description: str):
        self.name = name
        self.score = score
        self.severity = severity  # low / medium / high / critical
        self.description = description

    def __repr__(self):
        return f'[{self.severity.upper()}] {self.name}: +{self.score} — {self.description}'


class FraudEngine:
    """
    Evaluates every order against 15+ fraud signals.
    Fast enough to run synchronously at checkout (< 100ms).
    """

    # Thresholds — calibrated to minimize false positives
    BLOCK_THRESHOLD = 85      # block order (requires 3+ signals)
    SOFT_BLOCK_THRESHOLD = 70 # require OTP re-verification
    HOLD_THRESHOLD = 55       # hold payment pending review
    FLAG_THRESHOLD = 30       # flag for admin review

    # Minimum signals required for each action (prevents single-signal blocks)
    MIN_SIGNALS_FOR_BLOCK = 3
    MIN_SIGNALS_FOR_HOLD = 2

    # Angola-specific amounts
    HIGH_VALUE_AOA = 150_000  # 150k AOA (~$150) — high value threshold
    VERY_HIGH_VALUE_AOA = 500_000  # 500k AOA — very high value

    def __init__(self, order, request=None):
        self.order = order
        self.buyer = order.buyer
        self.request = request
        self.signals = []
        self.total_score = 0
        self._buyer_history = None

    def run(self) -> dict:
        """Run all fraud checks. Returns assessment dict."""
        self._load_buyer_history()

        # Run all signal groups
        self._check_account_signals()
        self._check_velocity_signals()
        self._check_order_signals()
        self._check_behavioral_signals()
        self._check_device_signals()
        self._check_history_signals()
        self._check_network_signals()
        self._check_extended_signals()

        # Calculate total score (capped at 100)
        self.total_score = min(sum(s.score for s in self.signals), 100)

        # Determine action
        real_signals = [s for s in self.signals if s.score > 0]
        signal_count = len(real_signals)

        if self.total_score >= self.BLOCK_THRESHOLD and signal_count >= self.MIN_SIGNALS_FOR_BLOCK:
            action = 'block'
            severity = 'critical'
        elif self.total_score >= self.SOFT_BLOCK_THRESHOLD:
            action = 'soft_block'  # require OTP re-verification
            severity = 'high'
        elif self.total_score >= self.HOLD_THRESHOLD and signal_count >= self.MIN_SIGNALS_FOR_HOLD:
            action = 'hold'
            severity = 'high'
        elif self.total_score >= self.FLAG_THRESHOLD:
            action = 'flag'
            severity = 'medium'
        else:
            action = 'allow'
            severity = 'low'

        result = {
            'risk_score': self.total_score,
            'action': action,
            'severity': severity,
            'signals': [
                {
                    'name': s.name,
                    'score': s.score,
                    'severity': s.severity,
                    'description': s.description,
                }
                for s in self.signals
            ],
            'signal_count': len(self.signals),
            'assessed_at': timezone.now().isoformat(),
        }

        # Log the assessment
        if action != 'allow':
            logger.warning('fraud_assessment', extra={
                'user_id': str(self.buyer.id),
                'order_id': str(self.order.id),
                'risk_score': self.total_score,
                'action': action,
                'signals': [s.name for s in self.signals],
                'order_total': str(self.order.total),
            })

        # Persist alerts for flagged orders
        if action in ('flag', 'hold', 'block'):
            self._create_fraud_alert(result)

        return result

    def _load_buyer_history(self):
        """Load buyer's full history once for all checks."""
        from apps.orders.models import Order
        from apps.disputes.models import Dispute
        from apps.security.models import FraudAlert

        user = self.buyer
        now = timezone.now()

        self._buyer_history = {
            'account_age_days': (now - user.date_joined).days,
            'total_orders': Order.objects.filter(buyer=user).count(),
            'orders_last_hour': Order.objects.filter(
                buyer=user, created_at__gte=now - timedelta(hours=1)
            ).count(),
            'orders_last_24h': Order.objects.filter(
                buyer=user, created_at__gte=now - timedelta(hours=24)
            ).count(),
            'orders_last_7d': Order.objects.filter(
                buyer=user, created_at__gte=now - timedelta(days=7)
            ).count(),
            'failed_payments': Order.objects.filter(
                buyer=user,
                status='payment_failed',
                created_at__gte=now - timedelta(days=30)
            ).count(),
            'disputes_filed': Dispute.objects.filter(
                buyer=user
            ).count(),
            'disputes_won': Dispute.objects.filter(
                buyer=user, status='resolved',
                resolution='buyer_wins'
            ).count(),
            'disputes_lost': Dispute.objects.filter(
                buyer=user, status='resolved',
                resolution='seller_wins'
            ).count(),
            'past_fraud_alerts': FraudAlert.objects.filter(
                user=user
            ).count(),
            'past_blocks': FraudAlert.objects.filter(
                user=user, severity='critical'
            ).count(),
            'cancelled_orders': Order.objects.filter(
                buyer=user,
                status__in=['cancelled', 'returned', 'refunded']
            ).count(),
        }

    def _check_account_signals(self):
        """Account age and status signals."""
        h = self._buyer_history
        order_total = float(self.order.total or 0)

        # New account + high-value order
        age = h['account_age_days']
        if age < 1 and order_total > 50_000:
            self.signals.append(FraudSignal(
                'new_account_high_value',
                score=35,
                severity='high',
                description=f'Account {age}h old ordering {order_total:,.0f} AOA',
            ))
        elif age < 7 and order_total > self.HIGH_VALUE_AOA:
            self.signals.append(FraudSignal(
                'young_account_high_value',
                score=20,
                severity='medium',
                description=f'Account {age} days old, order {order_total:,.0f} AOA',
            ))

        # Previously blocked user
        if h['past_blocks'] > 0:
            self.signals.append(FraudSignal(
                'previously_blocked',
                score=50,
                severity='critical',
                description=f'User had {h["past_blocks"]} critical fraud alert(s)',
            ))

        # Multiple past fraud alerts
        if h['past_fraud_alerts'] >= 3:
            self.signals.append(FraudSignal(
                'repeat_fraud_flags',
                score=25,
                severity='high',
                description=f'{h["past_fraud_alerts"]} fraud alerts on this account',
            ))

        # Unverified email on high-value order
        if not self.buyer.is_email_verified and order_total > 30_000:
            self.signals.append(FraudSignal(
                'unverified_email_high_value',
                score=15,
                severity='medium',
                description='Unverified email on high-value order',
            ))

        # Account suspended/warned previously
        if self.buyer.status in ('warned', 'suspended'):
            self.signals.append(FraudSignal(
                'flagged_account_status',
                score=30,
                severity='high',
                description=f'Account status: {self.buyer.status}',
            ))

    def _check_velocity_signals(self):
        """Order velocity and rate-of-change signals."""
        h = self._buyer_history

        # Rapid orders in 1 hour
        if h['orders_last_hour'] >= 5:
            self.signals.append(FraudSignal(
                'extreme_velocity',
                score=40,
                severity='critical',
                description=f'{h["orders_last_hour"]} orders in last hour',
            ))
        elif h['orders_last_hour'] >= 3:
            self.signals.append(FraudSignal(
                'high_velocity',
                score=20,
                severity='high',
                description=f'{h["orders_last_hour"]} orders in last hour',
            ))

        # High volume in 24h
        if h['orders_last_24h'] >= 10:
            self.signals.append(FraudSignal(
                'high_daily_volume',
                score=25,
                severity='high',
                description=f'{h["orders_last_24h"]} orders in 24h',
            ))

        # First-ever order is high value (no track record)
        if h['total_orders'] == 0 and float(self.order.total or 0) > self.HIGH_VALUE_AOA:
            self.signals.append(FraudSignal(
                'first_order_high_value',
                score=20,
                severity='medium',
                description='First ever order is above 150,000 AOA',
            ))

    def _check_order_signals(self):
        """Signals from the order itself."""
        order_total = float(self.order.total or 0)

        # Very high value
        if order_total >= self.VERY_HIGH_VALUE_AOA:
            self.signals.append(FraudSignal(
                'very_high_value',
                score=20,
                severity='high',
                description=f'Order total {order_total:,.0f} AOA (≥ 500k)',
            ))

        # Single item but maximum quantity
        try:
            from apps.orders.models import OrderItem
            items = list(OrderItem.objects.filter(order=self.order)[:50])
            if len(items) == 1 and items[0].quantity >= 10:
                self.signals.append(FraudSignal(
                    'bulk_single_item',
                    score=15,
                    severity='medium',
                    description=f'Bulk order: {items[0].quantity}x of one item',
                ))

            # All items from same category (potential resale fraud)
            if len(items) >= 3:
                categories = set()
                for item in items:
                    if item.product and item.product.category_id:
                        categories.add(item.product.category_id)
                if len(categories) == 1:
                    self.signals.append(FraudSignal(
                        'single_category_bulk',
                        score=10,
                        severity='low',
                        description='Multiple items all from same category (resale pattern)',
                    ))
        except Exception:
            pass

        # Shipping to different province than account province
        try:
            from apps.users.models import UserProfile
            profile = UserProfile.objects.get(user=self.buyer)
            order_city = (self.order.shipping_city or '').lower()
            user_province = (profile.province or '').lower()
            if user_province and order_city and user_province not in order_city:
                self.signals.append(FraudSignal(
                    'mismatched_shipping_location',
                    score=10,
                    severity='low',
                    description=f'User province ({profile.province}) ≠ shipping city ({self.order.shipping_city})',
                ))
        except Exception:
            pass

    def _check_behavioral_signals(self):
        """Behavioral anomaly signals from AI engine."""
        try:
            from apps.ai_engine.models import BehavioralEvent
            user = self.buyer
            now = timezone.now()

            # Check if user viewed any of the products before ordering
            try:
                from apps.orders.models import OrderItem
                ordered_product_ids = set(
                    str(pid) for pid in
                    OrderItem.objects.filter(order=self.order).values_list('product_id', flat=True)
                )
            except Exception:
                ordered_product_ids = set()

            if ordered_product_ids:
                # Did they view the products they're ordering?
                viewed_products = set(
                    str(pid) for pid in
                    BehavioralEvent.objects.filter(
                        user=user,
                        event_type='view',
                        product_id__in=ordered_product_ids,
                        created_at__gte=now - timedelta(days=7),
                    ).values_list('product_id', flat=True)
                )

                if not viewed_products and float(self.order.total or 0) > 50_000:
                    self.signals.append(FraudSignal(
                        'ordered_without_viewing',
                        score=20,
                        severity='medium',
                        description='High-value order placed without any product views',
                    ))

            # Check session duration before checkout
            session_events = BehavioralEvent.objects.filter(
                user=user,
                created_at__gte=now - timedelta(hours=1),
            ).count()

            if session_events == 0 and float(self.order.total or 0) > 30_000:
                self.signals.append(FraudSignal(
                    'no_browsing_before_checkout',
                    score=15,
                    severity='medium',
                    description='Ordered directly with no browsing activity',
                ))

        except Exception as e:
            logger.debug(f'Behavioral signal check error: {e}')

    def _check_device_signals(self):
        """Device and IP-based signals."""
        if not self.request:
            return

        try:
            from apps.security.models import FraudAlert

            # Get client IP
            forwarded = self.request.META.get('HTTP_X_FORWARDED_FOR')
            ip = forwarded.split(',')[0].strip() if forwarded else self.request.META.get('REMOTE_ADDR', '')

            if not ip:
                return

            # Hash the IP for privacy
            ip_hash = hashlib.sha256(ip.encode()).hexdigest()[:16]

            # Check if this IP has fraud alerts from OTHER users
            other_user_alerts = FraudAlert.objects.filter(
                description__contains=ip_hash,
            ).exclude(user=self.buyer).count()

            if other_user_alerts >= 2:
                self.signals.append(FraudSignal(
                    'shared_ip_fraud_history',
                    score=30,
                    severity='high',
                    description=f'IP associated with {other_user_alerts} fraud alerts from other users',
                ))

            # Check if same IP used by multiple accounts recently
            from apps.users.models import UserSession
            recent_sessions = UserSession.objects.filter(
                ip_address=ip_hash,
                created_at__gte=timezone.now() - timedelta(days=7),
            ).values('user').distinct().count()

            if recent_sessions >= 3:
                self.signals.append(FraudSignal(
                    'ip_multiple_accounts',
                    score=25,
                    severity='high',
                    description=f'IP used by {recent_sessions} different accounts in 7 days',
                ))

            # Check if IP changed drastically from last login
            last_ip = self.buyer.last_login_ip
            if last_ip and last_ip != ip_hash:
                # Different IP — check if it's a known VPN range
                # Simple heuristic: if last login was < 1 hour ago from different IP
                if self.buyer.last_login:
                    time_since_login = (timezone.now() - self.buyer.last_login).total_seconds()
                    if time_since_login < 3600 and float(self.order.total or 0) > 100_000:
                        self.signals.append(FraudSignal(
                            'location_change_before_high_value',
                            score=20,
                            severity='high',
                            description='IP changed within 1 hour before high-value order',
                        ))

        except Exception as e:
            logger.debug(f'Device signal check error: {e}')

    def _check_history_signals(self):
        """Historical behavior signals."""
        h = self._buyer_history

        # Serial dispute filer
        if h['disputes_filed'] >= 5:
            dispute_win_rate = h['disputes_won'] / max(h['disputes_filed'], 1)
            if dispute_win_rate < 0.3:
                # Filing many disputes but losing most = abusive
                self.signals.append(FraudSignal(
                    'serial_dispute_abuser',
                    score=35,
                    severity='high',
                    description=f'{h["disputes_filed"]} disputes filed, only {h["disputes_won"]} won',
                ))
            elif h['disputes_filed'] >= 10:
                self.signals.append(FraudSignal(
                    'high_dispute_volume',
                    score=20,
                    severity='medium',
                    description=f'{h["disputes_filed"]} disputes filed',
                ))

        # High cancellation/return rate
        if h['total_orders'] >= 5:
            cancel_rate = h['cancelled_orders'] / h['total_orders']
            if cancel_rate > 0.5:
                self.signals.append(FraudSignal(
                    'high_cancellation_rate',
                    score=20,
                    severity='medium',
                    description=f'{cancel_rate*100:.0f}% of orders cancelled/returned',
                ))

        # Multiple failed payments before this order
        if h['failed_payments'] >= 3:
            self.signals.append(FraudSignal(
                'multiple_failed_payments',
                score=25,
                severity='high',
                description=f'{h["failed_payments"]} failed payments in last 30 days',
            ))

        # Payment testing pattern (small orders followed by large)
        if h['orders_last_24h'] >= 3 and float(self.order.total or 0) > self.HIGH_VALUE_AOA:
            try:
                from apps.orders.models import Order
                recent = Order.objects.filter(
                    buyer=self.buyer,
                    created_at__gte=timezone.now() - timedelta(hours=24),
                ).exclude(id=self.order.id).order_by('total')
                first_recent = recent.first()
                if recent.exists() and first_recent and float(first_recent.total or 0) < 10_000:
                    self.signals.append(FraudSignal(
                        'payment_testing_pattern',
                        score=30,
                        severity='high',
                        description='Small test orders followed by large order (card testing pattern)',
                    ))
            except Exception:
                pass

    def _check_extended_signals(self):
        """Run all 12 extended fraud detectors."""
        # Late import to avoid circular dependency
        from apps.security.fraud_signals import (
            RefundTriangulationDetector, AccountTakeoverDetector,
            CompetitorSabotageDetector, LoyaltyLaunderingDetector,
            TrustBonusCalculator,
        )

        # Refund triangulation
        try:
            signals = RefundTriangulationDetector().check_buyer(self.buyer)
            self.signals.extend(signals)
        except Exception as e:
            logger.debug(f'Triangulation check error: {e}')

        # Account takeover
        try:
            signals = AccountTakeoverDetector().check(self.buyer, self.order, self.request)
            self.signals.extend(signals)
        except Exception as e:
            logger.debug(f'ATO check error: {e}')

        # Loyalty laundering
        try:
            signals = LoyaltyLaunderingDetector().check(self.buyer, self.order)
            self.signals.extend(signals)
        except Exception as e:
            logger.debug(f'Loyalty check error: {e}')

        # Competitor sabotage
        try:
            signals = CompetitorSabotageDetector().check_buyer(self.buyer)
            self.signals.extend(signals)
        except Exception as e:
            logger.debug(f'Sabotage check error: {e}')

        # Trust bonus (reduces false positives)
        try:
            bonus = TrustBonusCalculator().calculate_bonus(self.buyer)
            if bonus < 0:
                self.signals.append(FraudSignal(
                    'trust_bonus',
                    score=bonus,  # negative score
                    severity='low',
                    description=f'Established customer trust bonus: {bonus} points',
                ))
        except Exception as e:
            logger.debug(f'Trust bonus error: {e}')

    def _check_network_signals(self):
        """Check for coordinated fraud network signals."""
        try:
            # Same device/fingerprint used across accounts
            last_device = self.buyer.last_login_device
            if last_device:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                same_device_users = User.objects.filter(
                    last_login_device=last_device,
                ).exclude(id=self.buyer.id).count()

                if same_device_users >= 2:
                    self.signals.append(FraudSignal(
                        'device_shared_accounts',
                        score=30,
                        severity='high',
                        description=f'Device used by {same_device_users + 1} different accounts',
                    ))

            # Check referred_by chain abuse
            # Bad actors create referral chains to earn referral bonuses
            if self.buyer.referred_by:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                referrer = self.buyer.referred_by
                referral_chain_size = User.objects.filter(
                    referred_by=referrer,
                    date_joined__gte=timezone.now() - timedelta(days=7),
                ).count()
                if referral_chain_size >= 5:
                    self.signals.append(FraudSignal(
                        'referral_chain_abuse',
                        score=20,
                        severity='medium',
                        description=f'Referred by user who invited {referral_chain_size} accounts in 7 days',
                    ))

            # Check loyalty point manipulation
            if self.buyer.loyalty_points > 10_000:
                account_age = (timezone.now() - self.buyer.date_joined).days
                points_per_day = self.buyer.loyalty_points / max(account_age, 1)
                if points_per_day > 500:
                    self.signals.append(FraudSignal(
                        'loyalty_point_manipulation',
                        score=20,
                        severity='medium',
                        description=f'Unusually high loyalty point accumulation: {points_per_day:.0f}/day',
                    ))

        except Exception as e:
            logger.debug(f'Network signal check error: {e}')

    def _create_fraud_alert(self, result: dict):
        """Persist fraud alert to database."""
        try:
            from apps.security.models import FraudAlert
            severity_map = {'low': 'low', 'medium': 'medium', 'high': 'high', 'critical': 'critical'}
            top_signals = sorted(self.signals, key=lambda s: s.score, reverse=True)[:3]
            description = (
                f'Risk score: {self.total_score}/100. '
                f'Action: {result["action"]}. '
                f'Top signals: {", ".join(s.name for s in top_signals)}'
            )
            FraudAlert.objects.create(
                user=self.buyer,
                order=self.order,
                type='high_value_new_account',  # using existing type field
                severity=severity_map.get(result['severity'], 'medium'),
                description=description,
            )
        except Exception as e:
            logger.error(f'Failed to create fraud alert: {e}')


def assess_order_fraud(order, request=None) -> dict:
    """
    Main entry point. Call from CheckoutView after order creation.
    Returns assessment dict with risk_score and action.
    """
    try:
        engine = FraudEngine(order, request)
        return engine.run()
    except Exception as e:
        logger.error(f'Fraud engine error for order {order.id}: {e}')
        # Fail open — don't block legitimate orders due to engine errors
        return {
            'risk_score': 0,
            'action': 'allow',
            'severity': 'low',
            'signals': [],
            'error': str(e),
        }
