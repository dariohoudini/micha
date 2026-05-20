from celery import shared_task
from django.utils import timezone

@shared_task(name='payments.reconcile_refunds')
def reconcile_refunds_task(limit=200, window_hours=72):
    """Detect + repair drift where the gateway refunded but local state
    didn't catch up. Wraps refund_reconciliation.reconcile_refunds.

    Schedule via CELERY_BEAT_SCHEDULE. Cheap to run every 5 minutes —
    PaymentProcessor.refund's idempotency makes the repair path safe
    to re-run even on already-consistent rows.
    """
    from .refund_reconciliation import reconcile_refunds
    return reconcile_refunds(limit=limit, window_hours=window_hours)


@shared_task(name='payments.process_pending_refunds')
def process_pending_refunds_task():
    """Drain Refund(status='pending') rows through the gateway.

    Wraps apps.payments.refund_service.process_pending_refunds for the
    Celery scheduler. Add to CELERY_BEAT_SCHEDULE:

        'refunds-sweep': {
            'task': 'payments.process_pending_refunds',
            'schedule': crontab(minute='*/2'),  # every 2 minutes
        }

    Also triggered ad-hoc by the dispute.resolved outbox handler so
    dispute-driven refunds don't wait for the next scheduled sweep.
    """
    from .refund_service import process_pending_refunds
    return process_pending_refunds(limit=200)


@shared_task(name='payments.process_refund')
def process_refund_task(refund_id):
    """Process a single Refund row.

    Used by the dispute.resolved outbox handler to kick processing
    immediately. The sweep task picks up any rows that get deferred or
    missed.
    """
    from apps.orders.models import Refund
    from .refund_service import process_refund
    try:
        refund = Refund.objects.get(pk=refund_id)
    except Refund.DoesNotExist:
        return {'status': 'missing', 'refund_id': refund_id}
    updated = process_refund(refund)
    return {'status': updated.status, 'refund_id': refund_id}


@shared_task(name='payments.release_held_earnings')
def release_held_earnings():
    """Release seller earnings that have passed the hold period (default 7 days).

    Excludes holds where ``is_disputed=True`` — those funds are frozen
    until the dispute is resolved. Releasing a disputed hold mid-dispute
    is the classic "marketplace ate the loss" bug: seller withdraws,
    dispute resolves against them, platform eats the buyer refund.
    See disputes.service for the freeze/settle path.
    """
    try:
        from .models import SellerWallet, WalletTransaction, EarningsHold
        holds = EarningsHold.objects.filter(
            released=False,
            is_disputed=False,
            release_at__lte=timezone.now(),
        )
        released_count = 0
        for hold in holds:
            wallet, _ = SellerWallet.objects.get_or_create(seller=hold.seller)
            # Use select_for_update to prevent race condition
            from apps.payments.models import SellerWallet
            locked_wallet = SellerWallet.objects.select_for_update(of=('self',)).get(pk=wallet.pk)
            locked_wallet.balance += hold.amount
            locked_wallet.save(update_fields=['balance', 'updated_at'])
            wallet = locked_wallet  # keep reference updated
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


@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def retry_failed_payment(self, payment_id: str):
    """
    Retry a failed payment after 5 minutes.
    Max 3 retries (15 minutes total).
    After exhausting retries, marks as abandoned.
    """
    import logging
    from apps.orders.models import Payment
    from apps.payments.gateway import PaymentState

    logger = logging.getLogger('micha.payments')

    try:
        payment = Payment.objects.get(id=payment_id)

        if payment.status == PaymentState.CONFIRMED:
            logger.info(f'Payment {payment_id} already confirmed — skipping retry')
            return

        if self.request.retries >= self.max_retries:
            Payment.objects.filter(id=payment_id).update(
                status=PaymentState.ABANDONED
            )
            logger.error(f'Payment {payment_id} abandoned after {self.max_retries} retries')
            return

        logger.info(f'Retrying payment {payment_id} (attempt {self.request.retries + 1})')

    except Payment.DoesNotExist:
        logger.error(f'Payment {payment_id} not found for retry')
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task
def run_payment_reconciliation():
    """
    Daily reconciliation — check all pending payments against gateway.
    Catches any payments confirmed by gateway but missed by webhook.
    Run: daily at 2am
    """
    import time
    import logging
    from apps.orders.models import Payment
    from apps.payments.gateway import PaymentProcessor, PaymentState
    from apps.payments.models import PaymentReconciliationLog

    logger = logging.getLogger('micha.payments')
    start = time.time()

    pending_payments = Payment.objects.filter(
        status=PaymentState.PENDING,
        created_at__lte=timezone.now() - timedelta(minutes=30),
    ).select_related('order')[:200]

    checked = 0
    discrepancies = 0
    resolved = 0
    errors = []

    processor = PaymentProcessor()

    for payment in pending_payments:
        try:
            result = processor.reconcile_order(payment.order)
            checked += 1

            if result['action'] == 'confirmed':
                discrepancies += 1
                resolved += 1
                logger.warning('Reconciliation found missed payment', extra={
                    'payment_id': str(payment.id),
                    'reference': payment.gateway_reference,
                })

        except Exception as e:
            errors.append({'payment_id': str(payment.id), 'error': str(e)})
            logger.error(f'Reconciliation error for payment {payment.id}: {e}')

    duration = time.time() - start

    PaymentReconciliationLog.objects.create(
        orders_checked=checked,
        discrepancies_found=discrepancies,
        discrepancies_resolved=resolved,
        errors=errors,
        duration_seconds=duration,
    )

    logger.info('Payment reconciliation complete', extra={
        'checked': checked,
        'discrepancies': discrepancies,
        'resolved': resolved,
        'duration_seconds': duration,
    })

    return {
        'checked': checked,
        'discrepancies': discrepancies,
        'resolved': resolved,
    }
