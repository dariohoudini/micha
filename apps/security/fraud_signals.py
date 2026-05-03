"""
MICHA Extended Fraud Signals
================================
12 fraud pattern detectors specific to Angolan e-commerce.

Each detector is a standalone class with a .check() method
that returns a list of FraudSignal objects.
"""
import hashlib
import logging
from datetime import timedelta
from django.utils import timezone
from django.core.cache import cache
from apps.security.fraud_engine import FraudSignal

logger = logging.getLogger('micha.security')


# ─────────────────────────────────────────────────────────────────
# 1. GHOST SELLER DETECTION
# ─────────────────────────────────────────────────────────────────
class GhostSellerDetector:
    """
    Detects sellers who list products, collect payment, never deliver.
    Called on: every new order, seller registration, first sale.
    """
    def check_seller(self, seller) -> list:
        signals = []
        try:
            from apps.orders.models import Order
            now = timezone.now()
            days_old = (now - seller.date_joined).days

            total_orders = Order.objects.filter(seller=seller).count()
            delivered = Order.objects.filter(
                seller=seller, status__in=['delivered', 'completed']
            ).count()
            pending_unconfirmed = Order.objects.filter(
                seller=seller,
                status='confirmed',
                created_at__lte=now - timedelta(days=7),
            ).count()
            high_value_orders = Order.objects.filter(
                seller=seller, total__gte=200_000
            ).count()

            # New seller, immediate high-value sale
            if days_old < 30 and high_value_orders > 0 and total_orders < 3:
                signals.append(FraudSignal(
                    'ghost_seller_new_high_value',
                    score=35,
                    severity='high',
                    description=f'Seller {days_old}d old with high-value orders, no delivery history',
                ))

            # Has orders but delivery rate is suspiciously low
            if total_orders >= 3 and delivered == 0:
                signals.append(FraudSignal(
                    'ghost_seller_zero_delivery',
                    score=45,
                    severity='critical',
                    description=f'{total_orders} orders accepted, 0 delivered',
                ))

            # Orders sitting unactioned for 7+ days
            if pending_unconfirmed >= 2:
                signals.append(FraudSignal(
                    'ghost_seller_ignoring_orders',
                    score=30,
                    severity='high',
                    description=f'{pending_unconfirmed} orders unactioned for 7+ days',
                ))

            # Unverified seller with many orders
            try:
                from apps.verification.models import SellerVerification
                verified = SellerVerification.objects.filter(
                    seller=seller, status='approved'
                ).exists()
                if not verified and total_orders >= 5:
                    signals.append(FraudSignal(
                        'ghost_seller_unverified_active',
                        score=20,
                        severity='medium',
                        description=f'Unverified seller with {total_orders} orders',
                    ))
            except Exception:
                pass

        except Exception as e:
            logger.debug(f'GhostSellerDetector error: {e}')

        return signals


