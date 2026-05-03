"""
Management command to run feed weight optimization.
Usage: python manage.py optimize_weights --days=30
"""
from django.core.management.base import BaseCommand
from apps.ai_engine.weight_optimizer import WeightOptimizer, ABTestManager


class Command(BaseCommand):
    help = 'Analyze feed interaction data and suggest optimal scoring weights'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30,
            help='Days of data to analyze (default: 30)')
        parser.add_argument('--ab-results', action='store_true',
            help='Show A/B test results instead of weight optimization')

    def handle(self, *args, **options):
        if options['ab_results']:
            self.stdout.write('\n=== A/B Test Results ===\n')
            results = ABTestManager.get_results(days=options['days'])
            for group_id, data in results.items():
                if isinstance(group_id, int):
                    self.stdout.write(
                        f'Group {group_id} ({data["variant"]}): '
                        f'{data["purchasers"]}/{data["total_users"]} purchasers '
                        f'= {data["conversion_rate"]}% conversion'
                    )
            if 'winner' in results:
                self.stdout.write(f'\nWinner: {results["winner"]} (+{results["lift_pp"]}pp)')
        else:
            WeightOptimizer.run(days=options['days'])
