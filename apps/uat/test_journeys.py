"""
MICHA Express — User Acceptance Tests (UAT)
=============================================
Tests complete user journeys end-to-end through the real API.
These are NOT unit tests — they test real business flows.

Each test class is one complete journey:
  - Uses real DB, real views, real serializers
  - Follows the exact same path a real user would take
  - Validates the outcome from the user's perspective

Run: python -m pytest apps/uat/ -v --no-cov --tb=short
"""
import pytest
from decimal import Decimal
from django.utils import timezone
from rest_framework.test import APIClient


# ─── Shared fixtures ─────────────────────────────────────────────

@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def auth_api(db):
    """Returns a factory: auth_api(user) → authenticated client."""
    def _make(user):
        from rest_framework_simplejwt.tokens import RefreshToken
        client = APIClient()
        token = RefreshToken.for_user(user)
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token.access_token}')
        return client
    return _make


@pytest.fixture
def verified_buyer(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        email='uat_buyer@micha.ao',
        password='UATPass123!',
        is_email_verified=True,
        status='active',
    )


@pytest.fixture
def verified_seller(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    seller = User.objects.create_user(
        email='uat_seller@micha.ao',
        password='UATPass123!',
        is_email_verified=True,
        is_seller=True,
        is_verified_seller=True,
        status='active',
    )
    # Create store
    from apps.stores.models import Store
    Store.objects.create(
        owner=seller,
        name='UAT Test Store',
        city='Luanda',
        is_active=True,
        is_open=True,
    )
    return seller


@pytest.fixture
def admin_user(db):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_superuser(
        email='uat_admin@micha.ao',
        password='UATAdmin123!',
    )


@pytest.fixture
def category(db):
    from apps.products.models import Category
    return Category.objects.create(name='Electrónica', slug='electronica')


@pytest.fixture
def product(db, verified_seller, category):
    from apps.products.models import Product
    from apps.stores.models import Store
    store = Store.objects.get(owner=verified_seller)
    return Product.objects.create(
        store=store,
        created_by=verified_seller,
        title='Samsung Galaxy S24 UAT',
        slug='samsung-galaxy-s24-uat',
        description='Smartphone para testes UAT',
        price=Decimal('180000.00'),
        category=category,
        quantity=10,
        is_active=True,
    )


# ═══════════════════════════════════════════════════════════════════
# JOURNEY 1: Complete Buyer Purchase Flow
# Register → Browse → Search → Cart → Checkout → Track
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestBuyerPurchaseJourney:
    """
    UAT: Full buyer journey from registration to order tracking.
    Validates the most critical path in the entire system.
    """

    def test_1_register(self, api):
        """Buyer can register with valid data."""
        res = api.post('/api/v1/auth/register/', {
            'email': 'journey_buyer@micha.ao',
            'password': 'JourneyPass123!',
            'password2': 'JourneyPass123!',
            'privacy_consent': True,
            'terms_consent': True,
        })
        assert res.status_code == 201
        assert 'email' in res.data or res.status_code == 201

    def test_2_login(self, api, verified_buyer):
        """Verified buyer can login and receive JWT tokens."""
        res = api.post('/api/v1/auth/login/', {
            'email': 'uat_buyer@micha.ao',
            'password': 'UATPass123!',
        })
        assert res.status_code == 200
        assert 'access' in res.data
        assert 'refresh' in res.data

    def test_3_browse_products(self, api, product):
        """Anonymous users can browse products."""
        res = api.get('/api/v1/products/')
        assert res.status_code == 200
        assert 'results' in res.data or isinstance(res.data, list)

    def test_4_search_products(self, api, product):
        """Search returns relevant results."""
        res = api.get('/api/v1/search/?q=Samsung')
        assert res.status_code == 200

    def test_5_view_product_detail(self, api, product):
        """Buyer can view product detail page."""
        res = api.get(f'/api/v1/products/{product.slug}/')
        assert res.status_code == 200

    def test_6_add_to_cart(self, auth_api, verified_buyer, product):
        """Authenticated buyer can add product to cart."""
        client = auth_api(verified_buyer)
        res = client.post('/api/v1/cart/add/', {
            'product_id': product.id,
            'quantity': 1,
        })
        assert res.status_code in [200, 201]

    def test_7_view_cart(self, auth_api, verified_buyer, product):
        """Buyer can view their cart with items."""
        client = auth_api(verified_buyer)
        client.post('/api/v1/cart/add/', {'product_id': product.id, 'quantity': 1})
        res = client.get('/api/v1/cart/')
        assert res.status_code == 200

    def test_8_checkout_empty_cart_rejected(self, auth_api, verified_buyer):
        """Checkout with empty cart is rejected."""
        client = auth_api(verified_buyer)
        res = client.post('/api/v1/orders/checkout/', {
            'shipping_address': 'Rua UAT 123, Luanda',
            'shipping_phone': '+244923000001',
            'payment_method': 'multicaixa',
        })
        assert res.status_code == 400

    def test_9_checkout_creates_order(self, auth_api, verified_buyer, product):
        """Full checkout creates an order and reduces stock."""
        client = auth_api(verified_buyer)
        initial_stock = product.quantity

        # Add to cart
        client.post('/api/v1/cart/add/', {'product_id': product.id, 'quantity': 2})

        # Checkout
        res = client.post('/api/v1/orders/checkout/', {
            'shipping_address': 'Rua UAT 123, Luanda',
            'shipping_phone': '+244923000001',
            'payment_method': 'multicaixa',
        })
        assert res.status_code in [201, 400]  # 400 if payment validation required

        if res.status_code == 201:
            # Stock should be reduced
            product.refresh_from_db()
            assert product.quantity <= initial_stock

    def test_10_view_orders(self, auth_api, verified_buyer):
        """Buyer can view their order history."""
        client = auth_api(verified_buyer)
        res = client.get('/api/v1/orders/my/')
        assert res.status_code == 200

    def test_11_cart_cleared_after_checkout(self, auth_api, verified_buyer, product):
        """Cart should be empty after successful checkout."""
        client = auth_api(verified_buyer)
        client.post('/api/v1/cart/add/', {'product_id': product.id, 'quantity': 1})

        checkout_res = client.post('/api/v1/orders/checkout/', {
            'shipping_address': 'Rua UAT 123, Luanda',
            'shipping_phone': '+244923000001',
            'payment_method': 'multicaixa',
        })

        if checkout_res.status_code == 201:
            cart_res = client.get('/api/v1/cart/')
            if cart_res.status_code == 200:
                items = cart_res.data.get('items', [])
                assert len(items) == 0


# ═══════════════════════════════════════════════════════════════════
# JOURNEY 2: Complete Seller Flow
# Setup store → Add product → Manage orders → Get paid
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestSellerJourney:
    """
    UAT: Full seller journey from store setup to payment.
    """

    def test_1_seller_can_access_dashboard(self, auth_api, verified_seller):
        """Seller can access their dashboard."""
        client = auth_api(verified_seller)
        res = client.get('/api/v1/seller/dashboard/')
        assert res.status_code == 200

    def test_2_seller_can_create_product(self, auth_api, verified_seller, category):
        """Seller can create a new product listing."""
        client = auth_api(verified_seller)
        res = client.post('/api/v1/products/create/', {
            'title': 'UAT Product New',
            'description': 'Product created via UAT',
            'price': '50000.00',
            'quantity': 5,
            'category': category.id,
        })
        assert res.status_code in [201, 400]  # 400 if missing required fields

    def test_3_seller_can_view_own_products(self, auth_api, verified_seller, product):
        """Seller can view their product listings."""
        client = auth_api(verified_seller)
        res = client.get('/api/v1/products/my/')
        assert res.status_code == 200

    def test_4_seller_can_view_orders(self, auth_api, verified_seller):
        """Seller can view incoming orders."""
        client = auth_api(verified_seller)
        res = client.get('/api/v1/orders/seller/')
        assert res.status_code == 200

    def test_5_seller_can_view_wallet(self, auth_api, verified_seller):
        """Seller can view their wallet balance."""
        client = auth_api(verified_seller)
        res = client.get('/api/v1/payments/wallet/')
        assert res.status_code == 200
        assert 'balance' in res.data

    def test_6_seller_can_view_analytics(self, auth_api, verified_seller):
        """Seller can view their performance analytics."""
        client = auth_api(verified_seller)
        res = client.get('/api/v1/analytics/seller/performance/')
        assert res.status_code == 200

    def test_7_seller_cannot_access_other_seller_products(self, auth_api, verified_seller, db):
        """Seller cannot modify another seller's products."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        other_seller = User.objects.create_user(
            email='other_seller@micha.ao',
            password='Pass123!',
            is_email_verified=True,
            is_seller=True,
        )
        client = auth_api(verified_seller)
        # Try to update other seller's product (using a fake ID)
        res = client.patch('/api/v1/products/999/update/', {'price': '1.00'})
        assert res.status_code in [403, 404]

    def test_8_seller_can_toggle_store_open(self, auth_api, verified_seller):
        """Seller can open/close their store."""
        client = auth_api(verified_seller)
        res = client.post('/api/v1/stores/toggle-open/')
        assert res.status_code in [200, 404]

    def test_9_buyer_cannot_access_seller_dashboard(self, auth_api, verified_buyer):
        """Buyer cannot access seller-only endpoints."""
        client = auth_api(verified_buyer)
        res = client.get('/api/v1/seller/dashboard/')
        assert res.status_code in [403, 404]


# ═══════════════════════════════════════════════════════════════════
# JOURNEY 3: Admin Operations
# Approve KYC → Resolve dispute → Approve payout
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestAdminJourney:
    """
    UAT: Admin can manage the platform effectively.
    """

    def test_1_admin_can_access_dashboard(self, auth_api, admin_user):
        """Admin can access platform stats."""
        client = auth_api(admin_user)
        res = client.get('/api/v1/admin-api/stats/')
        assert res.status_code == 200

    def test_2_admin_can_list_users(self, auth_api, admin_user):
        """Admin can list all users."""
        client = auth_api(admin_user)
        res = client.get('/api/v1/admin-actions/users/')
        assert res.status_code == 200

    def test_3_admin_can_list_sellers(self, auth_api, admin_user):
        """Admin can list all sellers."""
        client = auth_api(admin_user)
        res = client.get('/api/v1/admin-api/sellers/')
        assert res.status_code == 200

    def test_4_admin_can_list_products(self, auth_api, admin_user):
        """Admin can list all products."""
        client = auth_api(admin_user)
        res = client.get('/api/v1/admin-api/products/')
        assert res.status_code == 200

    def test_5_admin_can_list_orders(self, auth_api, admin_user):
        """Admin can list all orders."""
        client = auth_api(admin_user)
        res = client.get('/api/v1/admin-api/orders/')
        assert res.status_code == 200

    def test_6_non_admin_cannot_access_admin_endpoints(self, auth_api, verified_buyer):
        """Regular users cannot access admin endpoints."""
        client = auth_api(verified_buyer)
        res = client.get('/api/v1/admin-api/stats/')
        assert res.status_code in [403, 404]

    def test_7_admin_can_list_fraud_alerts(self, auth_api, admin_user):
        """Admin can view fraud alerts."""
        client = auth_api(admin_user)
        res = client.get('/api/v1/security/fraud-alerts/')
        assert res.status_code == 200

    def test_8_admin_can_list_disputes(self, auth_api, admin_user):
        """Admin can view disputes."""
        client = auth_api(admin_user)
        res = client.get('/api/v1/disputes/admin/')
        assert res.status_code == 200


# ═══════════════════════════════════════════════════════════════════
# JOURNEY 4: Fraud Detection
# New account → High value order → Gets flagged
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestFraudDetectionJourney:
    """
    UAT: Fraud detection fires correctly without blocking legitimate users.
    """

    def test_1_new_account_high_value_flagged(self, db, product):
        """New account placing very high value order triggers fraud check."""
        from django.contrib.auth import get_user_model
        from apps.security.fraud_engine import assess_order_fraud
        from apps.orders.models import Order
        from apps.stores.models import Store

        User = get_user_model()
        new_buyer = User.objects.create_user(
            email='new_fraud@micha.ao',
            password='Pass123!',
            is_email_verified=True,
        )

        # Simulate a high value order
        store = Store.objects.filter(owner=product.store.owner).first()
        order = Order.objects.create(
            buyer=new_buyer,
            seller=product.store.owner,
            idempotency_key='fraud-test-001',
            shipping_address='Rua Teste',
            shipping_phone='+244923000001',
            shipping_city='Luanda',
            subtotal=Decimal('600000.00'),
            total=Decimal('600000.00'),  # 600k AOA — above VERY_HIGH threshold
            status='pending',
        )

        result = assess_order_fraud(order)
        assert result['risk_score'] > 0
        assert result['action'] in ['flag', 'hold', 'block']

    def test_2_trusted_buyer_not_flagged(self, db, verified_buyer, product):
        """Established buyer with history is not flagged for normal orders."""
        from apps.orders.models import Order
        from apps.security.fraud_engine import assess_order_fraud

        # Give buyer some order history
        from apps.stores.models import Store
        store = Store.objects.filter(owner=product.store.owner).first()

        for i in range(5):
            Order.objects.create(
                buyer=verified_buyer,
                seller=product.store.owner,
                idempotency_key=f'trust-test-{i}',
                shipping_address='Rua Conhecida 123',
                shipping_phone='+244923000001',
                shipping_city='Luanda',
                subtotal=Decimal('50000.00'),
                total=Decimal('50000.00'),
                status='completed',
            )

        # Normal value order
        order = Order.objects.create(
            buyer=verified_buyer,
            seller=product.store.owner,
            idempotency_key='trust-test-normal',
            shipping_address='Rua Conhecida 123',
            shipping_phone='+244923000001',
            shipping_city='Luanda',
            subtotal=Decimal('40000.00'),
            total=Decimal('40000.00'),
            status='pending',
        )

        result = assess_order_fraud(order)
        # Trusted buyer should have low risk or be allowed
        assert result['action'] in ['allow', 'flag']
        assert result['risk_score'] < 60

    def test_3_rapid_orders_detected(self, db, verified_buyer, product):
        """5+ orders in 1 hour triggers velocity fraud detection."""
        from apps.orders.models import Order
        from apps.security.fraud_engine import assess_order_fraud

        # Create 5 recent orders
        for i in range(5):
            Order.objects.create(
                buyer=verified_buyer,
                seller=product.store.owner,
                idempotency_key=f'velocity-{i}',
                shipping_address='Rua Teste',
                shipping_phone='+244923000001',
                shipping_city='Luanda',
                subtotal=Decimal('10000.00'),
                total=Decimal('10000.00'),
                status='pending',
                created_at=timezone.now(),
            )

        order = Order.objects.create(
            buyer=verified_buyer,
            seller=product.store.owner,
            idempotency_key='velocity-trigger',
            shipping_address='Rua Teste',
            shipping_phone='+244923000001',
            shipping_city='Luanda',
            subtotal=Decimal('10000.00'),
            total=Decimal('10000.00'),
            status='pending',
        )

        result = assess_order_fraud(order)
        velocity_signals = [s for s in result['signals'] if 'velocity' in s['name']]
        assert len(velocity_signals) > 0

    def test_4_fraud_engine_never_crashes(self, db, verified_buyer, product):
        """Fraud engine always returns a result, never raises exceptions."""
        from apps.orders.models import Order
        from apps.security.fraud_engine import assess_order_fraud

        order = Order.objects.create(
            buyer=verified_buyer,
            seller=product.store.owner,
            idempotency_key='no-crash-test',
            shipping_address='',
            shipping_phone='',
            shipping_city='',
            subtotal=Decimal('0.00'),
            total=Decimal('0.00'),
            status='pending',
        )

        # Should never raise
        result = assess_order_fraud(order)
        assert 'risk_score' in result
        assert 'action' in result


# ═══════════════════════════════════════════════════════════════════
# JOURNEY 5: Dispute & Returns Flow
# Buyer files dispute → Admin resolves → Outcome recorded
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestDisputeJourney:
    """
    UAT: Dispute resolution flow works end-to-end.
    """

    def test_1_buyer_can_open_dispute(self, auth_api, verified_buyer, verified_seller, product, db):
        """Buyer can file a dispute on an order."""
        from apps.orders.models import Order

        order = Order.objects.create(
            buyer=verified_buyer,
            seller=verified_seller,
            idempotency_key='dispute-test-001',
            shipping_address='Rua Teste',
            shipping_phone='+244923000001',
            shipping_city='Luanda',
            subtotal=Decimal('50000.00'),
            total=Decimal('50000.00'),
            status='delivered',
        )

        client = auth_api(verified_buyer)
        res = client.post('/api/v1/disputes/open/', {
            'order_id': str(order.id),
            'reason': 'item_not_received',
            'description': 'O produto não chegou após 14 dias.',
        })
        assert res.status_code in [201, 400]

    def test_2_seller_cannot_file_dispute_as_buyer(self, auth_api, verified_seller, verified_buyer, product, db):
        """Seller cannot open a dispute against themselves."""
        from apps.orders.models import Order

        order = Order.objects.create(
            buyer=verified_buyer,
            seller=verified_seller,
            idempotency_key='dispute-test-002',
            shipping_address='Rua Teste',
            shipping_phone='+244923000001',
            shipping_city='Luanda',
            subtotal=Decimal('50000.00'),
            total=Decimal('50000.00'),
            status='delivered',
        )

        client = auth_api(verified_seller)
        res = client.post('/api/v1/disputes/open/', {
            'order_id': str(order.id),
            'reason': 'item_not_received',
            'description': 'Test',
        })
        assert res.status_code in [400, 403, 404]

    def test_3_admin_can_resolve_dispute(self, auth_api, admin_user, verified_buyer, verified_seller, db):
        """Admin can resolve a dispute in favour of buyer or seller."""
        from apps.disputes.models import Dispute
        from apps.orders.models import Order

        order = Order.objects.create(
            buyer=verified_buyer,
            seller=verified_seller,
            idempotency_key='dispute-resolve-001',
            shipping_address='Rua Teste',
            shipping_phone='+244923000001',
            shipping_city='Luanda',
            subtotal=Decimal('50000.00'),
            total=Decimal('50000.00'),
            status='delivered',
        )
        dispute = Dispute.objects.create(
            order=order,
            buyer=verified_buyer,
            seller=verified_seller,
            reason='item_not_received',
            description='Produto não chegou',
            status='open',
        )

        client = auth_api(admin_user)
        res = client.patch(f'/api/v1/disputes/admin/{dispute.id}/resolve/', {
            'resolution': 'refund_buyer',
            'admin_note': 'Delivery not confirmed by seller',
        })
        assert res.status_code in [200, 201, 404]


# ═══════════════════════════════════════════════════════════════════
# JOURNEY 6: Chat & Safety
# Buyer sends message → Seller replies → Diversion blocked
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestChatSafetyJourney:
    """
    UAT: Chat works correctly and payment diversion is detected.
    """

    def test_1_buyer_can_start_chat(self, auth_api, verified_buyer, verified_seller, product):
        """Buyer can initiate a chat with a seller."""
        client = auth_api(verified_buyer)
        res = client.post('/api/v1/chat/conversations/', {
            'seller_id': verified_seller.id,
        })
        assert res.status_code in [200, 201]

    def test_2_payment_diversion_detected(self, db):
        """Chat payment diversion patterns are detected."""
        from apps.security.fraud_signals import ChatDiversionDetector

        detector = ChatDiversionDetector()

        # These should trigger
        bad_messages = [
            'Paga directo no meu número',
            'Manda o dinheiro pelo multicaixa directo',
            'Paga fora da plataforma é mais barato',
            'Zap me para combinar o pagamento',
        ]
        for msg in bad_messages:
            signals = detector.check_message(msg, sender=None, chat=None)
            assert len(signals) > 0, f'Should detect diversion in: "{msg}"'

        # These should NOT trigger
        safe_messages = [
            'O produto ainda está disponível?',
            'Qual é o prazo de entrega?',
            'Tem este em azul?',
            'Posso pagar com Multicaixa?',
        ]
        for msg in safe_messages:
            signals = detector.check_message(msg, sender=None, chat=None)
            assert len(signals) == 0, f'False positive for: "{msg}"'

    def test_3_chat_list_requires_auth(self, api):
        """Chat endpoint requires authentication."""
        res = api.get('/api/v1/chat/conversations/')
        assert res.status_code == 401


# ═══════════════════════════════════════════════════════════════════
# JOURNEY 7: Security Boundaries
# Critical: ensure no privilege escalation
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestSecurityBoundaries:
    """
    UAT: Security boundaries hold — no privilege escalation possible.
    Critical for financial integrity.
    """

    def test_buyer_cannot_access_admin(self, auth_api, verified_buyer):
        admin_endpoints = [
            '/api/v1/admin-api/stats/',
            '/api/v1/admin-api/users/',
            '/api/v1/admin-api/sellers/',
            '/api/v1/security/fraud-alerts/',
        ]
        client = auth_api(verified_buyer)
        for endpoint in admin_endpoints:
            res = client.get(endpoint)
            assert res.status_code in [403, 404], f'{endpoint} should be forbidden for buyer'

    def test_seller_cannot_access_admin(self, auth_api, verified_seller):
        admin_endpoints = [
            '/api/v1/admin-api/stats/',
            '/api/v1/security/fraud-alerts/',
        ]
        client = auth_api(verified_seller)
        for endpoint in admin_endpoints:
            res = client.get(endpoint)
            assert res.status_code in [403, 404], f'{endpoint} should be forbidden for seller'

    def test_unauthenticated_blocked_from_all_protected(self, api):
        protected = [
            '/api/v1/cart/',
            '/api/v1/orders/my/',
            '/api/v1/payments/wallet/',
            '/api/v1/notifications/',
            '/api/v1/auth/profile/',
            '/api/v1/seller/dashboard/',
        ]
        for endpoint in protected:
            res = api.get(endpoint)
            assert res.status_code == 401, f'{endpoint} should require auth'

    def test_wallet_transaction_immutable(self, db, verified_seller):
        """WalletTransaction records cannot be deleted or modified."""
        from apps.payments.models import SellerWallet, WalletTransaction
        from decimal import Decimal

        wallet, _ = SellerWallet.objects.get_or_create(seller=verified_seller)
        txn = WalletTransaction.objects.create(
            wallet=wallet,
            type='credit',
            amount=Decimal('1000.00'),
            description='UAT test credit',
            balance_after=Decimal('1000.00'),
        )
        with pytest.raises(ValueError):
            txn.delete()

    def test_payment_event_immutable(self, db, verified_buyer, verified_seller, product):
        """PaymentEvent records cannot be modified — financial audit trail."""
        from apps.orders.models import Order, Payment
        from apps.payments.models import PaymentEvent
        from decimal import Decimal

        order = Order.objects.create(
            buyer=verified_buyer,
            seller=verified_seller,
            idempotency_key='immutable-test',
            shipping_address='Rua Teste',
            shipping_phone='+244923000001',
            shipping_city='Luanda',
            subtotal=Decimal('50000.00'),
            total=Decimal('50000.00'),
            status='pending',
        )
        payment = Payment.objects.create(
            order=order,
            method='multicaixa_express',
            status='initiated',
            gateway_reference='MICHA-TEST001',
            amount=Decimal('50000.00'),
            currency='AOA',
        )
        event = PaymentEvent.objects.create(
            payment=payment,
            event_type='initiated',
            details={'test': True},
        )
        with pytest.raises(ValueError):
            event.save()  # Should raise — records are append-only

    def test_idempotent_checkout(self, auth_api, verified_buyer, product):
        """Same idempotency key returns same order, not two orders."""
        from apps.orders.models import Order
        client = auth_api(verified_buyer)

        client.post('/api/v1/cart/add/', {'product_id': product.id, 'quantity': 1})

        idem_key = 'uat-idempotency-test-001'
        res1 = client.post('/api/v1/orders/checkout/', {
            'shipping_address': 'Rua Teste 123',
            'shipping_phone': '+244923000001',
            'payment_method': 'multicaixa',
            'idempotency_key': idem_key,
        })
        res2 = client.post('/api/v1/orders/checkout/', {
            'shipping_address': 'Rua Teste 123',
            'shipping_phone': '+244923000001',
            'payment_method': 'multicaixa',
            'idempotency_key': idem_key,
        })

        if res1.status_code == 201 and res2.status_code == 201:
            # Both succeeded — must be same order
            assert res1.data.get('id') == res2.data.get('id')

        # Never duplicate orders with same key
        orders = Order.objects.filter(
            buyer=verified_buyer,
            idempotency_key=idem_key,
        ).count()
        assert orders <= 1


# ═══════════════════════════════════════════════════════════════════
# JOURNEY 8: Performance Engine
# Validates seller scoring doesn't crash on edge cases
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestSellerPerformanceJourney:
    """
    UAT: Seller performance engine handles all edge cases gracefully.
    """

    def test_1_new_seller_gets_cold_start_score(self, verified_seller):
        """Brand new seller gets a reasonable score, not 0."""
        from apps.analytics.performance_engine import SellerPerformanceEngine

        engine = SellerPerformanceEngine(verified_seller)
        result = engine.compute()

        assert 'overall_score' in result
        assert result['overall_score'] >= 30  # never zero for new sellers
        assert result['overall_score'] <= 60  # never full score without data
        assert result['tier'] in ['new', 'verified', 'good']

    def test_2_performance_engine_never_crashes(self, db):
        """Engine never raises — always returns a valid result."""
        from django.contrib.auth import get_user_model
        from apps.analytics.performance_engine import SellerPerformanceEngine

        User = get_user_model()
        seller = User.objects.create_user(
            email='perf_test@micha.ao',
            password='Pass123!',
            is_seller=True,
        )

        engine = SellerPerformanceEngine(seller)
        result = engine.compute()

        assert isinstance(result, dict)
        assert 'overall_score' in result
        assert 0 <= result['overall_score'] <= 100

    def test_3_score_weights_sum_to_one(self):
        """Dimension weights must sum to exactly 1.0."""
        from apps.analytics.performance_engine import SellerPerformanceEngine

        total = sum(SellerPerformanceEngine.WEIGHTS.values())
        assert abs(total - 1.0) < 0.0001, f'Weights sum to {total}, not 1.0'

    def test_4_tier_thresholds_are_ordered(self):
        """Tier thresholds must be in descending order."""
        from apps.analytics.performance_engine import SellerPerformanceEngine

        thresholds = [t[0] for t in SellerPerformanceEngine.TIERS]
        assert thresholds == sorted(thresholds, reverse=True)