# ─────────────────────────────────────────────────────────────────
# 2. REFUND TRIANGULATION DETECTION
# ─────────────────────────────────────────────────────────────────
class RefundTriangulationDetector:
    """
    Detects buyers who receive goods then falsely dispute.
    Pattern: receive goods → wait short time → file dispute claiming non-delivery
    """
    def check_buyer(self, buyer) -> list:
        signals = []
        try:
            from apps.disputes.models import Dispute
            from apps.orders.models import Order
            now = timezone.now()

            # Disputes filed after delivery confirmation
            suspicious_disputes = 0
            for dispute in Dispute.objects.filter(buyer=buyer).select_related('order'):
                order = dispute.order
                if not order:
                    continue
                if order.status in ['delivered', 'completed']:
                    time_to_dispute = (dispute.created_at - order.updated_at).total_seconds() / 3600
                    if time_to_dispute < 2:  # disputed within 2h of delivery
                        suspicious_disputes += 1

            if suspicious_disputes >= 2:
                signals.append(FraudSignal(
                    'triangulation_fast_dispute',
                    score=40,
                    severity='high',
                    description=f'{suspicious_disputes} disputes filed within 2h of delivery',
                ))

            # Never leaves reviews (serial abusers avoid leaving traces)
            from apps.reviews.models import ProductReview
            total_completed = Order.objects.filter(
                buyer=buyer, status='completed'
            ).count()
            reviews_left = ProductReview.objects.filter(reviewer=buyer).count()
            if total_completed >= 5 and reviews_left == 0:
                signals.append(FraudSignal(
                    'triangulation_no_reviews',
                    score=15,
                    severity='low',
                    description=f'{total_completed} completed orders, 0 reviews left',
                ))

            # Multiple dispute wins across different sellers
            won_disputes = Dispute.objects.filter(
                buyer=buyer,
                status='resolved',
                resolution='buyer_wins',
            )
            if won_disputes.count() >= 3:
                seller_ids = set(won_disputes.values_list('seller_id', flat=True))
                if len(seller_ids) >= 3:
                    signals.append(FraudSignal(
                        'triangulation_multi_seller',
                        score=35,
                        severity='high',
                        description=f'Won disputes against {len(seller_ids)} different sellers',
                    ))

        except Exception as e:
            logger.debug(f'RefundTriangulationDetector error: {e}')

        return signals


# ─────────────────────────────────────────────────────────────────
# 3. ACCOUNT TAKEOVER DETECTION
# ─────────────────────────────────────────────────────────────────
class AccountTakeoverDetector:
    """
    Detects stolen credential usage.
    Pattern: attacker logs in from new device/IP → immediately places high-value order
    """
    def check(self, user, order, request=None) -> list:
        signals = []
        try:
            now = timezone.now()
            order_total = float(order.total or 0)

            # Password changed recently before high-value order
            from apps.users.models import PasswordHistory
            recent_pwd_change = PasswordHistory.objects.filter(
                user=user,
                created_at__gte=now - timedelta(hours=24),
            ).exists()
            if recent_pwd_change and order_total > 100_000:
                signals.append(FraudSignal(
                    'ato_password_changed_recently',
                    score=35,
                    severity='high',
                    description='Password changed within 24h before high-value order',
                ))

            # 2FA was disabled recently
            if not user.two_fa_enabled:
                from apps.users.models import UserActivityLog
                disabled_2fa = UserActivityLog.objects.filter(
                    user=user,
                    action__icontains='2fa_disabled',
                    created_at__gte=now - timedelta(days=3),
                ).exists()
                if disabled_2fa and order_total > 50_000:
                    signals.append(FraudSignal(
                        'ato_2fa_disabled_before_order',
                        score=30,
                        severity='high',
                        description='2FA disabled within 3 days before high-value order',
                    ))

            # New device/IP + immediate high-value order
            if request:
                forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
                current_ip = forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR', '')
                current_ip_hash = hashlib.sha256(current_ip.encode()).hexdigest()[:16]
                last_ip = user.last_login_ip

                if last_ip and last_ip != current_ip_hash and order_total > 75_000:
                    # Check how recent the last login was from old IP
                    if user.last_login:
                        hours_since_login = (now - user.last_login).total_seconds() / 3600
                        if hours_since_login < 48:
                            signals.append(FraudSignal(
                                'ato_new_ip_high_value',
                                score=30,
                                severity='high',
                                description=f'New IP address used within 48h, order {order_total:,.0f} AOA',
                            ))

            # Shipping address never used before + high value
            order_address = (order.shipping_address or '').lower().strip()
            if order_address and order_total > 100_000:
                from apps.shipping.models import ShippingAddress
                known_addresses = ShippingAddress.objects.filter(user=user)
                known_addr_texts = [
                    a.address_line.lower().strip()
                    for a in known_addresses
                    if a.address_line
                ]
                address_is_known = any(
                    order_address[:30] in addr or addr[:30] in order_address
                    for addr in known_addr_texts
                )
                if not address_is_known and known_addresses.exists():
                    signals.append(FraudSignal(
                        'ato_unknown_shipping_address',
                        score=20,
                        severity='medium',
                        description='High-value order to an address never used before',
                    ))

        except Exception as e:
            logger.debug(f'AccountTakeoverDetector error: {e}')

        return signals


