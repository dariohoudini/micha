"""
Management command to run seller performance scoring and inspect results.
Usage:
  python manage.py score_sellers                    # score all sellers
  python manage.py score_sellers --seller=user@id   # score one seller
  python manage.py score_sellers --inspect          # show current scores
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Run seller performance scoring engine'

    def add_arguments(self, parser):
        parser.add_argument('--seller', type=str, help='Seller email or ID to score')
        parser.add_argument('--inspect', action='store_true', help='Show current score distribution')
        parser.add_argument('--verbose', action='store_true', help='Show full dimension breakdown')

    def handle(self, *args, **options):
        if options['inspect']:
            self._inspect()
            return

        if options['seller']:
            self._score_one(options['seller'], options['verbose'])
        else:
            self._score_all()

    def _score_all(self):
        from apps.analytics.performance_engine import update_all_seller_scores
        self.stdout.write('Scoring all sellers...')
        result = update_all_seller_scores()
        self.stdout.write(self.style.SUCCESS(
            f'\n✅ Done. Updated: {result["updated"]}, Errors: {result["errors"]}'
        ))
        self.stdout.write('\nTier distribution:')
        for tier, count in sorted(result['tiers'].items(), key=lambda x: x[1], reverse=True):
            self.stdout.write(f'  {tier}: {count} sellers')

    def _score_one(self, seller_id: str, verbose: bool):
        from django.contrib.auth import get_user_model
        from apps.analytics.performance_engine import SellerPerformanceEngine

        User = get_user_model()
        try:
            if '@' in seller_id:
                seller = User.objects.get(email=seller_id)
            else:
                seller = User.objects.get(id=seller_id)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f'Seller not found: {seller_id}'))
            return

        self.stdout.write(f'Scoring seller: {seller.email}')
        engine = SellerPerformanceEngine(seller)
        result = engine.compute()

        self.stdout.write(f'\n{"="*50}')
        self.stdout.write(f'Overall Score: {result["overall_score"]}/100')
        self.stdout.write(f'Tier:          {result["tier_label"]}')
        self.stdout.write(f'Confidence:    {result["meta"]["confidence"]}')
        self.stdout.write(f'Orders (90d):  {result["meta"].get("orders_90d", "N/A")}')

        if verbose and result.get('dimensions'):
            self.stdout.write(f'\nDimension Breakdown:')
            self.stdout.write(f'{"─"*50}')
            weights = {
                'delivery_speed': 25,
                'completion_rate': 25,
                'response_rate': 20,
                'review_quality': 20,
                'dispute_rate': 10,
            }
            for dim, data in result['dimensions'].items():
                w = weights.get(dim, 0)
                bar = '█' * int(data['score'] / 10) + '░' * (10 - int(data['score'] / 10))
                self.stdout.write(
                    f'{dim:<20} {bar} {data["score"]:5.1f}/100  ({w}% weight)  {data["label"]}'
                )
                if data.get('raw'):
                    self.stdout.write(f'  Raw: {data["raw"]}')

    def _inspect(self):
        from apps.analytics.models import SellerPerformance
        from django.db.models import Count, Avg

        perfs = SellerPerformance.objects.all()
        total = perfs.count()

        if total == 0:
            self.stdout.write('No performance records yet. Run: python manage.py score_sellers')
            return

        self.stdout.write(f'\nSeller Performance Summary ({total} sellers)')
        self.stdout.write('='*50)

        tiers = perfs.values('tier').annotate(count=Count('id')).order_by('-count')
        for t in tiers:
            pct = t['count'] / total * 100
            bar = '█' * int(pct / 5)
            self.stdout.write(f'{t["tier"]:<12} {bar} {t["count"]} ({pct:.0f}%)')

        avgs = perfs.aggregate(
            avg_score=Avg('overall_score'),
            avg_response=Avg('response_rate'),
            avg_completion=Avg('completion_rate'),
            avg_delivery=Avg('on_time_delivery_rate'),
        )

        self.stdout.write(f'\nAverages:')
        self.stdout.write(f'  Overall score:    {float(avgs["avg_score"] or 0)*100:.1f}/100')
        self.stdout.write(f'  Completion rate:  {float(avgs["avg_completion"] or 0)*100:.1f}%')
        self.stdout.write(f'  Response rate:    {float(avgs["avg_response"] or 0)*100:.1f}%')
        self.stdout.write(f'  On-time delivery: {float(avgs["avg_delivery"] or 0)*100:.1f}%')
