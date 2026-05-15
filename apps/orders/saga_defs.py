"""
apps/orders/saga_defs.py

Concrete saga definitions for the orders domain. Auto-discovered by the
sagas app on Django startup.

──── abandoned_checkout ────────────────────────────────────────────────────
Problem: a buyer hits POST /checkout, we create an Order and decrement stock,
but they never complete the payment. Stock sits trapped, the order rots in
``payment_status='pending'`` forever.

Saga: per pending order, periodically (or on a delayed schedule):
  1. Reconcile with the payment gateway — maybe the buyer DID pay and we just
     never received the webhook. If so, mark paid and STOP (no compensation).
  2. If gateway says no payment after the grace period:
     - Restore stock back to the product/variant rows
     - Refund any store credit that was redeemed
     - Mark the order cancelled

If step 2 raises mid-way (e.g. stock restore crashes for one item), the runner
flips to NEEDS_ATTENTION and surfaces the saga in the ops queue — we do NOT
silently leave inventory in an inconsistent state.
"""
from decimal import Decimal
import logging
from django.utils import timezone

from apps.sagas.registry import SagaDef, SagaStep, register, SagaAbort

log = logging.getLogger(__name__)


# ─── Step actions ──────────────────────────────────────────────────────────

def _reconcile_with_gateway(payload, saga):
    """If the gateway shows the order was paid after all, abort the saga
    (no compensation needed — order just needs a paid-marker)."""
    from apps.orders.models import Order
    order_id = payload['order_id']
    order = Order.objects.filter(pk=order_id).first()
    if order is None:
        # Order was deleted out from under us — nothing to reap.
        raise SagaAbort('order_not_found')
    if order.payment_status == 'paid':
        # Already paid — no need to reap.
        payload['skip_reap'] = True
        raise SagaAbort('already_paid')

    # Try to query the actual gateway. Failure here is non-fatal: we proceed
    # with the reap rather than getting stuck (the gateway will reject the
    # paid-event later if it ever arrives, because the order is cancelled).
    try:
        from apps.payments.gateway import PaymentService
        from apps.payments.models import Payment
        pay = Payment.objects.filter(order=order).order_by('-created_at').first()
        if pay and pay.gateway_reference:
            res = PaymentService().reconcile_order(order)
            if (res or {}).get('status') in ('confirmed', 'paid', 'success'):
                payload['skip_reap'] = True
                raise SagaAbort('gateway_says_paid')
    except SagaAbort:
        raise
    except Exception as e:
        log.warning('reconcile gateway query failed (proceeding to reap): %s', e)


def _restore_stock(payload, saga):
    """Put inventory back. We track *what* we restored in the payload so the
    compensation step can undo if a later step fails."""
    from apps.orders.models import Order, OrderItem
    from apps.products.models import Product
    from apps.inventory.models import ProductVariantCombo

    order = Order.objects.get(pk=payload['order_id'])
    restored = []  # [{kind: 'product'|'combo', id, qty}]
    for it in OrderItem.objects.filter(order=order).select_related('product'):
        qty = int(it.quantity or 0)
        if qty <= 0:
            continue
        if it.variant_combo_id:
            ProductVariantCombo.objects.filter(pk=it.variant_combo_id).update(
                quantity=models_F('quantity') + qty, is_active=True,
            )
            restored.append({'kind': 'combo', 'id': it.variant_combo_id, 'qty': qty})
        elif it.product_id:
            Product.objects.filter(pk=it.product_id).update(
                quantity=models_F('quantity') + qty, is_active=True,
            )
            restored.append({'kind': 'product', 'id': str(it.product_id), 'qty': qty})
    payload['restored'] = restored


def _restore_stock_compensation(payload, saga):
    """Undo a stock restore: re-subtract what we put back. Only runs if a
    LATER step failed and we need to roll the whole reap back (rare — the
    reap is one-way most of the time)."""
    from apps.products.models import Product
    from apps.inventory.models import ProductVariantCombo
    for entry in payload.get('restored', []):
        qty = int(entry.get('qty', 0))
        if entry['kind'] == 'combo':
            ProductVariantCombo.objects.filter(pk=entry['id']).update(
                quantity=models_F('quantity') - qty,
            )
        else:
            Product.objects.filter(pk=entry['id']).update(
                quantity=models_F('quantity') - qty,
            )