# ─────────────────────────────────────────────────────────────────
# 4. MULTICAIXA PHONE ABUSE
# ─────────────────────────────────────────────────────────────────
class MulticaixaAbuseDetector:
    """
    Detects stolen Multicaixa credentials.
    Angola-specific: payment phone ≠ account phone is a major red flag.
    """
    def check(self, user, order, payment_phone=None) -> list:
        signals = []
        try:
            if not payment_phone:
                return signals

            # Normalize phones for comparison
            def normalize(phone):
                return ''.join(filter(str.isdigit, str(phone or '')))[-9:]

            payment_norm = normalize(payment_phone)
            account_norm = normalize(user.phone or '')

            # Payment phone doesn't match account phone
            if account_norm and payment_norm and payment_norm != account_norm:
                signals.append(FraudSignal(
                    'multicaixa_phone_mismatch',
                    score=25,
                    severity='high',
                    description='Payment phone number differs from account phone',
                ))

            # Same payment phone used across multiple accounts
            from django.contrib.auth import get_user_model
            User = get_user_model()
            accounts_with_phone = User.objects.filter(
                phone__icontains=payment_norm[-8:]
            ).exclude(id=user.id).count()
            if accounts_with_phone >= 2:
                signals.append(FraudSignal(
                    'multicaixa_phone_multi_account',
                    score=35,
                    severity='critical',
                    description=f'Payment phone linked to {accounts_with_phone + 1} accounts',
                ))

            # Multiple payment phone attempts before success
            # (would need payment attempt log — tracked via failed orders)
            from apps.orders.models import Order
            failed_with_different_phone = Order.objects.filter(
                buyer=user,
                status='payment_failed',
                created_at__gte=timezone.now() - timedelta(hours=2),
            ).count()
            if failed_with_different_phone >= 3:
                signals.append(FraudSignal(
                    'multicaixa_multiple_phone_attempts',
                    score=30,
                    severity='high',
                    description=f'{failed_with_different_phone} failed payment attempts in 2h (credential testing)',
                ))

        except Exception as e:
            logger.debug(f'MulticaixaAbuseDetector error: {e}')

        return signals


# ─────────────────────────────────────────────────────────────────
# 5. FAKE REVIEW NETWORK DETECTION
# ─────────────────────────────────────────────────────────────────
class FakeReviewDetector:
    """
    Detects coordinated fake review campaigns.
    Called when a review is submitted.
    """
    def check_review(self, review, reviewer_ip=None) -> list:
        signals = []
        try:
            from apps.reviews.models import ProductReview
            now = timezone.now()
            seller = review.product.store.owner if review.product else None
            reviewer = review.reviewer

            # Reviewer account too new
            account_age = (now - reviewer.date_joined).days
            if account_age < 3:
                signals.append(FraudSignal(
                    'fake_review_new_account',
                    score=30,
                    severity='high',
                    description=f'Reviewer account only {account_age} days old',
                ))

            # Reviewer never purchased from this seller
            from apps.orders.models import Order
            purchased_from_seller = Order.objects.filter(
                buyer=reviewer,
                seller=seller,
                status__in=['delivered', 'completed'],
            ).exists()
            if not purchased_from_seller:
                signals.append(FraudSignal(
                    'fake_review_no_purchase',
                    score=40,
                    severity='high',
                    description='Review submitted without verified purchase from this seller',
                ))

            # Reviewed 5+ sellers with 5 stars in one day
            five_star_today = ProductReview.objects.filter(
                reviewer=reviewer,
                rating=5,
                created_at__date=now.date(),
            ).count()
            if five_star_today >= 5:
                signals.append(FraudSignal(
                    'fake_review_mass_five_star',
                    score=45,
                    severity='critical',
                    description=f'{five_star_today} five-star reviews submitted today',
                ))

            # Multiple reviews from same IP on same seller
            if reviewer_ip and seller:
                ip_key = f'review_ip:{hashlib.sha256(reviewer_ip.encode()).hexdigest()[:8]}:{seller.id}'
                review_count = cache.get(ip_key, 0)
                cache.set(ip_key, review_count + 1, timeout=86400)
                if review_count >= 3:
                    signals.append(FraudSignal(
                        'fake_review_same_ip_same_seller',
                        score=50,
                        severity='critical',
                        description=f'{review_count + 1} reviews from same IP on same seller in 24h',
                    ))

        except Exception as e:
            logger.debug(f'FakeReviewDetector error: {e}')

        return signals


