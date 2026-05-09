"""
Manual / cron-driven outbox dispatcher.

Usage:
    python manage.py dispatch_outbox                # one drain pass
    python manage.py dispatch_outbox --loop         # poll forever (dev)
    python manage.py dispatch_outbox --batch 200    # custom batch size
"""
import time
from django.core.management.base import BaseCommand

from apps.outbox.dispatcher import drain


class Command(BaseCommand):
    help = 'Drain pending outbox events.'

    def add_arguments(self, parser):
        parser.add_argument('--batch', type=int, default=100)
        parser.add_argument('--loop', action='store_true',
                            help='Poll forever (dev / fallback if no celery beat).')
        parser.add_argument('--interval', type=float, default=5.0,
                            help='Poll interval when --loop (seconds).')

    def handle(self, *args, **options):
        batch = options['batch']
        if options['loop']:
            self.stdout.write(f'Outbox loop running (batch={batch}, interval={options["interval"]}s)…')
            while True:
                n = drain(batch_size=batch)
                if n:
                    self.stdout.write(f'  dispatched {n}')
                time.sleep(options['interval'])
        else:
            n = drain(batch_size=batch)
            self.stdout.write(self.style.SUCCESS(f'Dispatched {n} event(s).'))
