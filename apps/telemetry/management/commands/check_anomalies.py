"""
Run anomaly checks once. Useful for cron fallback or one-off dev runs.

Usage:
    python manage.py check_anomalies
"""
from django.core.management.base import BaseCommand

from apps.telemetry.anomaly import run_all


class Command(BaseCommand):
    help = 'Run all telemetry anomaly checks once. Emits ops.alert outbox events on breach.'

    def handle(self, *args, **options):
        run_all()
        self.stdout.write(self.style.SUCCESS('Anomaly checks complete.'))