# ─────────────────────────────────────────────────────────────────
# 6. FLASH SALE BOT DETECTION
# ─────────────────────────────────────────────────────────────────
class FlashSaleBotDetector:
    """
    Detects automated scripts sniping flash sales.
    Called when cart_add happens during a flash sale.
    """
    def check(self, user, product, request=None) -> list:
        signals = []
        try:
            from apps.promotions.models import FlashSale
            now = timezone.now()

            flash = FlashSale.objects.filter(
                product=product,
                is_active=True,
                start_time__lte=now,
                end_time__gte=now,
            ).first()

            if not flash:
                return signals

            # Cart add within 5 seconds of flash sale start
            seconds_since_start = (now - flash.start_time).total_seconds()
            if seconds_since_start < 5:
                signals.append(FraudSignal(
                    'flash_bot_instant_add',
                    score=40,
                    severity='high',
                    description=f'Cart add {seconds_since_start:.1f}s after flash sale started (bot pattern)',
                ))

            # User clearing multiple flash sales today
            from apps.orders.models import OrderItem
            flash_orders_today = OrderItem.objects.filter(
                order__buyer=user,
                order__created_at__date=now.date(),
            ).count()
            if flash_orders_today >= 5:
                signals.append(FraudSignal(
                    'flash_bot_bulk_clearing',
                    score=35,
                    severity='high',
                    description=f'{flash_orders_today} flash sale items purchased today',
                ))

            # No browsing before checkout (direct URL hit)
            from apps.ai_engine.models import BehavioralEvent
            viewed_product = BehavioralEvent.objects.filter(
                user=user,
                product_id=str(product.id),
                event_type='view',
                created_at__gte=now - timedelta(minutes=10),
            ).exists()
            if not viewed_product:
                signals.append(FraudSignal(
                    'flash_bot_no_view',
                    score=25,
                    severity='medium',
                    description='Flash sale item added to cart without viewing product page',
                ))

            # Rate limit: same user + same flash product
            rate_key = f'flash_rate:{user.id}:{product.id}'
            attempts = cache.get(rate_key, 0)
            cache.set(rate_key, attempts + 1, timeout=300)
            if attempts >= 3:
                signals.append(FraudSignal(
                    'flash_bot_repeated_attempts',
                    score=30,
                    severity='high',
                    description=f'{attempts + 1} attempts on same flash sale item in 5 minutes',
                ))

        except Exception as e:
            logger.debug(f'FlashSaleBotDetector error: {e}')

        return signals


