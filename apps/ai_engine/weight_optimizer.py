"""
MICHA Express — Feed Weight Optimizer
======================================
Validates and optimizes the personalization scoring weights
using real interaction data.

Current weights (guesses):
  view=1, dwell_10=2, dwell_30=4, dwell_60=6
  wishlist=3, cart_add=5, purchase=10, share=4

Goal: find weights that maximize CTR and purchase rate
from the personalised feed.

Usage:
  python manage.py shell
  from apps.ai_engine.weight_optimizer import WeightOptimizer
  report = WeightOptimizer.run()
"""
import logging
from datetime import timedelta
from django.utils import timezone
from django.db.models import Count

logger = logging.getLogger('micha.ai')


# ── Current weights ───────────────────────────────────────────────
CURRENT_WEIGHTS = {
    'view':          1.0,
    'dwell_10':      2.0,
    'dwell_30':      4.0,
    'dwell_60':      6.0,
    'scroll_images': 1.5,
    'read_reviews':  2.0,
    'wishlist_add':  3.0,
    'wishlist_remove': -1.0,
    'cart_add':      5.0,
    'cart_remove':   -2.0,
    'share':         4.0,
    'click_rec':     2.0,
    'search_click':  2.5,
    'checkout_start': 8.0,
    'purchase':      10.0,
    'bounce':        -0.5,
}

# Minimum data required for validation
MIN_INTERACTIONS = 100
MIN_USERS = 20
MIN_DAYS = 7


