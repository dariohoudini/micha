from celery import shared_task

@shared_task(name='collections.record_price_history')
def record_price_history():
    """Daily snapshot of product prices for the price history chart."""
    try:
        from apps.products.models import Product
        from .models import PriceHistory
        from django.utils import timezone
        from datetime import timedelta

        products = Product.objects.filter(is_active=True, is_archived=False).only('id', 'price')
        records = [PriceHistory(product_id=p.id, price=p.price) for p in products]
        PriceHistory.objects.bulk_create(records)

        # Keep only last 90 days
        cutoff = timezone.now() - timedelta(days=90)
        deleted, _ = PriceHistory.objects.filter(recorded_at__lte=cutoff).delete()
        return f"Recorded {len(records)} prices, pruned {deleted} old records"
    except Exception as e:
        return f"Error: {e}"