# ─────────────────────────────────────────────────────────────────
# 7. REFERRAL FARMING DETECTION
# ─────────────────────────────────────────────────────────────────
class ReferralFarmingDetector:
    """
    Detects fake account networks farming referral bonuses.
    """
    def check_referral(self, referrer, new_user, ip=None) -> list:
        signals = []
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            now = timezone.now()

            # How many referrals has this person made in 7 days?
            week_referrals = User.objects.filter(
                referred_by=referrer,
                date_joined__gte=now - timedelta(days=7),
            ).count()

            if week_referrals >= 10:
                signals.append(FraudSignal(
                    'referral_farm_high_volume',
                    score=50,
                    severity='critical',
                    description=f'{week_referrals} referrals in 7 days',
                ))
            elif week_referrals >= 5:
                signals.append(FraudSignal(
                    'referral_farm_suspicious_volume',
                    score=25,
                    severity='medium',
                    description=f'{week_referrals} referrals in 7 days',
                ))

            # Check if referral chain depth > 2
            if referrer.referred_by:
                signals.append(FraudSignal(
                    'referral_chain_depth',
                    score=15,
                    severity='low',
                    description='Referral chain depth > 2 (A→B→C pattern)',
                ))

            # IP-based: multiple referrals from same IP
            if ip:
                ip_key = f'ref_ip:{hashlib.sha256(ip.encode()).hexdigest()[:8]}'
                ip_count = cache.get(ip_key, 0)
                cache.set(ip_key, ip_count + 1, timeout=86400)
                if ip_count >= 3:
                    signals.append(FraudSignal(
                        'referral_same_ip',
                        score=35,
                        severity='high',
                        description=f'{ip_count + 1} referral registrations from same IP in 24h',
                    ))

            # Referred accounts that never purchase (farming pattern)
            referred_users = User.objects.filter(referred_by=referrer)
            if referred_users.count() >= 5:
                from apps.orders.models import Order
                purchasers = Order.objects.filter(
                    buyer__in=referred_users
                ).values('buyer').distinct().count()
                purchase_rate = purchasers / referred_users.count()
                if purchase_rate < 0.1:  # < 10% of referred users ever bought
                    signals.append(FraudSignal(
                        'referral_zero_purchase_rate',
                        score=40,
                        severity='high',
                        description=f'Only {purchase_rate*100:.0f}% of referred users ever purchased',
                    ))

        except Exception as e:
            logger.debug(f'ReferralFarmingDetector error: {e}')

        return signals


# ─────────────────────────────────────────────────────────────────
# 8. SELLER IDENTITY FRAUD
# ─────────────────────────────────────────────────────────────────
class SellerIdentityFraudDetector:
    """
    Detects impersonation of legitimate sellers.
    """
    def check_seller_registration(self, seller, nif=None, store_logo_hash=None) -> list:
        signals = []
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()

            # Duplicate NIF
            if nif:
                from apps.verification.models import SellerVerification
                existing_nif = SellerVerification.objects.filter(
                    id_number=nif
                ).exclude(seller=seller).count()
                if existing_nif > 0:
                    signals.append(FraudSignal(
                        'identity_duplicate_nif',
                        score=60,
                        severity='critical',
                        description=f'NIF already registered to {existing_nif} other seller(s)',
                    ))

            # Duplicate store logo/banner (image hash match)
            if store_logo_hash:
                from apps.stores.models import Store
                duplicate_logo = Store.objects.filter(
                    banner_image__icontains=store_logo_hash,
                ).exclude(owner=seller).count()
                if duplicate_logo > 0:
                    signals.append(FraudSignal(
                        'identity_duplicate_store_image',
                        score=40,
                        severity='high',
                        description='Store image identical to existing verified seller',
                    ))

            # Phone used on banned account
            if seller.phone:
                banned_phone = User.objects.filter(
                    phone=seller.phone,
                    status='banned',
                ).exclude(id=seller.id).count()
                if banned_phone > 0:
                    signals.append(FraudSignal(
                        'identity_banned_phone',
                        score=70,
                        severity='critical',
                        description='Phone number linked to a banned account',
                    ))

        except Exception as e:
            logger.debug(f'SellerIdentityFraudDetector error: {e}')

        return signals


