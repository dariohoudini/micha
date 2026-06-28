from django.apps import AppConfig


class PaymentGatewaysConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.payment_gateways'
    label = 'payment_gateways'
    verbose_name = 'Payment Gateway Integrations'
