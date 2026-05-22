import django
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import pytest


# Note: the django_db_setup fixture used to be a no-op (``pass``), which
# meant pytest-django skipped running migrations on the test DB. That
# made every test fail with "no such table" on SQLite. We let
# pytest-django's default fixture do the setup (i.e., run migrations
# into the test DB once per session) by NOT overriding it.
#
# If a CI environment needs to skip migrations (e.g., uses pg_dump of
# the prod schema), set DJANGO_TEST_SKIP_MIGRATIONS=1 in the env and
# the conftest in apps/conftest.py can override there.

@pytest.fixture
def buyer(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        email='buyer@test.com',
        password='TestPass123!',
        is_email_verified=True,
        status='active',
    )

@pytest.fixture
def seller(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        email='seller@test.com',
        password='TestPass123!',
        is_email_verified=True,
        is_seller=True,
        is_verified_seller=True,
        status='active',
    )

@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()

@pytest.fixture
def buyer_client(buyer):
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken
    client = APIClient()
    refresh = RefreshToken.for_user(buyer)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return client

@pytest.fixture
def seller_client(seller):
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken
    client = APIClient()
    refresh = RefreshToken.for_user(seller)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return client

@pytest.fixture
def category(db):
    from apps.products.models import Category
    return Category.objects.create(name='Electrónica', slug='electronica')

@pytest.fixture
def store(db, seller):
    from apps.stores.models import Store
    return Store.objects.create(
        owner=seller,
        name='Loja Test',
        city='Luanda',
        is_active=True,
    )

@pytest.fixture
def product(db, store, category):
    from apps.products.models import Product
    from decimal import Decimal
    return Product.objects.create(
        store=store,
        title='Samsung Galaxy S24',
        slug='samsung-galaxy-s24',
        description='Smartphone topo de gama com câmara de 200MP',
        price=Decimal('180000.00'),
        compare_at_price=Decimal('200000.00'),
        category=category,
        quantity=10,
        is_active=True,
    )
