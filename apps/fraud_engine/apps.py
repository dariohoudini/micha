from django.apps import AppConfig


class FraudEngineConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.fraud_engine'
    label = 'fraud_engine'
    verbose_name = 'Fraud Rules Engine'
