"""
Auto-create per-user ledger accounts when a User is created.

Idempotent — safe to re-run (uses get_or_create).
"""
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Account, AccountType


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_user_ledger_accounts(sender, instance, created, **kwargs):
    if not created:
        return
    Account.for_user(instance, AccountType.USER_STORE_CREDIT, currency='AOA')
    Account.for_user(instance, AccountType.USER_LOYALTY_POINTS, currency='PTS')
