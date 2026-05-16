from django.apps import AppConfig


class InboundWebhooksConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.inbound_webhooks'
    verbose_name = 'Inbound webhooks (provider callback verification + audit)'