class WeightOptimizer:

    @classmethod
    def run(cls, days=30):
        """Main entry point — runs full validation and optimization."""
        print('\n' + '='*60)
        print('MICHA Feed Weight Optimizer')
        print('='*60)

        data = cls._collect_data(days)
        if not data['sufficient']:
            print(f'\n⚠️  Insufficient data for optimization:')
            print(f'   Interactions: {data["total_interactions"]} (need {MIN_INTERACTIONS})')
            print(f'   Users: {data["unique_users"]} (need {MIN_USERS})')
            print(f'\n   Run again after {MIN_DAYS} days of real usage.')
            print(f'\n   Current weights are reasonable defaults.')
            cls._print_current_weights()
            cls._print_data_collection_guide()
            return data

        report = cls._analyze(data)
        cls._print_report(report)
        return report

    @classmethod
    def _collect_data(cls, days):
        """Collect interaction and conversion data."""
        from apps.ai_engine.models import BehavioralEvent
        from apps.recommendations.models import ProductInteraction
        from apps.orders.models import Order

        since = timezone.now() - timedelta(days=days)

        try:
            events = BehavioralEvent.objects.filter(created_at__gte=since)
            interactions = ProductInteraction.objects.filter(created_at__gte=since)
            orders = Order.objects.filter(created_at__gte=since)

            total_interactions = events.count() + interactions.count()
            unique_users = events.values('user').distinct().count()

            # Event breakdown
            event_counts = dict(
                events.values('event_type')
                .annotate(count=Count('id'))
                .values_list('event_type', 'count')
            )

            # Conversion data
            purchase_users = set(
                interactions.filter(type='purchase')
                .values_list('user_id', flat=True)
            )
            cart_users = set(
                interactions.filter(type='cart_add')
                .values_list('user_id', flat=True)
            )

            return {
                'sufficient': total_interactions >= MIN_INTERACTIONS and unique_users >= MIN_USERS,
                'total_interactions': total_interactions,
                'unique_users': unique_users,
                'event_counts': event_counts,
                'purchase_users': len(purchase_users),
                'cart_users': len(cart_users),
                'total_orders': orders.count(),
                'days': days,
                'events_qs': events,
                'interactions_qs': interactions,
            }
        except Exception as e:
            logger.error(f'Weight optimizer data collection failed: {e}')
            return {
                'sufficient': False,
                'total_interactions': 0,
                'unique_users': 0,
                'error': str(e),
            }

    @classmethod
    def _analyze(cls, data):
        """
        Analyze which interaction signals actually predict purchases.

        Method: For each event type, calculate:
        - P(purchase | event occurred) = purchase rate given interaction
        - lift = P(purchase|event) / P(purchase|no event)
        - The lift tells us how much each signal matters
        """

        results = {}
        baseline_purchase_rate = (
            data['purchase_users'] / data['unique_users']
            if data['unique_users'] > 0 else 0
        )

        for event_type, count in data['event_counts'].items():
            if count < 10:
                continue

            # Users who performed this event
            event_user_ids = set(
                data['events_qs'].filter(event_type=event_type)
                .values_list('user_id', flat=True)
            )

            # Of those, how many purchased?
            purchased_after_event = len(
                event_user_ids & data.get('purchase_users_set', set())
            )

            purchase_rate = (
                purchased_after_event / len(event_user_ids)
                if event_user_ids else 0
            )

            lift = (
                purchase_rate / baseline_purchase_rate
                if baseline_purchase_rate > 0 else 1.0
            )

            results[event_type] = {
                'count': count,
                'purchase_rate': round(purchase_rate, 3),
                'lift': round(lift, 2),
                'current_weight': CURRENT_WEIGHTS.get(event_type, 1.0),
                'suggested_weight': round(lift * CURRENT_WEIGHTS.get(event_type, 1.0), 1),
            }

        # Sort by lift
        sorted_results = dict(
            sorted(results.items(), key=lambda x: x[1]['lift'], reverse=True)
        )

        return {
            'sufficient': True,
            'baseline_purchase_rate': round(baseline_purchase_rate, 3),
            'event_analysis': sorted_results,
            'current_weights': CURRENT_WEIGHTS,
            'suggested_weights': {
                k: v['suggested_weight']
                for k, v in sorted_results.items()
            },
        }

    @classmethod
    def _print_current_weights(cls):
        print('\nCurrent weights:')
        for event, weight in CURRENT_WEIGHTS.items():
            bar = '█' * int(abs(weight)) + ('▓' if weight < 0 else '')
            sign = '-' if weight < 0 else '+'
            print(f'  {event:<20} {sign}{abs(weight):.1f}  {bar}')

    @classmethod
    def _print_report(cls, report):
        print(f'\nBaseline purchase rate: {report["baseline_purchase_rate"]*100:.1f}%')
        print(f'\n{"Event":<22} {"Count":>6} {"P(buy|event)":>12} {"Lift":>6} {"Current W":>10} {"Suggested W":>12}')
        print('-' * 75)
        for event, stats in report['event_analysis'].items():
            lift_indicator = '🔥' if stats['lift'] > 2 else '📈' if stats['lift'] > 1 else '📉'
            print(f'{event:<22} {stats["count"]:>6} {stats["purchase_rate"]*100:>11.1f}% {stats["lift"]:>6.2f}x {stats["current_weight"]:>10.1f} {stats["suggested_weight"]:>12.1f} {lift_indicator}')

        print('\n✅ Suggested weight updates:')
        for event, weight in report['suggested_weights'].items():
            current = CURRENT_WEIGHTS.get(event, 1.0)
            change = weight - current
            direction = '↑' if change > 0 else '↓' if change < 0 else '='
            print(f'  {event:<22} {current:.1f} → {weight:.1f} {direction}')

    @classmethod
    def _print_data_collection_guide(cls):
        print("""
📊 Data collection checklist:
   ✅ TrackEventView wired to frontend (/api/v1/ai/event/)
   ✅ BehavioralEvent model ready
   ✅ ProductInteraction model ready

   Events being tracked:
   • view          — user views a product
   • dwell_10/30/60 — time spent on product page
   • scroll_images — scrolled through images (high intent)
   • read_reviews  — read reviews (high intent)
   • wishlist_add  — added to wishlist
   • cart_add      — added to cart
   • share         — shared product
   • purchase      — completed purchase
   • bounce        — left quickly (negative signal)

   Run optimizer again with:
   python manage.py optimize_weights --days=30
""")