# ─────────────────────────────────────────────────────────────────
# 9. PRICE MANIPULATION DETECTION
# ─────────────────────────────────────────────────────────────────
class PriceManipulationDetector:
    """
    Detects fake discounts and price manipulation.
    Called when a product is created/updated.
    """
    def check_product(self, product) -> list:
        signals = []
        try:
            price = float(product.price or 0)
            compare = float(product.compare_at_price or 0)

            # Fake discount: compare_at > 3x current price
            if compare > 0 and price > 0:
                ratio = compare / price
                if ratio > 5:
                    signals.append(FraudSignal(
                        'price_fake_discount_extreme',
                        score=40,
                        severity='high',
                        description=f'Compare price {ratio:.1f}x current price (fake discount)',
                    ))
                elif ratio > 3:
                    signals.append(FraudSignal(
                        'price_fake_discount',
                        score=20,
                        severity='medium',
                        description=f'Compare price {ratio:.1f}x current price (suspicious discount)',
                    ))

            # Rapid repricing
            from apps.collections.models import PriceHistory
            week_ago = timezone.now() - timedelta(days=7)
            price_changes = PriceHistory.objects.filter(
                product=product,
                recorded_at__gte=week_ago,
            ).count()
            if price_changes >= 10:
                signals.append(FraudSignal(
                    'price_rapid_repricing',
                    score=25,
                    severity='medium',
                    description=f'Price changed {price_changes} times in 7 days',
                ))

            # Far below category average (suspicious underpricing — could be stolen goods)
            if product.category:
                from apps.products.models import Product
                from django.db.models import Avg
                category_avg = Product.objects.filter(
                    category=product.category,
                    is_active=True,
                ).exclude(id=product.id).aggregate(avg=Avg('price'))['avg']

                if category_avg and price < category_avg * 0.2:
                    signals.append(FraudSignal(
                        'price_suspiciously_low',
                        score=20,
                        severity='medium',
                        description=f'Price {price:,.0f} AOA is <20% of category average ({category_avg:,.0f} AOA)',
                    ))

        except Exception as e:
            logger.debug(f'PriceManipulationDetector error: {e}')

        return signals


# ─────────────────────────────────────────────────────────────────
# 10. LOYALTY POINT LAUNDERING
# ─────────────────────────────────────────────────────────────────
class LoyaltyLaunderingDetector:
    """
    Detects abuse of the loyalty points system.
    """
    def check(self, user, order) -> list:
        signals = []
        try:
            order_total = float(order.total or 0)

            # Points used then disputed (withdraw via dispute)
            if user.loyalty_points > 0 and order.store_credit_used:
                from apps.disputes.models import Dispute
                store_credit_disputes = Dispute.objects.filter(
                    buyer=user,
                    created_at__gte=timezone.now() - timedelta(days=30),
                ).count()
                if store_credit_disputes >= 2:
                    signals.append(FraudSignal(
                        'loyalty_dispute_after_credit',
                        score=30,
                        severity='high',
                        description='Used store credit then disputed multiple orders',
                    ))

            # Referring own seller (buyer and seller are connected)
            try:
                from apps.stores.models import Store
                seller_store = Store.objects.filter(owner=order.seller).first()
                if seller_store and user.referred_by == order.seller:
                    signals.append(FraudSignal(
                        'loyalty_self_referral_purchase',
                        score=35,
                        severity='high',
                        description='Buyer was referred by the seller they are purchasing from',
                    ))
            except Exception:
                pass

        except Exception as e:
            logger.debug(f'LoyaltyLaunderingDetector error: {e}')

        return signals


# ─────────────────────────────────────────────────────────────────
# 11. COMPETITOR SABOTAGE DETECTION
# ─────────────────────────────────────────────────────────────────
class CompetitorSabotageDetector:
    """
    Detects coordinated attacks on specific sellers.
    Pattern: place orders → cancel before shipment → damage seller metrics
    """
    def check_buyer(self, buyer) -> list:
        signals = []
        try:
            from apps.orders.models import Order
            now = timezone.now()

            # Cancelled orders across many different sellers
            recent_cancelled = Order.objects.filter(
                buyer=buyer,
                status='cancelled',
                created_at__gte=now - timedelta(days=30),
            )
            sellers_sabotaged = recent_cancelled.values('seller').distinct().count()

            if sellers_sabotaged >= 4 and recent_cancelled.count() >= 5:
                signals.append(FraudSignal(
                    'sabotage_multi_seller_cancel',
                    score=35,
                    severity='high',
                    description=f'{recent_cancelled.count()} cancellations targeting {sellers_sabotaged} sellers in 30 days',
                ))

            # Pre-shipment cancellations only (maximizes damage, no financial loss to attacker)
            early_cancels = Order.objects.filter(
                buyer=buyer,
                status='cancelled',
                created_at__gte=now - timedelta(days=30),
            ).filter(
                # Cancelled while still in pending/confirmed status
                statuslog__to_status='cancelled',
                statuslog__from_status__in=['pending', 'confirmed'],
            ).distinct().count()

            if early_cancels >= 5:
                signals.append(FraudSignal(
                    'sabotage_pre_shipment_pattern',
                    score=25,
                    severity='medium',
                    description=f'{early_cancels} orders cancelled before shipment in 30 days',
                ))

        except Exception as e:
            logger.debug(f'CompetitorSabotageDetector error: {e}')

        return signals


