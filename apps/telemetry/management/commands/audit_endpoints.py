"""
Probe hot endpoints with the Django test client + count DB queries.

Run after seeding fixtures (or against a non-trivial dev DB) to see
which routes are at risk of N+1.

Usage:
    python manage.py audit_endpoints
    python manage.py audit_endpoints --threshold=10
"""
import time
from contextlib import contextmanager

from django.core.management.base import BaseCommand
from django.db import connection, reset_queries, transaction
from django.test import Client
from django.conf import settings

# Endpoints to probe. Tuples of (method, path, body, label).
ENDPOINTS = [
    ('GET',  '/api/v1/products/?limit=20',                                'Search list (uncollapsed)'),
    ('GET',  '/api/v1/products/?limit=20&collapse=group',                 'Search list (collapsed SPU)'),
    ('GET',  '/api/v1/products/?search=phone&limit=20',                   'Search with query'),
    ('GET',  '/api/v1/products/facets/',                                  'Facets aggregation'),
    ('GET',  '/api/v1/recommendations/recently-viewed/',                  'Recently viewed (auth)'),
    ('GET',  '/api/v1/orders/my/?limit=10',                               'My orders list (auth)'),
    ('GET',  '/api/v1/cart/',                                             'Cart (auth)'),
]


@contextmanager
def query_counter():
    # Force DEBUG so connection.queries fills up regardless of project setting.
    prev_debug = settings.DEBUG
    settings.DEBUG = True
    reset_queries()
    t0 = time.monotonic()
    try:
        yield
    finally:
        settings.DEBUG = prev_debug


class Command(BaseCommand):
    help = 'Audit DB query counts on hot endpoints.'

    def add_arguments(self, parser):
        parser.add_argument('--threshold', type=int, default=10,
                            help='Warn-style highlight when count >= threshold.')

    def handle(self, *args, **options):
        threshold = options['threshold']

        # Need an authed user for /my and /cart endpoints
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.filter(is_active=True).first()
        if not user:
            user = User.objects.create_user(email='audit@example.com', password='x')

        client = Client()
        client.force_login(user)

        self.stdout.write(self.style.HTTP_INFO(
            'Endpoint                                                          Status   Queries  Time(ms)'
        ))
        self.stdout.write('-' * 100)

        for method, path, label in ENDPOINTS:
            with query_counter():
                t0 = time.monotonic()
                try:
                    if method == 'GET':
                        resp = client.get(path)
                    else:
                        resp = client.generic(method, path)
                    status = resp.status_code
                except Exception as e:
                    status = 'ERR'
                    self.stderr.write(f'  {label}: {e}')
                    continue
                elapsed_ms = (time.monotonic() - t0) * 1000
                count = len(connection.queries)

            badge = self.style.ERROR('!!!') if count >= threshold else self.style.SUCCESS('   ')
            line = f'{badge} {label:55} {status:6}  {count:6}    {elapsed_ms:7.1f}'
            self.stdout.write(line)

        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO(
            f'Threshold = {threshold} queries. Highlight (!!!) means audit this route.'
        ))