class ABTestManager:
    """
    Manages A/B tests for feed weight variants.
    Group 0 = control (current weights)
    Group 1 = variant (experimental weights)
    """

    VARIANTS = {
        0: CURRENT_WEIGHTS,  # Control
        1: {                  # Variant — higher purchase/cart weight
            **CURRENT_WEIGHTS,
            'purchase':      15.0,  # 10 → 15
            'cart_add':      8.0,   # 5 → 8
            'wishlist_add':  4.0,   # 3 → 4
            'dwell_60':      8.0,   # 6 → 8
            'bounce':        -1.0,  # -0.5 → -1.0
        },
    }

    @classmethod
    def get_weights(cls, user):
        """Returns weights for user's A/B group."""
        group = getattr(user, 'ab_test_group', 0)
        return cls.VARIANTS.get(group, CURRENT_WEIGHTS)

    @classmethod
    def get_results(cls, days=14):
        """Compare conversion rates between A/B groups."""
        from apps.recommendations.models import ProductInteraction
        from django.contrib.auth import get_user_model

        User = get_user_model()
        since = timezone.now() - timedelta(days=days)
        results = {}

        for group_id in [0, 1]:
            group_users = User.objects.filter(
                id__in=[u.id for u in User.objects.all() if getattr(u, 'ab_test_group', 0) == group_id]
            )
            total = group_users.count()
            if total == 0:
                continue

            purchasers = ProductInteraction.objects.filter(
                user__in=group_users,
                type='purchase',
                created_at__gte=since,
            ).values('user').distinct().count()

            results[group_id] = {
                'total_users': total,
                'purchasers': purchasers,
                'conversion_rate': round(purchasers / total * 100, 2),
                'variant': 'control' if group_id == 0 else 'variant',
                'weights': cls.VARIANTS[group_id],
            }

        if len(results) == 2:
            lift = results[1]['conversion_rate'] - results[0]['conversion_rate']
            results['lift_pp'] = round(lift, 2)
            results['winner'] = 'variant' if lift > 0 else 'control'

        return results


class FeedQualityMonitor:
    """
    Tracks feed quality metrics in real time.
    Run daily to check if personalization is working.
    """

    @classmethod
    def daily_report(cls):
        """Generate daily feed quality report."""
        from apps.ai_engine.models import BehavioralEvent
        from apps.recommendations.models import ProductInteraction
        from django.utils import timezone
        from datetime import timedelta

        yesterday = timezone.now() - timedelta(days=1)
        today = timezone.now()

        # Feed CTR: views that led to cart_add within same session
        views_today = BehavioralEvent.objects.filter(
            event_type='view',
            created_at__gte=yesterday,
        ).count()

        cart_adds_today = BehavioralEvent.objects.filter(
            event_type='cart_add',
            created_at__gte=yesterday,
        ).count()

        purchases_today = ProductInteraction.objects.filter(
            type='purchase',
            created_at__gte=yesterday,
        ).count()

        # Click-through rate from feed
        feed_clicks = BehavioralEvent.objects.filter(
            event_type='click_rec',
            source='home_feed',
            created_at__gte=yesterday,
        ).count()

        report = {
            'date': yesterday.date().isoformat(),
            'views': views_today,
            'cart_adds': cart_adds_today,
            'purchases': purchases_today,
            'feed_clicks': feed_clicks,
            'view_to_cart_rate': round(cart_adds_today / views_today * 100, 2) if views_today else 0,
            'cart_to_purchase_rate': round(purchases_today / cart_adds_today * 100, 2) if cart_adds_today else 0,
        }

        logger.info('feed_quality_report', extra=report)
        return report

    @classmethod
    def check_weight_drift(cls):
        """
        Alert if interaction patterns shift significantly.
        This means our weights may be becoming stale.
        """
        from apps.ai_engine.models import BehavioralEvent
        from django.utils import timezone
        from datetime import timedelta

        # Compare last 7 days vs previous 7 days
        week_ago = timezone.now() - timedelta(days=7)
        two_weeks_ago = timezone.now() - timedelta(days=14)

        recent = BehavioralEvent.objects.filter(created_at__gte=week_ago)
        previous = BehavioralEvent.objects.filter(
            created_at__gte=two_weeks_ago,
            created_at__lt=week_ago,
        )

        if recent.count() < 50 or previous.count() < 50:
            return {'status': 'insufficient_data'}

        from django.db.models import Count
        recent_dist = dict(
            recent.values('event_type').annotate(c=Count('id')).values_list('event_type', 'c')
        )
        prev_dist = dict(
            previous.values('event_type').annotate(c=Count('id')).values_list('event_type', 'c')
        )

        # Normalize
        recent_total = sum(recent_dist.values()) or 1
        prev_total = sum(prev_dist.values()) or 1

        drift = {}
        for event in set(list(recent_dist) + list(prev_dist)):
            r = recent_dist.get(event, 0) / recent_total
            p = prev_dist.get(event, 0) / prev_total
            change = (r - p) / p if p > 0 else 0
            if abs(change) > 0.20:  # >20% shift
                drift[event] = {
                    'recent_pct': round(r * 100, 1),
                    'prev_pct': round(p * 100, 1),
                    'change_pct': round(change * 100, 1),
                }

        if drift:
            logger.warning('weight_drift_detected', extra={
                'drifted_events': list(drift.keys()),
                'details': drift,
            })

        return {
            'status': 'drift_detected' if drift else 'stable',
            'drifted_events': drift,
        }
