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
