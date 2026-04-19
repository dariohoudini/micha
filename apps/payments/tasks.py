from celery import shared_task
from django.utils import timezone

@shared_task(name='payments.release_held_earnings')
def release_held_earnings():
    """Release seller earnings that have passed the hold period (default 7 days)."""
    try:
        from .models import SellerWallet, WalletTransaction, EarningsHold
        holds = EarningsHold.objects.filter(released=False, release_at__lte=timezone.now())
        released_count = 0
        for hold in holds:
            wallet, _ = SellerWallet.objects.get_or_create(seller=hold.seller)
            wallet.balance += hold.amount
            wallet.pending_balance = max(0, wallet.pending_balance - hold.amount)
            wallet.save(update_fields=['balance', 'pending_balance'])
            WalletTransaction.objects.create(
                wallet=wallet,
                type='release',
                amount=hold.amount,
                description=f'Earnings released from order hold',
                balance_after=wallet.balance,
            )
            hold.released = True
            hold.save(update_fields=['released'])
            released_count += 1
        return f"Released earnings from {released_count} holds"
    except Exception as e:
        return f"Error: {e}"

@shared_task(name='payments.auto_payout_sellers')
def auto_payout_sellers():
    """Auto-trigger payouts for sellers with balance above threshold."""
    try:
        from .models import SellerWallet, SellerBankAccount, PayoutRequest
        MIN_PAYOUT = 5000  # 5,000 AOA minimum
        wallets = SellerWallet.objects.filter(balance__gte=MIN_PAYOUT)
        count = 0
        for wallet in wallets:
            bank = SellerBankAccount.objects.filter(seller=wallet.seller, is_default=True).first()
            if bank and not PayoutRequest.objects.filter(seller=wallet.seller, status='pending').exists():
                PayoutRequest.objects.create(seller=wallet.seller, bank_account=bank, amount=wallet.balance)
                count += 1
        return f"Triggered {count} automatic payouts"
    except Exception as e:
        return f"Error: {e}"
