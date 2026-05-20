"""
MICHA Payment Gateway Abstraction Layer
=========================================
Designed for APPYPAY (Multicaixa Express) as primary gateway.
Architecture ensures zero payment loss, idempotency, and full audit trail.

Key guarantees:
1. Every payment attempt is logged BEFORE hitting the gateway
2. Webhook events are idempotent — duplicate webhooks are safe
3. All state transitions use atomic DB transactions
4. Failed payments retry automatically with exponential backoff
5. Wallet credits only happen AFTER confirmed payment (never before)
6. Double-credit prevention via unique reference locks
7. Full reconciliation support — every AOA is accounted for

State machine:
  initiated → pending → confirmed → credited_to_seller
                     ↘ failed → retry → confirmed
                               ↘ abandoned (3 retries exhausted)
"""
import hashlib
import hmac
import json
import logging
import uuid
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache

logger = logging.getLogger('micha.payments')


# ─── Payment States ────────────────────────────────────────────────
class PaymentState:
    INITIATED   = 'initiated'    # We created the payment record
    PENDING     = 'pending'      # Sent to gateway, awaiting callback
    CONFIRMED   = 'confirmed'    # Gateway confirmed payment received
    FAILED      = 'failed'       # Gateway rejected / user cancelled
    REFUNDED    = 'refunded'     # Money returned to buyer
    ABANDONED   = 'abandoned'    # 3 retries exhausted
    DISPUTED    = 'disputed'     # Chargeback / dispute filed


# ─── Payment Event Log ────────────────────────────────────────────
class PaymentEventLogger:
    """
    Append-only log of every payment event.
    Critical for debugging, reconciliation, and dispute resolution.
    """
    @staticmethod
    def log(payment, event_type: str, details: dict = None, error: str = None):
        try:
            from apps.payments.models import PaymentEvent
            PaymentEvent.objects.create(
                payment=payment,
                event_type=event_type,
                details=details or {},
                error=error or '',
            )
        except Exception as e:
            # Never let logging failure break payment flow
            logger.error(f'PaymentEventLogger failed: {e}', extra={
                'payment_id': str(getattr(payment, 'id', 'unknown')),
                'event_type': event_type,
            })


# ─── Idempotency Guard ─────────────────────────────────────────────
class IdempotencyGuard:
    """
    Prevents double-processing of payment events.
    Uses Redis as fast idempotency store + DB as durable backup.
    """
    @staticmethod
    def is_processed(reference: str, event_type: str) -> bool:
        key = f'payment_processed:{hashlib.sha256(f"{reference}:{event_type}".encode()).hexdigest()}'
        if cache.get(key):
            return True
        # Check DB as fallback
        try:
            from apps.payments.models import PaymentEvent
            return PaymentEvent.objects.filter(
                payment__gateway_reference=reference,
                event_type=event_type,
            ).exists()
        except Exception:
            return False

    @staticmethod
    def mark_processed(reference: str, event_type: str, ttl: int = 86400):
        key = f'payment_processed:{hashlib.sha256(f"{reference}:{event_type}".encode()).hexdigest()}'
        cache.set(key, True, timeout=ttl)