def _refund_store_credit(payload, saga):
    """If the order redeemed any store credit, return it to the buyer."""
    from apps.orders.models import Order
    from django.contrib.auth import get_user_model
    User = get_user_model()
    order = Order.objects.get(pk=payload['order_id'])
    credit = Decimal(str(order.store_credit_used or 0))
    if credit <= 0:
        payload['credit_refunded'] = '0'
        return
    User.objects.filter(pk=order.buyer_id).update(
        store_credit=models_F('store_credit') + credit,
    )
    payload['credit_refunded'] = str(credit)


def _refund_store_credit_compensation(payload, saga):
    """If something fails after we returned credit, take it back again."""
    from apps.orders.models import Order
    from django.contrib.auth import get_user_model
    User = get_user_model()
    refunded = Decimal(payload.get('credit_refunded') or '0')
    if refunded <= 0:
        return
    order = Order.objects.get(pk=payload['order_id'])
    User.objects.filter(pk=order.buyer_id).update(
        store_credit=models_F('store_credit') - refunded,
    )


def _cancel_order(payload, saga):
    """Mark the order cancelled. No compensation — once cancelled, stays."""
    from apps.orders.models import Order
    Order.objects.filter(pk=payload['order_id']).update(
        status='cancelled', payment_status='failed', updated_at=timezone.now(),
    )


def _emit_reaped_event(payload, saga):
    """Publish an outbox event so downstream systems (analytics, seller
    webhooks, notifications) know the order was reaped."""
    try:
        from apps.outbox.service import publish
        publish(
            topic='order.cancelled',
            payload={'order_id': payload['order_id'], 'reason': 'abandoned_checkout'},
            dedupe_key=f'saga.abandoned_checkout:{payload["order_id"]}',
            ref_type='order', ref_id=payload['order_id'],
        )
    except Exception as e:
        # Non-fatal — the order is already cancelled; a missing notification
        # is not a reason to flip the saga to needs_attention.
        log.warning('emit reaped event failed: %s', e)


# Imported late to avoid circular: Django F-expression
from django.db.models import F as models_F  # noqa: E402


# ─── Definition ────────────────────────────────────────────────────────────

register(SagaDef(
    name='abandoned_checkout',
    max_lifetime_seconds=60 * 60,  # 1h — if we can't finish reaping in an hour, sweep abandons it
    steps=[
        SagaStep('reconcile_with_gateway', _reconcile_with_gateway, None),
        SagaStep('restore_stock',          _restore_stock,           _restore_stock_compensation),
        SagaStep('refund_store_credit',    _refund_store_credit,     _refund_store_credit_compensation),
        SagaStep('cancel_order',           _cancel_order,            None),
        SagaStep('emit_reaped_event',      _emit_reaped_event,       None),
    ],
))


# ─── return_completion saga ────────────────────────────────────────────────
# When a seller (or admin override) marks a return ``completed``, this saga
# does the three things that MUST happen atomically-with-compensation:
#   1. Restock the returned items   (compensable)
#   2. Refund the buyer             (compensable)
#   3. Stamp the return row with the resulting amounts (no comp)
#
# If step 2 (refund) fails mid-way, step 1 (restock) is rolled back so we
# don't end up with inventory restored but no refund issued — that would be
# a quiet payout to the seller. If a compensation itself fails the saga
# flips to NEEDS_ATTENTION and surfaces in the ops queue.

def _return_restock_items(payload, saga):
    """Put inventory back. Records what we restored so the compensation can
    undo precisely if a later step fails."""
    from apps.orders.return_models import ReturnRequest
    from apps.orders.models import OrderItem
    from apps.products.models import Product
    from apps.inventory.models import ProductVariantCombo

    rr = ReturnRequest.objects.select_related('order').get(pk=payload['return_id'])
    if rr.restocked:
        payload['restocked_items'] = []  # idempotent re-run; nothing to do
        return

    restored = []
    for it in OrderItem.objects.filter(order=rr.order):
        qty = int(it.quantity or 0)
        if qty <= 0:
            continue
        if it.variant_combo_id:
            ProductVariantCombo.objects.filter(pk=it.variant_combo_id).update(
                quantity=models_F('quantity') + qty, is_active=True,
            )
            restored.append({'kind': 'combo', 'id': it.variant_combo_id, 'qty': qty})
        elif it.product_id:
            Product.objects.filter(pk=it.product_id).update(
                quantity=models_F('quantity') + qty, is_active=True,
            )
            restored.append({'kind': 'product', 'id': str(it.product_id), 'qty': qty})
    payload['restocked_items'] = restored
    ReturnRequest.objects.filter(pk=rr.pk).update(restocked=True)


