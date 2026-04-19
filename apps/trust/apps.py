from django.apps import AppConfig


class TrustConfig(AppConfig):
    name = "apps.trust"
    label = "ai_trust"
    verbose_name = 'MICHA Trust Score'

    def ready(self):
        try:
            from apps.orders.models import Order
            from django.db.models.signals import post_save
            from django.dispatch import receiver

            @receiver(post_save, sender=Order)
            def on_order_status_change(sender, instance, **kwargs):
                if instance.status == 'delivered':
                    from .services import TrustScoreService
                    TrustScoreService.record_event(
                        seller=instance.seller,
                        event_type='order_delivered',
                        order_id=instance.id,
                    )
                elif instance.status == 'cancelled' and getattr(instance, 'cancelled_by', '') == 'seller':
                    from .services import TrustScoreService
                    TrustScoreService.record_event(
                        seller=instance.seller,
                        event_type='order_cancelled',
                        order_id=instance.id,
                    )
        except ImportError:
            pass
