from django.apps import AppConfig


class GiftCardsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.gift_cards'
    verbose_name = 'Gift cards (issue, claim, redeem, refund, expire)'