def _return_restock_compensation(payload, saga):
    """Undo the restock — re-subtract what we put back."""
    from apps.products.models import Product
    from apps.inventory.models import ProductVariantCombo
    from apps.orders.return_models import ReturnRequest
    for entry in payload.get('restocked_items', []) or []:
        qty = int(entry.get('qty', 0))
        if entry['kind'] == 'combo':
            ProductVariantCombo.objects.filter(pk=entry['id']).update(
                quantity=models_F('quantity') - qty,
            )
        else:
            Product.objects.filter(pk=entry['id']).update(
                quantity=models_F('quantity') - qty,
            )
    ReturnRequest.objects.filter(pk=payload['return_id']).update(restocked=False)


def _return_issue_refund(payload, saga):
    """Issue the refund through the ledger (single source of truth) and
    bump the buyer's cached store_credit balance if that's the destination."""
    from apps.orders.return_models import ReturnRequest
    from apps.orders.models import Order
    from django.contrib.auth import get_user_model
    User = get_user_model()

    rr = ReturnRequest.objects.select_related('order').get(pk=payload['return_id'])
    order = rr.order
    amount = Decimal(str(order.total or 0))
    if amount <= 0:
        payload['refunded_amount'] = '0'
        return

    try:
        from apps.ledger.service import record_refund_to_buyer
        record_refund_to_buyer(
            order=order, amount=amount,
            refund_id=f'return:{rr.id}',
            destination=rr.refund_destination,
        )
    except Exception:
        # Re-raise so the saga compensates the restock.
        raise

    if rr.refund_destination == 'store_credit':
        User.objects.filter(pk=order.buyer_id).update(
            store_credit=models_F('store_credit') + amount,
        )
    payload['refunded_amount'] = str(amount)
    payload['refund_destination'] = rr.refund_destination
    ReturnRequest.objects.filter(pk=rr.pk).update(refunded_amount=amount)


def _return_refund_compensation(payload, saga):
    """Reverse the refund. Bumps the user balance back down and posts a
    compensating ledger journal so the books stay balanced."""
    refunded = Decimal(payload.get('refunded_amount') or '0')
    if refunded <= 0:
        return
    from apps.orders.return_models import ReturnRequest
    from apps.orders.models import Order
    from django.contrib.auth import get_user_model
    User = get_user_model()
    rr = ReturnRequest.objects.select_related('order').get(pk=payload['return_id'])
    if payload.get('refund_destination') == 'store_credit':
        User.objects.filter(pk=rr.order.buyer_id).update(
            store_credit=models_F('store_credit') - refunded,
        )
    # Best-effort journal reversal — if this fails we still surface via the
    # ledger drift detector in the ops queue.
    try:
        from apps.ledger.service import record_payout_reverse
        record_payout_reverse(
            order=rr.order, amount=refunded,
            reason_id=f'return-undo:{rr.id}',
        )
    except Exception as e:
        log.warning('refund compensation ledger reversal failed: %s', e)
    ReturnRequest.objects.filter(pk=rr.pk).update(refunded_amount=0)


def _return_finalise(payload, saga):
    """No-op finaliser — kept as a step so the saga has a clean "completed"
    boundary distinct from refund. Useful hook for future additions
    (notification email, tax adjustment, etc.) without restructuring."""
    log.info('return %s completed: refund=%s, restocked=%s',
             payload.get('return_id'), payload.get('refunded_amount'),
             bool(payload.get('restocked_items')))


register(SagaDef(
    name='return_completion',
    max_lifetime_seconds=60 * 60,
    steps=[
        SagaStep('restock_items', _return_restock_items, _return_restock_compensation),
        SagaStep('issue_refund',  _return_issue_refund,  _return_refund_compensation),
        SagaStep('finalise',      _return_finalise,      None),
    ],
))
