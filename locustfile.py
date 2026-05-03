"""
MICHA Express — Load Test Suite
Run: locust -f locustfile.py --host=http://localhost:8000

Simulates real Angolan e-commerce traffic patterns:
- 70% buyers browsing and purchasing
- 20% sellers managing their stores
- 10% new user registrations

Target benchmarks:
- Homepage feed: < 200ms p95
- Product detail: < 150ms p95
- Search: < 300ms p95
- Checkout: < 500ms p95
- 500 concurrent users without degradation
"""
import random
import string
from locust import HttpUser, task, between, events
from locust.contrib.fasthttp import FastHttpUser


# ─── Test data ────────────────────────────────────────────────────
PRODUCT_SLUGS = ['samsung-galaxy-s24', 'iphone-15-pro', 'xiaomi-14']
SEARCH_QUERIES = ['samsung', 'nike', 'sofá', 'vestido', 'televisão', 'sapatos', 'perfume']
CATEGORIES = ['electronica', 'moda', 'casa', 'beleza', 'desporto']
PROVINCES = ['Luanda', 'Benguela', 'Huambo', 'Huíla', 'Cabinda']


def random_email():
    return f"test_{''.join(random.choices(string.ascii_lowercase, k=8))}@micha-test.ao"


def random_password():
    return "LoadTest1234!"


# ─── Buyer User ────────────────────────────────────────────────────
class BuyerUser(HttpUser):
    """
    Simulates a typical MICHA buyer.
    Browses feed, searches, views products, adds to cart, checks orders.
    """
    weight = 70  # 70% of traffic
    wait_time = between(1, 4)  # Think time between actions

    def on_start(self):
        """Login as a pre-created verified test user."""
        self.token = None
        self.product_ids = []
        user_num = random.randint(1, 50)
        self.email = f'loadtest_buyer_{user_num}@micha-test.ao'
        self.password = 'LoadTest1234!'
        res = self.client.post('/api/v1/auth/login/', json={
            'email': self.email,
            'password': self.password,
        }, name='/auth/login')
        if res.status_code == 200:
            self.token = res.json().get('access')
            self.client.headers.update({'Authorization': f'Bearer {self.token}'})

    def _auth_headers(self):
        if self.token:
            return {'Authorization': f'Bearer {self.token}'}
        return {}

    @task(20)
    def browse_home_feed(self):
        """Most common action — browsing the home feed."""
        province = random.choice(PROVINCES)
        self.client.get(
            f'/api/v1/ai/feed/?province={province}&limit=20',
            name='/ai/feed',
            headers=self._auth_headers()
        )

    @task(15)
    def search_products(self):
        """Search is the second most common action."""
        query = random.choice(SEARCH_QUERIES)
        self.client.get(
            f'/api/v1/search/?q={query}',
            name='/search'
        )

    @task(12)
    def browse_recommendations(self):
        """Personalised feed."""
        self.client.get(
            '/api/v1/recommendations/feed/',
            name='/recommendations/feed',
            headers=self._auth_headers()
        )

    @task(10)
    def view_product(self):
        """View a product detail page."""
        # Get product list first
        res = self.client.get('/api/v1/products/', name='/products/list')
        if res.status_code == 200:
            products = res.json().get('results', [])
            if products:
                product = random.choice(products[:10])
                slug = product.get('slug', '')
                if slug:
                    self.client.get(
                        f'/api/v1/products/{slug}/',
                        name='/products/detail'
                    )
                    # Track interaction
                    self.client.post(
                        '/api/v1/recommendations/track/',
                        json={'product_id': product.get('id'), 'interaction_type': 'view'},
                        name='/recommendations/track',
                        headers=self._auth_headers()
                    )

    @task(8)
    def search_with_suggestions(self):
        """Autocomplete search."""
        query = random.choice(['sam', 'nik', 'sof', 'ves'])
        self.client.get(
            f'/api/v1/search/suggestions/?q={query}',
            name='/search/suggestions'
        )

    @task(6)
    def view_categories(self):
        """Browse by category."""
        category = random.choice(CATEGORIES)
        self.client.get(
            f'/api/v1/products/?category={category}&page=1',
            name='/products/by-category'
        )

    @task(5)
    def add_to_cart(self):
        """Add product to cart."""
        res = self.client.get('/api/v1/products/?limit=5', name='/products/for-cart')
        if res.status_code == 200:
            products = res.json().get('results', [])
            if products:
                product = random.choice(products)
                self.client.post(
                    '/api/v1/cart/add/',
                    json={'product_id': product.get('id'), 'quantity': 1},
                    name='/cart/add',
                    headers=self._auth_headers()
                )

    @task(4)
    def view_cart(self):
        """View cart."""
        self.client.get(
            '/api/v1/cart/',
            name='/cart/view',
            headers=self._auth_headers()
        )

    @task(3)
    def view_orders(self):
        """Check order history."""
        self.client.get(
            '/api/v1/orders/my/',
            name='/orders/my',
            headers=self._auth_headers()
        )

    @task(3)
    def view_notifications(self):
        """Check notifications."""
        self.client.get(
            '/api/v1/notifications/',
            name='/notifications',
            headers=self._auth_headers()
        )

    @task(2)
    def view_wishlist(self):
        """Check wishlist."""
        self.client.get(
            '/api/v1/wishlist/',
            name='/wishlist',
            headers=self._auth_headers()
        )

    @task(2)
    def get_trending(self):
        """Get trending searches."""
        self.client.get('/api/v1/search/trending/', name='/search/trending')

    @task(1)
    def view_store(self):
        """Browse public stores."""
        self.client.get('/api/v1/stores/', name='/stores/list')

    @task(1)
    def check_flash_sales(self):
        """Check active flash sales."""
        self.client.get('/api/v1/promotions/flash-sales/', name='/promotions/flash-sales')