# ─── AppyPay Gateway ──────────────────────────────────────────────
class AppyPayGateway:
    """
    APPYPAY / Multicaixa Express integration.
    All methods are designed to be safe to retry.

    Environment variables needed:
        APPYPAY_API_KEY      — API key from APPYPAY dashboard
        APPYPAY_SECRET       — Webhook secret for HMAC verification
        APPYPAY_MERCHANT_ID  — Your merchant ID
        APPYPAY_BASE_URL     — https://api.appypay.co.ao/v1
        APPYPAY_WEBHOOK_URL  — https://yourapp.ao/api/v1/payments/webhook/
    """

    def __init__(self):
        from django.conf import settings
        self.api_key = getattr(settings, 'APPYPAY_API_KEY', '')
        self.secret = getattr(settings, 'APPYPAY_SECRET', '')
        self.merchant_id = getattr(settings, 'APPYPAY_MERCHANT_ID', '')
        self.base_url = getattr(settings, 'APPYPAY_BASE_URL', 'https://api.appypay.co.ao/v1')
        self.webhook_url = getattr(settings, 'APPYPAY_WEBHOOK_URL', '')
        self.is_configured = bool(self.api_key and self.secret and self.merchant_id)

    def initiate_payment(self, payment, phone_number: str) -> dict:
        """
        Initiate a Multicaixa Express payment request.
        Returns gateway response dict.
        This sends a push notification to the buyer's phone.
        """
        if not self.is_configured:
            return self._sandbox_response(payment)

        import requests as http_requests

        payload = {
            'merchant_id': self.merchant_id,
            'reference': str(payment.gateway_reference),
            'amount': str(payment.amount),
            'currency': 'AOA',
            'phone': self._normalize_phone(phone_number),
            'description': f'MICHA Order {str(payment.order_id)[:8].upper()}',
            'webhook_url': self.webhook_url,
            'idempotency_key': str(payment.id),  # prevent duplicate charges
        }

        try:
            response = http_requests.post(
                f'{self.base_url}/payments/initiate',
                json=payload,
                headers={
                    'Authorization': f'Bearer {self.api_key}',
                    'Content-Type': 'application/json',
                    'X-Idempotency-Key': str(payment.id),
                },
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except http_requests.Timeout:
            raise PaymentGatewayError('Gateway timeout — payment may or may not have been initiated')
        except http_requests.HTTPError as e:
            raise PaymentGatewayError(f'Gateway error: {e.response.status_code}')
        except Exception as e:
            raise PaymentGatewayError(f'Network error: {e}')

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """
        Verify APPYPAY webhook signature using HMAC-SHA256.
        MUST be called before processing any webhook event.
        """
        if not self.secret:
            logger.error('APPYPAY_SECRET not configured — rejecting all webhooks')
            return False

        expected = hmac.new(
            self.secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def refund_payment(self, payment, amount: Decimal, reason: str) -> dict:
        """Initiate a refund via APPYPAY."""
        if not self.is_configured:
            return {'status': 'sandbox_refund', 'refund_id': str(uuid.uuid4())}

        import requests as http_requests

        payload = {
            'merchant_id': self.merchant_id,
            'original_reference': str(payment.gateway_reference),
            'amount': str(amount),
            'reason': reason,
            'idempotency_key': f'refund_{payment.id}_{amount}',
        }

        try:
            response = http_requests.post(
                f'{self.base_url}/payments/refund',
                json=payload,
                headers={'Authorization': f'Bearer {self.api_key}'},
                timeout=30,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise PaymentGatewayError(f'Refund failed: {e}')

    def query_payment_status(self, gateway_reference: str) -> dict:
        """
        Query payment status directly from gateway.
        Used for reconciliation and when webhooks are delayed/missed.
        """
        if not self.is_configured:
            return {'status': 'confirmed', 'reference': gateway_reference}

        import requests as http_requests

        try:
            response = http_requests.get(
                f'{self.base_url}/payments/{gateway_reference}',
                headers={'Authorization': f'Bearer {self.api_key}'},
                timeout=15,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            raise PaymentGatewayError(f'Status query failed: {e}')

    def _normalize_phone(self, phone: str) -> str:
        """Normalize Angolan phone number to +244XXXXXXXXX format."""
        digits = ''.join(filter(str.isdigit, phone))
        if digits.startswith('244'):
            return f'+{digits}'
        elif digits.startswith('9') and len(digits) == 9:
            return f'+244{digits}'
        elif len(digits) == 9:
            return f'+244{digits}'
        return f'+{digits}'

    def _sandbox_response(self, payment) -> dict:
        """Simulated response for development (no APPYPAY credentials)."""
        logger.warning('AppyPay in sandbox mode — no real payment processed', extra={
            'payment_id': str(payment.id),
            'amount': str(payment.amount),
        })
        return {
            'status': 'pending',
            'reference': str(payment.gateway_reference),
            'sandbox': True,
            'message': 'Configure APPYPAY_API_KEY to process real payments',
        }


class PaymentGatewayError(Exception):
    """Raised when gateway communication fails."""


# ─── Payment Processor ─────────────────────────────────────────────
class PaymentProcessor:
    """
    Orchestrates the full payment lifecycle.
    All operations are atomic and idempotent.
    """

    def __init__(self):
        self.gateway = AppyPayGateway()
        self.logger = PaymentEventLogger()

    def initiate(self, order, phone_number: str) -> dict:
        """
        Step 1: Create payment record and send to gateway.
        Safe to call multiple times — idempotent via order.idempotency_key.
        """
        from apps.orders.models import Payment

        with transaction.atomic():
            # Check for existing payment on this order
            existing = Payment.objects.filter(
                order=order,
                status__in=[PaymentState.PENDING, PaymentState.CONFIRMED],
            ).first()

            if existing:
                logger.info('Payment already exists for order', extra={
                    'order_id': str(order.id),
                    'payment_id': str(existing.id),
                    'status': existing.status,
                })
                return {'payment_id': str(existing.id), 'status': existing.status}

            # Create payment record FIRST (before hitting gateway)
            payment = Payment.objects.create(
                order=order,
                method='multicaixa_express',
                status=PaymentState.INITIATED,
                gateway_reference=f'MICHA-{str(uuid.uuid4()).replace("-", "")[:16].upper()}',
                amount=order.total,
                currency='AOA',
            )

        # Log initiation
        self.logger.log(payment, 'initiated', {
            'order_id': str(order.id),
            'amount': str(order.total),
            'phone': phone_number[-4:],  # only last 4 digits for privacy
        })

        # Send to gateway (outside transaction — network call)
        try:
            gateway_response = self.gateway.initiate_payment(payment, phone_number)

            with transaction.atomic():
                Payment.objects.filter(id=payment.id).update(
                    status=PaymentState.PENDING,
                )

            self.logger.log(payment, 'gateway_pending', gateway_response)

            return {
                'payment_id': str(payment.id),
                'reference': payment.gateway_reference,
                'status': PaymentState.PENDING,
                'gateway_response': gateway_response,
            }

        except PaymentGatewayError as e:
            with transaction.atomic():
                Payment.objects.filter(id=payment.id).update(
                    status=PaymentState.FAILED,
                )
            self.logger.log(payment, 'gateway_error', error=str(e))
            raise

    def confirm_payment(self, gateway_reference: str, gateway_data: dict) -> bool:
        """
        Step 2: Called by webhook when gateway confirms payment.
        IDEMPOTENT — safe to call multiple times with same reference.
        Returns True if payment was processed, False if already handled.
        """
        # Idempotency check
        if IdempotencyGuard.is_processed(gateway_reference, 'confirmed'):
            logger.info('Duplicate webhook ignored', extra={'reference': gateway_reference})
            return False

        from apps.orders.models import Payment, Order

        try:
            payment = Payment.objects.select_for_update().get(
                gateway_reference=gateway_reference
            )
        except Payment.DoesNotExist:
            logger.error('Payment not found for reference', extra={'reference': gateway_reference})
            return False

        if payment.status == PaymentState.CONFIRMED:
            logger.info('Payment already confirmed', extra={'reference': gateway_reference})
            IdempotencyGuard.mark_processed(gateway_reference, 'confirmed')
            return False

        with transaction.atomic():
            # Update payment
            Payment.objects.filter(id=payment.id).update(
                status=PaymentState.CONFIRMED,
                paid_at=timezone.now(),
            )

            # Update order via the state machine so the transition is
            # validated (pending → confirmed is the canonical move),
            # audit-logged, outbox-published, and protection-state-recalced
            # consistently with every other path.
            order = Order.objects.select_for_update().get(id=payment.order_id)
            from apps.orders.state_machine import transition, InvalidTransition
            try:
                order = transition(
                    order, 'confirmed',
                    source='gateway:payment_confirmed',
                    note=f'Payment confirmed via {payment.method}',
                )
            except InvalidTransition:
                # Already confirmed (idempotent retry) — proceed without raising
                pass
            # payment_status lives outside the state machine since it's
            # a separate field with its own (smaller) state space.
            Order.objects.filter(pk=order.pk).update(payment_status='paid')

            # Credit seller wallet (in escrow until delivery)
            self._credit_seller_escrow(order, payment)

            # Outbox: durable async-work intent. Lives in this transaction
            # so a broker outage can no longer cause a "silent" payment.
            try:
                from apps.outbox.service import publish
                publish(
                    topic='order.payment_confirmed',
                    payload={
                        'order_id': str(order.id),
                        'payment_id': str(payment.id),
                        'amount': str(payment.amount),
                    },
                    dedupe_key=f'order.payment_confirmed:{order.id}',
                    ref_type='order', ref_id=str(order.id),
                )
            except Exception as e:
                logger.error('Outbox publish failed for order.payment_confirmed', extra={
                    'order_id': str(order.id), 'error': str(e),
                })

        # Telemetry
        try:
            from apps.telemetry.metrics import payments_confirmed
            payments_confirmed.labels(method=getattr(payment, 'method', '') or 'unknown').inc()
        except Exception:
            pass

        # Log and mark idempotent
        self.logger.log(payment, 'confirmed', gateway_data)
        IdempotencyGuard.mark_processed(gateway_reference, 'confirmed')

        logger.info('Payment confirmed', extra={
            'order_id': str(order.id),
            'amount': str(payment.amount),
            'reference': gateway_reference,
        })

        return True

    def fail_payment(self, gateway_reference: str, reason: str) -> bool:
        """Called by webhook when gateway reports payment failure.

        Must do FOUR things, atomically, and idempotently:
          1. Flip the payment row to FAILED.
          2. Restore the inventory units that checkout decremented.
          3. Refund any store credit that was redeemed.
          4. Release any coupons that were applied.

        Steps 2-4 used to be missing — the function set order.status
        and walked away. Each failed payment therefore silently leaked
        1+ inventory units, kept the buyer's store credit, and inflated
        the coupon's used_count. Over a few months of production
        traffic this produces invisible catalog drift, customer-support
        load, and analytics that don't match reality.

        The restore_order() primitive is idempotent so a duplicate
        webhook delivery is safe: the second call sees the order's
        stock_restored flag and no-ops.
        """
        if IdempotencyGuard.is_processed(gateway_reference, 'failed'):
            return False

        from apps.orders.models import Payment, Order
        from apps.orders.stock_restore import (
            restore_order, StockRestoreError,
        )

        try:
            with transaction.atomic():
                payment = Payment.objects.select_for_update().get(
                    gateway_reference=gateway_reference
                )

                if payment.status in [PaymentState.CONFIRMED, PaymentState.REFUNDED]:
                    logger.warning('Cannot fail already confirmed payment', extra={
                        'reference': gateway_reference,
                        'current_status': payment.status,
                    })
                    return False

                Payment.objects.filter(id=payment.id).update(
                    status=PaymentState.FAILED,
                )

                # Set order status via the state machine so the
                # transition is validated, audited, and outbox-published.
                # admin_override because payment-fail can land while the
                # order is in non-pending states (e.g. confirmed via a
                # racing webhook arrived first, then the failure arrived).
                from apps.orders.state_machine import (
                    transition as _state_transition, InvalidTransition,
                )
                order = Order.objects.get(id=payment.order_id)
                try:
                    _state_transition(
                        order, 'payment_failed',
                        source=f'gateway:fail_payment',
                        note=f'Gateway reported failure: {reason[:80]}',
                        admin_override=True,
                    )
                except InvalidTransition:
                    # Already in payment_failed / terminal — idempotent
                    pass
                Order.objects.filter(id=payment.order_id).update(
                    payment_status='failed',
                )

            # restore_order opens its own atomic block + acquires PK-ordered
            # locks on the inventory rows. Doing it OUTSIDE the payment-row
            # lock keeps the lock-graph simple (payment → order, then a
            # separate inventory lock cycle).
            try:
                restore_order(
                    order_id=str(payment.order_id),
                    source='payment_failed',
                    reason=f'gateway:{reason[:80]}',
                )
            except StockRestoreError as e:
                # Order already shipped / cancelled — log but don't fail
                # the webhook. The payment side is already updated; the
                # mismatch is rare (race between ship and fail) and
                # operators can reconcile via the admin.
                logger.warning(
                    'fail_payment: restore_order refused for order=%s: %s',
                    payment.order_id, e,
                )

            self.logger.log(payment, 'failed', {'reason': reason})
            IdempotencyGuard.mark_processed(gateway_reference, 'failed')

            # Schedule retry
            self._schedule_payment_retry(payment)

            return True

        except Payment.DoesNotExist:
            logger.error('Payment not found for failure webhook', extra={'reference': gateway_reference})
            return False

    def refund(self, order, amount: Decimal = None, reason: str = 'customer_request') -> bool:
        """
        Initiate refund for an order.

        Ordering — gateway first, local second
        ───────────────────────────────────────
        Prior implementation: debit wallet + flip Payment status + state
        transition inside an atomic block, THEN call the gateway. If the
        gateway call raised (network blip, 5xx, timeout), the wallet had
        already been debited and the order showed 'refunded' — but the
        buyer's card was NEVER actually credited. Worse, the refund
        worker would mark the row 'rejected' (because Payment.status was
        no longer CONFIRMED on retry) and the buyer would be told the
        refund was issued. Pure financial leak.

        New ordering:
          1. Call gateway FIRST. Gateway is the source of truth for
             whether the buyer actually got the money.
          2. ONLY on gateway success, run the atomic block to update
             local state (wallet debit, Payment.status, state machine).

        If the gateway call fails: nothing local has changed. The refund
        worker catches the exception, applies backoff, and retries. The
        gateway's own deterministic idempotency key
        (refund_<payment.id>_<amount>) means a retry on the same payment
        + amount returns the existing refund_id — no double-refund risk.

        If the gateway succeeds but the local atomic block fails: the
        gateway has the canonical refund. PaymentEvent is the immutable
        audit; reconciliation can detect the gap by comparing
        Payment.status against PaymentEvent('refunded') rows for the
        same payment.

        Idempotency
        ───────────
        Calling on an already-REFUNDED payment is a no-op that returns
        True. The prior version raised "No confirmed payment found",
        which the refund worker maps to permanent-rejected — incorrect
        for an already-successful refund.
        """
        from apps.orders.models import Payment

        # Accept already-REFUNDED payments so a retry of an in-flight
        # refund that succeeded at the gateway but failed locally is
        # recognised as already-done rather than rejected.
        payment = Payment.objects.filter(
            order=order,
            status__in=(PaymentState.CONFIRMED, PaymentState.REFUNDED),
        ).order_by('-created_at').first()

        if not payment:
            raise PaymentGatewayError('No confirmed payment found for this order')

        refund_amount = amount or payment.amount

        # Atomic test-and-set via cache.add — replaces the prior
        # get-then-set which had a TOCTOU race under any concurrency.
        refund_key = f'refund_lock:{payment.id}'
        if not cache.add(refund_key, True, timeout=60):
            raise PaymentGatewayError('Refund already in progress for this payment')

        try:
            # ── Step 1: Call gateway FIRST (source of truth) ──────────
            #
            # If we're already at REFUNDED locally, this is a reconcile
            # attempt — call the gateway anyway (its idempotency_key
            # replays the original refund_id) so we get a confirming
            # response and an audit log. If gateway raises, propagate
            # to caller; nothing local has been touched yet.
            gateway_result = self.gateway.refund_payment(
                payment, refund_amount, reason,
            )
            gateway_refund_id = str(gateway_result.get('refund_id', '')) if isinstance(gateway_result, dict) else ''

            # ── Step 2: Local state update — gateway succeeded ────────
            with transaction.atomic():
                # Re-fetch under lock — defends against a concurrent
                # transition that ran while we waited on the gateway.
                payment_locked = Payment.objects.select_for_update().get(
                    pk=payment.pk,
                )

                if payment_locked.status == PaymentState.REFUNDED:
                    # Already reconciled locally. Log a replay event so
                    # ops can correlate the duplicate gateway call.
                    self.logger.log(
                        payment_locked, 'refund_replay',
                        {
                            'amount': str(refund_amount),
                            'reason': reason,
                            'gateway_refund_id': gateway_refund_id,
                        },
                    )
                    return True

                # Debit seller wallet (or pending_balance if that's
                # where the funds live). Wrapped wide because a missing
                # wallet shouldn't block the refund — the gateway has
                # already credited the buyer.
                try:
                    from apps.payments.models import SellerWallet
                    wallet = SellerWallet.objects.select_for_update().get(
                        seller=order.seller,
                    )
                    if wallet.balance >= refund_amount:
                        wallet.debit(
                            refund_amount,
                            f'Refund for order {str(order.id)[:8]}',
                            reference=f'REFUND-{payment_locked.gateway_reference}',
                        )
                    elif wallet.pending_balance >= refund_amount:
                        wallet.pending_balance -= refund_amount
                        wallet.save(update_fields=['pending_balance', 'updated_at'])
                    else:
                        # Seller's wallet doesn't cover the refund —
                        # platform eats the gap. Log it loudly so ops
                        # can chase clawback.
                        logger.warning(
                            'refund: wallet underfunded — platform absorbs gap',
                            extra={
                                'payment_id': str(payment_locked.pk),
                                'order_id': str(order.id),
                                'amount': str(refund_amount),
                                'wallet_balance': str(wallet.balance),
                                'wallet_pending': str(wallet.pending_balance),
                                'gateway_refund_id': gateway_refund_id,
                            },
                        )
                except SellerWallet.DoesNotExist:
                    logger.warning(
                        'refund: seller wallet missing — gateway already refunded',
                        extra={
                            'payment_id': str(payment_locked.pk),
                            'order_id': str(order.id),
                            'gateway_refund_id': gateway_refund_id,
                        },
                    )
                except Exception as e:
                    logger.error(
                        f'refund: wallet debit failed AFTER gateway refunded: {e}',
                        exc_info=True,
                    )

                # Flip Payment to REFUNDED.
                Payment.objects.filter(pk=payment_locked.pk).update(
                    status=PaymentState.REFUNDED,
                )

                # Route through the state machine so the refund transition
                # gets audited + protection-state-recalced. admin_override
                # because refunds may be initiated from terminal states
                # (delivered, completed) which would otherwise be blocked.
                from apps.orders.state_machine import (
                    transition as _state_transition, InvalidTransition,
                )
                try:
                    _state_transition(
                        order, 'refunded',
                        source='gateway:refund_payment',
                        note=f'Refund {refund_amount} via {payment_locked.method}',
                        admin_override=True,
                    )
                except InvalidTransition:
                    # Already refunded at state-machine layer — idempotent.
                    pass

                # PaymentEvent inside the atomic block so the audit row
                # commits together with the status flip. Carries the
                # gateway_refund_id for reconciliation joins.
                self.logger.log(
                    payment_locked, 'refunded',
                    {
                        'amount': str(refund_amount),
                        'reason': reason,
                        'gateway_refund_id': gateway_refund_id,
                    },
                )

            return True

        finally:
            cache.delete(refund_key)

    def reconcile_order(self, order) -> dict:
        """
        Check payment status directly from gateway.
        Called when webhook is delayed or missing.
        Fixes the common issue of payment confirmed by gateway but not reflected in our DB.
        """
        from apps.orders.models import Payment

        payment = Payment.objects.filter(order=order).order_by('-created_at').first()
        if not payment:
            return {'status': 'no_payment', 'action': 'none'}

        if payment.status == PaymentState.CONFIRMED:
            return {'status': 'already_confirmed', 'action': 'none'}

        try:
            gateway_status = self.gateway.query_payment_status(payment.gateway_reference)
            gateway_payment_status = gateway_status.get('status', '')

            if gateway_payment_status in ('confirmed', 'paid', 'success'):
                if not IdempotencyGuard.is_processed(payment.gateway_reference, 'confirmed'):
                    self.confirm_payment(payment.gateway_reference, gateway_status)
                    return {'status': 'reconciled', 'action': 'confirmed'}

            return {'status': gateway_payment_status, 'action': 'none'}

        except PaymentGatewayError as e:
            logger.error('Reconciliation failed', extra={
                'order_id': str(order.id),
                'error': str(e),
            })
            return {'status': 'reconciliation_failed', 'action': 'none', 'error': str(e)}

    def _credit_seller_escrow(self, order, payment):
        """
        Put seller earnings in escrow (EarningsHold).
        Released after delivery confirmation (7-day hold).
        """
        from apps.payments.models import SellerWallet, EarningsHold
        from datetime import timedelta

        # Calculate seller earnings (order total minus platform commission)
        commission_pct = self._get_commission_rate(order)
        platform_fee = payment.amount * Decimal(str(commission_pct / 100))
        seller_earnings = payment.amount - platform_fee

        # Hold earnings for 7 days
        release_at = timezone.now() + timedelta(days=7)

        EarningsHold.objects.create(
            seller=order.seller,
            order=order,
            amount=seller_earnings,
            release_at=release_at,
        )

        # Add to pending balance immediately (visible but not withdrawable)
        wallet, _ = SellerWallet.objects.get_or_create(seller=order.seller)
        wallet.hold(seller_earnings, f'Earnings from order {str(order.id)[:8]}')

        # Source-of-truth: post the canonical decomposition journal.
        # buyer_paid is what the gateway received (= order.total). Subsidies, seller
        # discounts and store credit were captured on the Order at checkout time, so
        # we replay them here to attribute the platform/seller funding split.
        try:
            from apps.ledger.service import record_payment_received
            record_payment_received(
                order=order,
                buyer_paid=payment.amount,
                commission_amount=platform_fee,
                platform_subsidy=getattr(order, 'platform_subsidy', 0) or 0,
                seller_discount=getattr(order, 'seller_subsidy', 0) or 0,
            )
        except Exception as e:
            logger.error('Ledger posting failed for payment_received', extra={
                'order_id': str(order.id), 'error': str(e),
            })

        logger.info('Seller earnings held in escrow', extra={
            'seller_id': str(order.seller.id),
            'amount': str(seller_earnings),
            'release_at': release_at.isoformat(),
            'platform_fee': str(platform_fee),
        })

    def _get_commission_rate(self, order) -> float:
        """Get platform commission rate for this order's category."""
        try:
            from apps.payments.models import PlatformCommission
            # Try category-specific rate first
            if order.items.exists():
                first_item = order.items.first()
                category = (
                    first_item.product.category
                    if first_item and first_item.product
                    else None
                )
                commission = PlatformCommission.objects.filter(
                    category=category,
                ).first()
                if commission:
                    return float(commission.percentage)
            # Fall back to default
            default = PlatformCommission.objects.filter(is_default=True).first()
            return float(default.percentage) if default else 10.0
        except Exception:
            return 10.0

    def _post_payment_tasks(self, order, payment):
        """Legacy hook — superseded by outbox publish in confirm_payment.
        Left in place for any code path that still calls it explicitly."""
        try:
            from apps.outbox.service import publish
            publish(
                topic='order.payment_confirmed',
                payload={'order_id': str(order.id), 'payment_id': str(payment.id)},
                dedupe_key=f'order.payment_confirmed:{order.id}',
                ref_type='order', ref_id=str(order.id),
            )
        except Exception as e:
            logger.error(f'Outbox publish failed in _post_payment_tasks: {e}')

    def _schedule_payment_retry(self, payment):
        """Schedule a payment retry 5 minutes from now via the outbox.

        Replaces a Celery countdown task. Outbox `delay_seconds` survives a
        broker outage; the dispatcher will run the handler when its
        next_attempt_at is reached.
        """
        try:
            from apps.outbox.service import publish
            publish(
                topic='payment.retry_scheduled',
                payload={'payment_id': str(payment.id)},
                # Use payment.id + a coarse retry-bucket so multiple retries
                # within the same 5-min window collapse to one attempt.
                dedupe_key=f'payment.retry_scheduled:{payment.id}:{int(timezone.now().timestamp() // 300)}',
                ref_type='payment', ref_id=str(payment.id),
                delay_seconds=300,
                max_attempts=3,
            )
        except Exception as e:
            logger.debug(f'Could not schedule payment retry via outbox: {e}')
