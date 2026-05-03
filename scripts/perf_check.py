"""
MICHA Express — Quick Performance Check
Tests database query performance without needing a running server.
Run: python scripts/perf_check.py
"""
import os, sys, time, django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.get('DJANGO_SETTINGS_MODULE', '') = 'config.settings'
django.setup()

from django.db import connection, reset_queries
from django.conf import settings

settings.DEBUG = True  # Enable query logging

results = []

def benchmark(name, fn, iterations=10):
    times = []
    for _ in range(iterations):
        reset_queries()
        start = time.perf_counter()
        fn()
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
        query_count = len(connection.queries)

    avg = sum(times) / len(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    results.append((name, avg, p95, query_count))
    status = '✅' if avg < 100 else '⚠️ ' if avg < 500 else '❌'
    print(f"{status} {name:45} avg={avg:.1f}ms  p95={p95:.1f}ms  queries={query_count}")

print("═" * 80)
print("MICHA Express — Database Performance Benchmarks")
print("═" * 80)

# Product listing
from apps.products.models import Product
benchmark("Product.active.all()[:20]",
    lambda: list(Product.objects.filter(is_active=True)[:20]))

benchmark("Product with store+category (select_related)",
    lambda: list(Product.objects.filter(is_active=True).select_related('store', 'category')[:20]))

benchmark("Product with images (prefetch_related)",
    lambda: list(Product.objects.filter(is_active=True).select_related('store', 'category').prefetch_related('images')[:20]))

# User queries
from django.contrib.auth import get_user_model
User = get_user_model()
benchmark("User.objects.count()",
    lambda: User.objects.count())

benchmark("Active sellers list",
    lambda: list(User.objects.filter(is_seller=True, is_verified_seller=True, status='active')[:20]))

# Orders
from apps.orders.models import Order
benchmark("Order.objects.all()[:20]",
    lambda: list(Order.objects.all()[:20]))

benchmark("Order with buyer+store (select_related)",
    lambda: list(Order.objects.select_related('buyer', 'seller')[:20]))

# Cart
from apps.cart.models import Cart
benchmark("Cart with items",
    lambda: list(Cart.objects.prefetch_related('items__product')[:10]))

# Notifications
from apps.notifications.models import Notification
benchmark("Unread notifications count",
    lambda: Notification.objects.filter(is_read=False).count())

# Recommendations
from apps.recommendations.models import UserInterest, ProductInteraction
benchmark("UserInterest top categories",
    lambda: list(UserInterest.objects.filter(score__gt=0).order_by('-score')[:10]))

# Search simulation
benchmark("Product search by title",
    lambda: list(Product.objects.filter(title__icontains='samsung').select_related('store', 'category')[:10]))

benchmark("Product search + filter + order",
    lambda: list(Product.objects.filter(
        is_active=True,
        price__gte=10000,
        price__lte=500000,
    ).select_related('store', 'category').order_by('-wishlist_count')[:20]))

print("\n" + "═" * 80)
print("SUMMARY")
print("═" * 80)
slow = [(n, a, p) for n, a, p, q in results if a > 100]
if slow:
    print(f"⚠️  {len(slow)} slow queries (>100ms avg):")
    for name, avg, p95 in slow:
        print(f"   {name}: avg={avg:.1f}ms")
else:
    print("✅ All queries under 100ms average")

print(f"\nTotal benchmarks: {len(results)}")
print(f"Passing (<100ms): {len([r for r in results if r[1] < 100])}")
print(f"Warning (100-500ms): {len([r for r in results if 100 <= r[1] < 500])}")
print(f"Critical (>500ms): {len([r for r in results if r[1] >= 500])}")
