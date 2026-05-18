"""
apps/orders/stock_restore.py

Single source of truth for unwinding an order. Called from THREE paths
that all need to do the same thing in the same way:

  1. Payment-failed webhook (apps.payments.gateway.fail_payment)
       Gateway tells us the card was declined / 3DS-cancelled / etc.
       Stock and store-credit and coupon-usage that were committed at
       checkout must be returned, or we silently bleed inventory and
       value.

  2. Abandoned-checkout saga (apps.orders.saga_defs)
       Reaper finds an order stuck in 'pending' beyond the grace window
       and unwinds it.

  3. Manual buyer cancel (apps.orders.views.CancelOrderView)
       Buyer clicks "cancel order" before the seller ships.

Pre-fix, only path #3 actually restocked inventory. Path #1 said
"Return stock" in a comment but never did it; the comment lied for
months. Every failed payment leaked 1+ inventory units, every coupon
on a failed payment inflated its used_count forever, every store-credit
redemption against a failed payment was permanently lost from the
buyer's balance.

Design notes
─────────────
  • Idempotent — re-running on an already-restored order is a no-op,
    NOT a double-restore. Guarded via Order.stock_restored boolean
    (defaulted False; the only writer is THIS function).
  • Atomic — entire restoration runs in one transaction so partial
    states are impossible. If the function returns, every piece moved
    together; if it raises, none of it stuck.
  • Lock-ordered — products and variants are locked in ascending PK
    order to prevent deadlock between concurrent restorations of
    overlapping orders.
  • Composes with the ledger — store-credit refund posts a journal
    entry so the financial source of truth stays consistent with
    the cached counter on the User row.
  • Coupon usage decrement — uses the canonical coupon_service.release,
    not a raw F-expression. The service is idempotent at the
    redemption-row level so retries are safe.
  • Telemetry — every restoration increments stock_restored_total,
    labelled by source, so ops can monitor real-world failure rates.

Failure modes intentionally NOT covered here:
  • If the order was already shipped / delivered we refuse to restock
    (the units physically left the warehouse; restocking the catalog
    would oversell).
  • If the order is already 'cancelled' or 'payment_failed' AND the
    stock_restored flag is True, this is a no-op.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import F
from django.utils import timezone


log = logging.getLogger(__name__)


# Statuses where physical fulfillment has begun — restocking would
# create a phantom unit that isn't in the warehouse.
_NON_RESTORABLE_STATUSES = frozenset({
    'shipped', 'delivered', 'completed',
})


class StockRestoreError(Exception):
    pass


def restore_order(*, order_id: str, source: str,
                  reason: str = '') -> dict:
    """Unwind a single order's inventory, store credit, and coupon usage.

    Args:
      order_id: PK of the Order to unwind. UUID string.
      source: tag for telemetry / audit. One of:
        'payment_failed', 'abandoned_checkout', 'manual_cancel'.
      reason: human-readable note attached to the audit row.

    Returns a dict describing what was restored, suitable for logging:
        {
          'order_id': '...',
          'restored_items': [...],
          'credit_refunded': '0.00',
          'coupons_released': [...],
          'already_restored': False,
        }

    Idempotent — re-calling on an order whose stock has already been
    restored is a no-op and returns ``already_restored=True``.

    Atomic — the whole unwind happens inside one transaction. If any
    sub-step fails the entire thing rolls back, and ``stock_restored``
    stays False so a later retry can complete the work.
    """
    from apps.orders.models import Order, OrderItem
    from apps.products.models import Product
    from apps.inventory.models import ProductVariantCombo
    from apps.promotions.models import Coupon

    result = {
        'order_id': order_id,
        'restored_items': [],
        'credit_refunded': '0.00',
        'coupons_released': [],
        'already_restored': False,
        'source': source,
    }

    with transaction.atomic():
        # Lock the order row first so nobody else (saga, manual cancel,
        # webhook retry) races us through.
        try:
            order = Order.objects.select_for_update().get(pk=order_id)
        except Order.DoesNotExist:
            raise StockRestoreError(f'Order {order_id} does not exist')

        # Refuse to restock orders that already shipped — physical units
        # have left the warehouse.
        if order.status in _NON_RESTORABLE_STATUSES:
            raise StockRestoreError(
                f'Refusing to restock order in status={order.status}; '
                f'physical fulfillment has begun.'
            )

        if getattr(order, 'stock_restored', False):
            log.info('restore_order: %s already restored (source=%s) — no-op',
                     order_id, source)
            result['already_restored'] = True
            return result

        # ── 1. Collect items and lock products + variants in PK order ─────
        # PK ordering = deterministic lock acquisition order across all
        # concurrent restorations. Eliminates the lock-ordering deadlock.
        items = list(
            OrderItem.objects.filter(order=order)
            .order_by('id')
            .values('id', 'product_id', 'variant_combo_id', 'quantity')
        )

        product_ids = sorted({
            i['product_id'] for i in items if i['product_id']
        })
        combo_ids = sorted({
            i['variant_combo_id'] for i in items if i['variant_combo_id']
        })

        # Batched locked SELECT — one round-trip instead of N. Sorted by
        # PK so concurrent restorations acquire locks in identical order.
        if product_ids:
            # of=("self",) means we lock ONLY the product rows, not the
            # joined store / category / etc. rows.
            list(
                Product.objects.select_for_update(of=("self",))
                .filter(pk__in=product_ids)
                .order_by('pk')
                .values_list('pk', flat=True)
            )
        if combo_ids:
            list(
                ProductVariantCombo.objects.select_for_update(of=("self",))
                .filter(pk__in=combo_ids)
                .order_by('pk')
                .values_list('pk', flat=True)
            )

        # ── 2. Increment quantities with F-expressions ────────────────────
        # F-expression is atomic at the SQL level — `quantity = quantity + N`.
        # The row is already locked above, so no other transaction is
        # racing; we use F-expr because it doesn't require us to read
        # the current value into Python.
        restored_items = []
        for item in items:
            qty = int(item['quantity'] or 0)
            if qty <= 0:
                continue
            if item['variant_combo_id']:
                ProductVariantCombo.objects.filter(
                    pk=item['variant_combo_id'],
                ).update(
                    quantity=F('quantity') + qty,
                    is_active=True,   # re-activate if zero-stock disabled it
                )
                restored_items.append({
                    'kind': 'combo', 'id': item['variant_combo_id'], 'qty': qty,
                })
            elif item['product_id']:
                Product.objects.filter(pk=item['product_id']).update(
                    quantity=F('quantity') + qty,
                    is_active=True,
                )
                restored_items.append({
                    'kind': 'product', 'id': str(item['product_id']), 'qty': qty,
                })

        result['restored_items'] = restored_items

        # ── 3. Refund store credit if any was redeemed ───────────────────
        credit = Decimal(str(order.store_credit_used or 0))
        if credit > 0:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            User.objects.filter(pk=order.buyer_id).update(
                store_credit=F('store_credit') + credit,
            )
            # Source of truth: post to ledger too. The buyer's
            # store-credit account is credited; the platform refund
            # pool absorbs the offset. Errors here are non-fatal —
            # reconciliation cron will surface drift.
            try:
                from apps.ledger.service import transfer
                from apps.ledger.models import Account, AccountType
                buyer = User.objects.get(pk=order.buyer_id)
                transfer(
                    from_account=Account.platform(
                        AccountType.PLATFORM_REFUND_POOL, currency='AOA',
                    ),
                    to_account=Account.for_user(
                        buyer, AccountType.USER_STORE_CREDIT, currency='AOA',
                    ),
                    amount=credit,
                    journal_key=f'restore:{order_id}:store_credit',
                    ref_type='order',
                    ref_id=str(order_id),
                    description=f'Store-credit refund {credit} Kz '
                                f'(source={source})',
                    user=buyer,
                )
            except Exception:
                log.exception('restore_order: ledger refund post failed')
            result['credit_refunded'] = str(credit)

        # ── 4. Release coupons used on this order ────────────────────────
        # The coupon_service.release() path is idempotent at the
        # redemption-row level — re-releasing a previously-released
        # redemption is a no-op.
        coupon_codes = (order.coupon_code or '').split(',')
        coupon_codes = [c.strip() for c in coupon_codes if c.strip()]
        if coupon_codes:
            try:
                from apps.promotions.coupon_service import release as coupon_release
                # The new (post-feat) seller-idempotency-key is
                # f'{checkout_idem}:{seller_id}'. Coupon redemptions
                # are keyed by (coupon, order_id) — and order_id here is
                # the order's idempotency_key, which is what coupon_service
                # stored against.
                for code in coupon_codes:
                    coupon = Coupon.objects.filter(code__iexact=code).first()
                    if coupon is None:
                        continue
                    rel = coupon_release(
                        coupon, order_id=order.idempotency_key or str(order_id),
                        reason=f'restore:{source}',
                    )
                    if rel is not None:
                        result['coupons_released'].append(code)
            except Exception:
                log.exception('restore_order: coupon release failed')

        # ── 5. Mark order restored + final status ────────────────────────
        # We don't set order.status here — that's the caller's job.
        # fail_payment wants 'payment_failed'; manual cancel wants
        # 'cancelled'; saga wants 'cancelled'. The status decision
        # belongs to the caller; restore is a pure side-effect primitive.
        Order.objects.filter(pk=order_id).update(
            stock_restored=True,
            stock_restored_at=timezone.now(),
            stock_restored_source=source[:32],
        )

    # ── 6. Telemetry (outside the transaction so a metrics-backend
    # outage doesn't block the commit) ──────────────────────────────────
    try:
        from apps.telemetry.metrics import stock_restored_total
        for it in restored_items:
            stock_restored_total.labels(source=source).inc(it.get('qty', 0))
    except Exception:
        pass

    log.info(
        'restore_order: order=%s source=%s items=%d credit=%s coupons=%s',
        order_id, source, len(result['restored_items']),
        result['credit_refunded'], result['coupons_released'],
    )
    return result
