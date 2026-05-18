import logging
logger = logging.getLogger(__name__)
"""Seller tasks"""
from celery import shared_task


@shared_task(name='seller.seller_engagement_nudge')
def seller_engagement_nudge():
    """
    Nudge sellers who haven't listed a new product in 7+ days.
    Reminds them to keep their catalogue fresh.
    Runs weekly on Mondays.
    """
    from django.contrib.auth import get_user_model
    from django.utils import timezone
    from datetime import timedelta
    from apps.notifications.models import Notification
    from apps.products.models import Product

    User = get_user_model()
    cutoff = timezone.now() - timedelta(days=7)

    # Find sellers with no new products in 7 days
    active_sellers = User.objects.filter(
        is_seller=True,
        status='active',
        is_verified_seller=True,
    )

    nudged = 0
    for seller in active_sellers:
        recent_product = Product.objects.filter(
            store__owner=seller,
            created_at__gte=cutoff,
        ).exists()

        if not recent_product:
            store_name = ''
            try:
                store_obj = seller.stores.first()
                store_name = store_obj.name if store_obj else ''
            except Exception as e:
                logger.debug('Seller-nudge store lookup failed: %s', e)

            Notification.objects.create(
                recipient=seller,
                notification_type='seller_nudge',
                title='Adiciona novos produtos à tua loja!',
                message=(
                    f'{"A " + store_name if store_name else "A tua loja"} '
                    f'não tem novos produtos há mais de 7 dias. Compradores '
                    f'que vêem novidades frequentes compram mais.'
                ),
            )
            nudged += 1

    return f'Nudged {nudged} inactive sellers'
