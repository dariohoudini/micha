from django.apps import AppConfig


class PaymentOpsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.payment_ops'
    label = 'payment_ops'
    verbose_name = 'Payment Operations'
