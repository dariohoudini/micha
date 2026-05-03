"""
MICHA Express — Shared Test Fixtures
Available to all test files via pytest conftest
"""
import pytest
from django.contrib.auth import get_user_model
from decimal import Decimal

User = get_user_model()


# ─── User Factories ───────────────────────────────────────────────
@pytest.fixture
def buyer(db):
    return User.objects.create_user(
        email='buyer@test.com',
        password='TestPass123!',
        is_email_verified=True,
        status='active',
    )

@pytest.fixture
def seller(db):
    user = User.objects.create_user(
        email='seller@test.com',
        password='TestPass123!',
        is_email_verified=True,
        is_seller=True,
        is_verified_seller=True,
        status='active',
    )
    return user

@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        email='admin@test.com',
        password='AdminPass123!',
    )

@pytest.fixture
def buyer_client(buyer):
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken
    client = APIClient()
    refresh = RefreshToken.for_user(buyer)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return client

@pytest.fixture
def seller_client(seller):
    from rest_framework.test import APIClient
    from rest_framework_simplejwt.tokens import RefreshToken
    client = APIClient()
    refresh = RefreshToken.for_user(seller)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}')
    return client

@pytest.fixture
def api_client():
    from rest_framework.test import APIClient
    return APIClient()


# ─── Product Factories ────────────────────────────────────────────
@pytest.fixture
def category(db):
    from apps.products.models import Category
    return Category.objects.create(
        name='Electrónica',
        slug='electronica',
    )

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

@pytest.fixture
def cart(db, buyer):
    from apps.cart.models import Cart
    cart, _ = Cart.objects.get_or_create(user=buyer)
    return cart