# ─────────────────────────────────────────────────────────────────
# 12. CHAT PAYMENT DIVERSION
# ─────────────────────────────────────────────────────────────────
class ChatDiversionDetector:
    """
    Detects sellers trying to move payments off-platform via chat.
    Already partially handled by content_filter.py — this adds fraud scoring.
    """
    DIVERSION_PATTERNS = [
        'paga directo', 'paga no whatsapp', 'fora da plataforma',
        'transferência directa', 'multicaixa directo',
        'manda o dinheiro', 'paga primeiro', 'express directo',
        'paga pelo zap', 'zap me', 'me manda pelo boa',
        'boa directo', 'manda por boa', 'fora do micha',
    ]

    def check_message(self, message_content, sender, chat) -> list:
        signals = []
        try:
            content_lower = message_content.lower()
            matched = [p for p in self.DIVERSION_PATTERNS if p in content_lower]

            if matched:
                # Check if this seller has done this before
                from apps.chat.models import Message
                prior_flags = Message.objects.filter(
                    chat__seller=sender,
                    content__iregex='|'.join(self.DIVERSION_PATTERNS[:5]),
                ).exclude(chat=chat).count()

                score = 40 + min(prior_flags * 10, 30)
                signals.append(FraudSignal(
                    'chat_payment_diversion',
                    score=min(score, 70),
                    severity='critical' if prior_flags >= 2 else 'high',
                    description=f'Off-platform payment solicitation detected. Patterns: {matched}. Prior incidents: {prior_flags}',
                ))

        except Exception as e:
            logger.debug(f'ChatDiversionDetector error: {e}')

        return signals


# ─────────────────────────────────────────────────────────────────
# TRUST BONUS — Reduce false positives for loyal customers
# ─────────────────────────────────────────────────────────────────
class TrustBonusCalculator:
    """
    Gives established, verified, loyal users a trust bonus
    that reduces their effective fraud score.
    This is critical to prevent false positives on good customers.
    """
    def calculate_bonus(self, user) -> int:
        """Returns a negative number to subtract from fraud score."""
        bonus = 0
        try:
            from apps.orders.models import Order

            # Completed orders (most important)
            completed = Order.objects.filter(
                buyer=user, status__in=['delivered', 'completed']
            ).count()
            bonus += min(completed * 3, 20)  # up to -20 for 7+ completed orders

            # Account age
            age_days = (timezone.now() - user.date_joined).days
            if age_days > 365:
                bonus += 10
            elif age_days > 90:
                bonus += 5

            # Verified email + phone
            if user.is_email_verified:
                bonus += 5
            if user.is_phone_verified:
                bonus += 5

            # Loyalty points (demonstrates engagement)
            if user.loyalty_points > 500:
                bonus += 5

            # Has positive reviews (gives reviews = trustworthy)
            from apps.reviews.models import ProductReview
            reviews = ProductReview.objects.filter(reviewer=user).count()
            if reviews >= 3:
                bonus += 5

        except Exception as e:
            logger.debug(f'TrustBonusCalculator error: {e}')

        return -min(bonus, 30)  # max -30 trust bonus (caps at score reduction of 30)