# ─── Seller User ───────────────────────────────────────────────────
class SellerUser(HttpUser):
    """
    Simulates a MICHA seller managing their store.
    Checks dashboard, manages orders, updates products.
    """
    weight = 20  # 20% of traffic
    wait_time = between(3, 8)  # Sellers act less frequently

    def on_start(self):
        self.token = None
        self._login_as_seller()

    def _login_as_seller(self):
        """Try to login as an existing test seller."""
        res = self.client.post('/api/v1/auth/login/', json={
            'email': f'seller_load_{random.randint(1,10)}@micha-test.ao',
            'password': 'LoadTest1234!',
        }, name='/auth/login-seller')
        if res.status_code == 200:
            self.token = res.json().get('access')
            self.client.headers.update({'Authorization': f'Bearer {self.token}'})

    def _auth_headers(self):
        return {'Authorization': f'Bearer {self.token}'} if self.token else {}

    @task(10)
    def view_dashboard(self):
        """Check seller dashboard — most frequent seller action."""
        self.client.get(
            '/api/v1/seller/dashboard/',
            name='/seller/dashboard',
            headers=self._auth_headers()
        )

    @task(8)
    def view_orders(self):
        """Check incoming orders."""
        self.client.get(
            '/api/v1/orders/seller/',
            name='/seller/orders',
            headers=self._auth_headers()
        )

    @task(6)
    def view_products(self):
        """Check product listings."""
        self.client.get(
            '/api/v1/products/my/',
            name='/seller/products',
            headers=self._auth_headers()
        )

    @task(4)
    def view_wallet(self):
        """Check wallet balance."""
        self.client.get(
            '/api/v1/payments/wallet/',
            name='/seller/wallet',
            headers=self._auth_headers()
        )

    @task(3)
    def view_analytics(self):
        """Check analytics."""
        self.client.get(
            '/api/v1/analytics/seller/performance/',
            name='/seller/analytics',
            headers=self._auth_headers()
        )

    @task(2)
    def view_payout_schedule(self):
        """Check payout schedule."""
        self.client.get(
            '/api/v1/payments/payouts/schedule/',
            name='/seller/payout-schedule',
            headers=self._auth_headers()
        )


# ─── Anonymous Browser ─────────────────────────────────────────────
class AnonymousBrowser(HttpUser):
    """
    Simulates anonymous users browsing without account.
    High volume, low complexity.
    """
    weight = 10  # 10% of traffic
    wait_time = between(0.5, 2)

    @task(10)
    def browse_products(self):
        self.client.get('/api/v1/products/', name='/products/anon')

    @task(8)
    def search(self):
        query = random.choice(SEARCH_QUERIES)
        self.client.get(f'/api/v1/search/?q={query}', name='/search/anon')

    @task(5)
    def view_stores(self):
        self.client.get('/api/v1/stores/', name='/stores/anon')

    @task(3)
    def view_flash_sales(self):
        self.client.get('/api/v1/promotions/flash-sales/', name='/flash-sales/anon')


# ─── Event hooks for reporting ─────────────────────────────────────
@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    print("""
╔════════════════════════════════════════╗
║   MICHA Express — Load Test Starting   ║
╚════════════════════════════════════════╝
Target benchmarks:
  - Homepage feed:    < 200ms p95
  - Product search:   < 300ms p95
  - Product detail:   < 150ms p95
  - Cart operations:  < 200ms p95
  - Checkout:         < 500ms p95
""")

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    stats = environment.stats
    print("\n╔════ MICHA Load Test Results ════╗")
    for name, stat in sorted(stats.entries.items()):
        p95 = stat.get_response_time_percentile(0.95)
        color = "✅" if p95 < 300 else "⚠️ " if p95 < 1000 else "❌"
        print(f"{color} {name[1][:40]:40} p95={p95:.0f}ms  rps={stat.current_rps:.1f}  fail%={stat.fail_ratio*100:.1f}%")
