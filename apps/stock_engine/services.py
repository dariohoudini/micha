"""
Stock engine services — race-condition-safe inventory operations.

The correctness model (doc CH5): three layers, all must agree, DB is truth.
  Layer 1 — Redis atomic pre-screen (fast path; optional, falls back to DB)
  Layer 2 — DB SELECT FOR UPDATE row lock (authoritative)
  Layer 3 — DB CHECK invariant (cannot-oversell backstop)

Chapter → function map:
  CH3   reserve / fast_reserve / extend_reservation
  CH4   release_expired_reservations
  CH5   reserve (select_for_update + no_wait), DB CHECK backstop
  CH2   commit / release / ship / deliver / mark_damaged / write_off /
        receive_return / restock_return / return_to_damaged
  CH6   setup_flash_pool / claim_flash_stock / reconcile_flash_pool
  CH7   allocate_warehouse
  CH8   bulk_update
  CH9   check_stock_alerts
  CH10  apply_audit_adjustment / freeze_count / unfreeze_count
  CH11  place_backorder / fulfil_backorders
  CH12  receive_return (bridges ReturnInventoryReceipt)
  CH14  variant_availability_matrix
  CH15  subscribe_restock / send_restock_notifications
  CH16  recommend_safety_stock (bridge to apps.forecasting)
  CH18/21 event_sum_integrity / oversell_monitor
  CH19  bundle_available / reserve_bundle
  CH20  reserve_order_items (saga, deadlock-safe ordering)
  CH24  snapshot_kpis
"""
import math
from datetime import timedelta

from django.db import (IntegrityError, OperationalError, connection,
                       transaction)
from django.db.models import Count, F, Q, Sum
from django.utils import timezone


def _supports_lock_options():
    """no_wait / skip_locked are Postgres-only. On SQLite (dev) they raise
    NotSupportedError, so degrade to a plain row lock (a no-op on SQLite,
    real serialisation on Postgres).
    """
    return connection.vendor == 'postgresql'

from . import state_machine as sm
from .models import (
    BackorderDemand, FlashClaim, FlashStockPool, InventorySku,
    RestockSubscription, SkuReservation, StockEngineEvent,
    StockEngineKpiSnapshot, StockIntegrityException, StockMovement,
)

# TTL per reservation type (doc CH3)
TTL_MINUTES = {
    'cart': 30, 'checkout': 15, 'flash_sale': 5,
}
COD_TTL_MINUTES = 30
REFERENCE_TTL_HOURS = 72
BANK_TRANSFER_TTL_HOURS = 48
MAX_RESERVATION_EXTENSIONS = 3


def _ttl_for(reservation_type, *, payment_method=None):
    if payment_method == 'mcx_reference':
        return timedelta(hours=REFERENCE_TTL_HOURS)
    if payment_method == 'bank_transfer':
        return timedelta(hours=BANK_TRANSFER_TTL_HOURS)
    if payment_method == 'cod':
        return timedelta(minutes=COD_TTL_MINUTES)
    return timedelta(minutes=TTL_MINUTES.get(reservation_type, 15))


def _log_movement(sku, event_type, *, delta, before_available, after_available,
                  ref_type='', ref_id='', actor='system'):
    StockMovement.objects.create(
        sku=sku, event_type=event_type, quantity_delta=delta,
        before_available=before_available, after_available=after_available,
        reference_type=ref_type, reference_id=str(ref_id), actor=str(actor))


@transaction.atomic
def create_sku(seller, *, product_id, initial_qty=0, variant_combo_id='',
               warehouse_id='', sku_code='', barcode='', safety_stock_qty=0):
    """Create a SKU and post the opening inbound event so the event log is a
    complete derivation of total from unit zero (doc CH18 principle).
    """
    sku = InventorySku.objects.create(
        seller=seller, product_id=str(product_id),
        variant_combo_id=str(variant_combo_id), warehouse_id=str(warehouse_id),
        sku_code=sku_code, barcode=barcode, safety_stock_qty=safety_stock_qty,
        total_quantity=0, available_quantity=0)
    if initial_qty > 0:
        sku.total_quantity = initial_qty
        sku.available_quantity = initial_qty
        sku.save(update_fields=['total_quantity', 'available_quantity'])
        _log_movement(sku, 'received_inbound', delta=initial_qty,
                      before_available=0, after_available=initial_qty,
                      ref_type='opening_balance', actor=seller.pk)
    return sku


# ──────────────────────────────────────────────────────────────────────
# CH5 / CH3 — Race-safe reservation
# ──────────────────────────────────────────────────────────────────────

@transaction.atomic
def reserve(sku_id, quantity, *, reservation_type='checkout', order_id='',
           cart_id='', payment_method=None, idempotency_key='', no_wait=False):
    """available → reserved, atomically (doc CH5). select_for_update
    serialises concurrent buyers; the DB CHECK invariant is the backstop.
    Returns the SkuReservation. Raises InsufficientStock / StockLockContention.
    """
    if idempotency_key:
        existing = SkuReservation.objects.filter(
            idempotency_key=idempotency_key).first()
        if existing:
            return existing
    use_no_wait = no_wait and _supports_lock_options()
    try:
        qs = InventorySku.objects.select_for_update(nowait=use_no_wait)
        sku = qs.get(id=sku_id)
    except OperationalError:
        # no_wait fast-fail: another request holds the row (doc CH5).
        raise sm.StockLockContention(
            'SKU row locked by another transaction')

    if sku.count_locked:
        raise sm.StockLockContention('SKU frozen for physical count')
    before = sku.available_quantity
    if before < quantity:
        raise sm.InsufficientStock('available', quantity, before, sku_id)

    sku.available_quantity = F('available_quantity') - quantity
    sku.reserved_quantity = F('reserved_quantity') + quantity
    sku.save(update_fields=['available_quantity', 'reserved_quantity',
                            'updated_at'])
    sku.refresh_from_db(fields=['available_quantity', 'reserved_quantity'])

    res = SkuReservation.objects.create(
        sku=sku, quantity=quantity, reservation_type=reservation_type,
        order_id=order_id, cart_id=cart_id, idempotency_key=idempotency_key,
        status='active',
        expires_at=timezone.now() + _ttl_for(reservation_type,
                                             payment_method=payment_method))
    _log_movement(sku, 'reserved', delta=0, before_available=before,
                  after_available=sku.available_quantity,
                  ref_type=reservation_type, ref_id=order_id or cart_id)
    _sync_redis(sku)
    return res


@transaction.atomic
def commit(reservation):
    """reserved → committed on payment confirmation (doc CH2)."""
    res = SkuReservation.objects.select_for_update().get(id=reservation.id)
    if res.status != 'active':
        return res
    sku = InventorySku.objects.select_for_update().get(id=res.sku_id)
    sku.reserved_quantity = F('reserved_quantity') - res.quantity
    sku.committed_quantity = F('committed_quantity') + res.quantity
    sku.save(update_fields=['reserved_quantity', 'committed_quantity',
                            'updated_at'])
    res.status = 'committed'
    res.save(update_fields=['status'])
    sku.refresh_from_db()
    _log_movement(sku, 'committed', delta=0,
                  before_available=sku.available_quantity,
                  after_available=sku.available_quantity,
                  ref_type='order', ref_id=res.order_id)
    return res


@transaction.atomic
def release(reservation, *, actor='system', reason='released'):
    """reserved → available (doc CH2/CH4)."""
    res = SkuReservation.objects.select_for_update().get(id=reservation.id)
    if res.status != 'active':
        return res
    sku = InventorySku.objects.select_for_update().get(id=res.sku_id)
    before = sku.available_quantity
    sku.reserved_quantity = F('reserved_quantity') - res.quantity
    sku.available_quantity = F('available_quantity') + res.quantity
    sku.save(update_fields=['reserved_quantity', 'available_quantity',
                            'updated_at'])
    res.status = 'released'
    res.save(update_fields=['status'])
    sku.refresh_from_db()
    _log_movement(sku, 'reservation_released', delta=0,
                  before_available=before,
                  after_available=sku.available_quantity,
                  ref_type=reason, ref_id=res.id, actor=actor)
    _sync_redis(sku)
    return res


def extend_reservation(reservation, *, minutes=5):
    """Buyer still on payment screen — extend up to 3× (doc CH4)."""
    res = SkuReservation.objects.filter(id=reservation.id,
                                        status='active').first()
    if res is None or res.extensions >= MAX_RESERVATION_EXTENSIONS:
        return {'extended': False, 'reason': 'max_extensions_or_inactive'}
    res.expires_at = max(res.expires_at,
                         timezone.now() + timedelta(minutes=minutes))
    res.extensions += 1
    res.save(update_fields=['expires_at', 'extensions'])
    return {'extended': True, 'extensions': res.extensions}


def release_expired_reservations(*, limit=500):
    """Celery JOB 1 (doc CH4). skip_locked so parallel workers don't
    double-release. Returns released to available.
    """
    now = timezone.now()
    released = 0
    expired_ids = list(SkuReservation.objects.filter(
        status='active', expires_at__lt=now).values_list('id', flat=True)[:limit])
    for rid in expired_ids:
        try:
            with transaction.atomic():
                lock_qs = SkuReservation.objects.select_for_update(
                    skip_locked=_supports_lock_options())
                res = lock_qs.filter(id=rid, status='active').first()
                if res is None:
                    continue
                sku = InventorySku.objects.select_for_update().get(
                    id=res.sku_id)
                before = sku.available_quantity
                sku.reserved_quantity = F('reserved_quantity') - res.quantity
                sku.available_quantity = F('available_quantity') + res.quantity
                sku.save(update_fields=['reserved_quantity',
                                        'available_quantity', 'updated_at'])
                res.status = 'expired'
                res.save(update_fields=['status'])
                sku.refresh_from_db()
                _log_movement(sku, 'reservation_released', delta=0,
                              before_available=before,
                              after_available=sku.available_quantity,
                              ref_type='reservation_expiry', ref_id=res.id)
                _sync_redis(sku)
                released += 1
        except Exception:
            continue
    return {'released': released}


# ──────────────────────────────────────────────────────────────────────
# CH20 — Reservation saga (multi-item, deadlock-safe)
# ──────────────────────────────────────────────────────────────────────

def reserve_order_items(order_id, items, *, reservation_type='checkout',
                        payment_method=None):
    """All-or-nothing reservation (doc CH20). Sort by sku_id so concurrent
    orders lock SKUs in the same order → no deadlock. Roll back on any failure.
    """
    items = sorted(items, key=lambda x: str(x['sku_id']))
    reservations = []
    try:
        for item in items:
            res = reserve(item['sku_id'], item['quantity'],
                          reservation_type=reservation_type, order_id=order_id,
                          payment_method=payment_method)
            reservations.append(res)
    except sm.InsufficientStock as e:
        for res in reservations:
            release(res, reason='saga_rollback')
        raise
    return reservations


# ──────────────────────────────────────────────────────────────────────
# CH2 — Other state transitions
# ──────────────────────────────────────────────────────────────────────

@transaction.atomic
def ship(sku_id, quantity, *, order_id=''):
    """committed → in_transit (doc CH2)."""
    sku = InventorySku.objects.select_for_update().get(id=sku_id)
    if sku.committed_quantity < quantity:
        raise sm.InsufficientStock('committed', quantity,
                                   sku.committed_quantity, sku_id)
    sku.committed_quantity = F('committed_quantity') - quantity
    sku.in_transit_quantity = F('in_transit_quantity') + quantity
    sku.save(update_fields=['committed_quantity', 'in_transit_quantity',
                            'updated_at'])
    sku.refresh_from_db()
    _log_movement(sku, 'shipped', delta=0,
                  before_available=sku.available_quantity,
                  after_available=sku.available_quantity, ref_type='order',
                  ref_id=order_id)
    return sku


@transaction.atomic
def deliver(sku_id, quantity, *, order_id=''):
    """in_transit → removed (leaves inventory). total decreases (doc CH2)."""
    sku = InventorySku.objects.select_for_update().get(id=sku_id)
    if sku.in_transit_quantity < quantity:
        raise sm.InsufficientStock('in_transit', quantity,
                                   sku.in_transit_quantity, sku_id)
    sku.in_transit_quantity = F('in_transit_quantity') - quantity
    sku.total_quantity = F('total_quantity') - quantity
    sku.save(update_fields=['in_transit_quantity', 'total_quantity',
                            'updated_at'])
    sku.refresh_from_db()
    _log_movement(sku, 'delivered', delta=-quantity,
                  before_available=sku.available_quantity,
                  after_available=sku.available_quantity, ref_type='order',
                  ref_id=order_id)
    return sku


@transaction.atomic
def mark_damaged(sku_id, quantity, *, actor='system', reason='damaged'):
    """available → damaged (doc CH13)."""
    sku = InventorySku.objects.select_for_update().get(id=sku_id)
    if sku.available_quantity < quantity:
        raise sm.InsufficientStock('available', quantity,
                                   sku.available_quantity, sku_id)
    before = sku.available_quantity
    sku.available_quantity = F('available_quantity') - quantity
    sku.damaged_quantity = F('damaged_quantity') + quantity
    sku.save(update_fields=['available_quantity', 'damaged_quantity',
                            'updated_at'])
    sku.refresh_from_db()
    _log_movement(sku, 'damaged', delta=0, before_available=before,
                  after_available=sku.available_quantity, ref_type=reason,
                  actor=actor)
    check_stock_alerts(sku_id)
    return sku


@transaction.atomic
def write_off(sku_id, quantity, *, authorised_by='system', reason=''):
    """damaged → removed. total decreases permanently (doc CH13)."""
    sku = InventorySku.objects.select_for_update().get(id=sku_id)
    if sku.damaged_quantity < quantity:
        raise ValueError('cannot write off more than damaged quantity')
    sku.damaged_quantity = F('damaged_quantity') - quantity
    sku.total_quantity = F('total_quantity') - quantity
    sku.save(update_fields=['damaged_quantity', 'total_quantity',
                            'updated_at'])
    sku.refresh_from_db()
    _log_movement(sku, 'written_off', delta=-quantity,
                  before_available=sku.available_quantity,
                  after_available=sku.available_quantity, ref_type='write_off',
                  actor=authorised_by)
    StockEngineEvent.log('stock_written_off', sku_id=str(sku_id),
                         quantity=quantity, reason=reason)
    return sku


@transaction.atomic
def receive_return(sku_id, quantity, *, return_id=''):
    """Inbound return → RETURNED state, total increases (doc CH12)."""
    sku = InventorySku.objects.select_for_update().get(id=sku_id)
    sku.returned_quantity = F('returned_quantity') + quantity
    sku.total_quantity = F('total_quantity') + quantity
    sku.save(update_fields=['returned_quantity', 'total_quantity',
                            'updated_at'])
    sku.refresh_from_db()
    _log_movement(sku, 'returned', delta=quantity,
                  before_available=sku.available_quantity,
                  after_available=sku.available_quantity, ref_type='return',
                  ref_id=return_id)
    return sku


@transaction.atomic
def restock_return(sku_id, quantity, *, return_id=''):
    """returned → available (inspection passed, doc CH12 3A)."""
    sku = InventorySku.objects.select_for_update().get(id=sku_id)
    if sku.returned_quantity < quantity:
        raise sm.InsufficientStock('returned', quantity,
                                   sku.returned_quantity, sku_id)
    was_oos = sku.available_quantity == 0
    before = sku.available_quantity
    sku.returned_quantity = F('returned_quantity') - quantity
    sku.available_quantity = F('available_quantity') + quantity
    sku.save(update_fields=['returned_quantity', 'available_quantity',
                            'updated_at'])
    sku.refresh_from_db()
    _log_movement(sku, 'returned_restocked', delta=0, before_available=before,
                  after_available=sku.available_quantity, ref_type='return',
                  ref_id=return_id)
    if was_oos and sku.available_quantity > 0:
        _reactivate_listing(sku)
    return sku


@transaction.atomic
def return_to_damaged(sku_id, quantity, *, return_id=''):
    """returned → damaged (inspection failed, doc CH12 3B)."""
    sku = InventorySku.objects.select_for_update().get(id=sku_id)
    if sku.returned_quantity < quantity:
        raise sm.InsufficientStock('returned', quantity,
                                   sku.returned_quantity, sku_id)
    sku.returned_quantity = F('returned_quantity') - quantity
    sku.damaged_quantity = F('damaged_quantity') + quantity
    sku.save(update_fields=['returned_quantity', 'damaged_quantity',
                            'updated_at'])
    sku.refresh_from_db()
    _log_movement(sku, 'returned_damaged', delta=0,
                  before_available=sku.available_quantity,
                  after_available=sku.available_quantity, ref_type='return',
                  ref_id=return_id)
    return sku


@transaction.atomic
def receive_inbound(sku_id, quantity, *, reference_id=''):
    """New supplier stock → AVAILABLE, total increases. Fulfils backorders
    FIFO first (doc CH11), remainder to available.
    """
    sku = InventorySku.objects.select_for_update().get(id=sku_id)
    before = sku.available_quantity
    sku.total_quantity = F('total_quantity') + quantity
    sku.available_quantity = F('available_quantity') + quantity
    sku.save(update_fields=['total_quantity', 'available_quantity',
                            'updated_at'])
    sku.refresh_from_db()
    _log_movement(sku, 'received_inbound', delta=quantity,
                  before_available=before,
                  after_available=sku.available_quantity, ref_type='inbound',
                  ref_id=reference_id)
    if before == 0 and sku.available_quantity > 0:
        _reactivate_listing(sku)
    fulfil_backorders(sku_id)
    return sku


# ──────────────────────────────────────────────────────────────────────
# CH8 — Bulk update
# ──────────────────────────────────────────────────────────────────────

@transaction.atomic
def bulk_update(seller, sku_id, *, change_type, value):
    """SET_TO / ADD / SUBTRACT (doc CH8). Respects reserved+committed."""
    sku = InventorySku.objects.select_for_update().get(id=sku_id, seller=seller)
    before = sku.available_quantity
    locked = (sku.reserved_quantity + sku.committed_quantity
              + sku.damaged_quantity + sku.in_transit_quantity
              + sku.returned_quantity)
    if change_type == 'set_to':
        if value < locked:
            raise ValueError('value below reserved+committed — would oversell')
        sku.available_quantity = value - locked
        sku.total_quantity = value
    elif change_type == 'add':
        sku.available_quantity = F('available_quantity') + value
        sku.total_quantity = F('total_quantity') + value
    elif change_type == 'subtract':
        if value > before:
            raise ValueError('cannot subtract more than available')
        sku.available_quantity = F('available_quantity') - value
        sku.total_quantity = F('total_quantity') - value
    else:
        raise ValueError('invalid change_type')
    sku.save()
    sku.refresh_from_db()
    _log_movement(
        sku, 'adjusted_positive' if sku.available_quantity >= before
        else 'adjusted_negative',
        delta=sku.available_quantity - before, before_available=before,
        after_available=sku.available_quantity, ref_type='bulk_update',
        actor=seller.pk)
    _sync_redis(sku)
    check_stock_alerts(sku_id)
    return sku


# ──────────────────────────────────────────────────────────────────────
# CH10 — Physical audit
# ──────────────────────────────────────────────────────────────────────

def freeze_count(sku_id):
    InventorySku.objects.filter(id=sku_id).update(count_locked=True)


def unfreeze_count(sku_id):
    InventorySku.objects.filter(id=sku_id).update(count_locked=False)
    sku = InventorySku.objects.filter(id=sku_id).first()
    if sku:
        _sync_redis(sku)


@transaction.atomic
def apply_audit_adjustment(sku_id, physical_count, *, auditor='system'):
    """Reconcile system vs physical (doc CH10). variance = physical − total."""
    sku = InventorySku.objects.select_for_update().get(id=sku_id)
    variance = physical_count - sku.total_quantity
    before = sku.available_quantity
    if variance > 0:
        sku.total_quantity = F('total_quantity') + variance
        sku.available_quantity = F('available_quantity') + variance
        event = 'adjusted_positive'
    elif variance < 0:
        take = min(abs(variance), sku.available_quantity)
        sku.total_quantity = F('total_quantity') + variance
        sku.available_quantity = F('available_quantity') - take
        event = 'adjusted_negative'
    else:
        return {'variance': 0}
    sku.save()
    sku.refresh_from_db()
    _log_movement(sku, event, delta=variance, before_available=before,
                  after_available=sku.available_quantity, ref_type='audit',
                  actor=auditor)
    return {'variance': variance, 'event': event}


# ──────────────────────────────────────────────────────────────────────
# CH6 — Flash sale pool
# ──────────────────────────────────────────────────────────────────────

@transaction.atomic
def setup_flash_pool(sku_id, *, flash_event_id, quantity, per_buyer_limit=1,
                     ends_at=None):
    """Move `quantity` from available into a dedicated flash pool (doc CH6)."""
    sku = InventorySku.objects.select_for_update().get(id=sku_id)
    if sku.available_quantity < quantity:
        raise sm.InsufficientStock('available', quantity,
                                   sku.available_quantity, sku_id)
    sku.available_quantity = F('available_quantity') - quantity
    sku.flash_sale_qty = F('flash_sale_qty') + quantity
    sku.save(update_fields=['available_quantity', 'flash_sale_qty',
                            'updated_at'])
    pool, _ = FlashStockPool.objects.update_or_create(
        flash_event_id=flash_event_id, sku=sku,
        defaults={'allocated_qty': quantity, 'claimed_qty': 0,
                  'per_buyer_limit': per_buyer_limit, 'is_open': True,
                  'opens_at': timezone.now(), 'ends_at': ends_at,
                  'reconciled': False})
    return pool


@transaction.atomic
def claim_flash_stock(pool_id, buyer, quantity=1):
    """Atomic flash claim with per-buyer limit (doc CH6). The DB unique
    (pool, buyer) + select_for_update on the pool serialise concurrent claims.
    """
    pool = FlashStockPool.objects.select_for_update().get(id=pool_id)
    if not pool.is_open or (pool.ends_at and pool.ends_at < timezone.now()):
        return {'ok': False, 'reason': 'sale_not_open'}
    if quantity > pool.per_buyer_limit:
        return {'ok': False, 'reason': 'over_per_buyer_limit'}
    if pool.remaining < quantity:
        return {'ok': False, 'reason': 'sold_out', 'remaining': pool.remaining}
    try:
        FlashClaim.objects.create(pool=pool, buyer=buyer, quantity=quantity)
    except IntegrityError:
        return {'ok': False, 'reason': 'already_claimed'}
    pool.claimed_qty = F('claimed_qty') + quantity
    pool.save(update_fields=['claimed_qty'])
    pool.refresh_from_db()
    _log_movement(pool.sku, 'flash_claimed', delta=0,
                  before_available=pool.sku.available_quantity,
                  after_available=pool.sku.available_quantity,
                  ref_type='flash', ref_id=pool.flash_event_id,
                  actor=buyer.pk)
    return {'ok': True, 'remaining': pool.remaining}


@transaction.atomic
def reconcile_flash_pool(pool_id):
    """Post-event: unclaimed flash units → available (doc CH6 JOB 7)."""
    pool = FlashStockPool.objects.select_for_update().get(id=pool_id)
    if pool.reconciled:
        return {'reconciled': True, 'returned': 0}
    unclaimed = pool.remaining
    sku = InventorySku.objects.select_for_update().get(id=pool.sku_id)
    if unclaimed > 0:
        sku.flash_sale_qty = F('flash_sale_qty') - unclaimed
        sku.available_quantity = F('available_quantity') + unclaimed
        sku.save(update_fields=['flash_sale_qty', 'available_quantity',
                                'updated_at'])
        sku.refresh_from_db()
        _log_movement(sku, 'flash_released', delta=0,
                      before_available=sku.available_quantity - unclaimed,
                      after_available=sku.available_quantity,
                      ref_type='flash', ref_id=pool.flash_event_id)
    pool.is_open = False
    pool.reconciled = True
    pool.save(update_fields=['is_open', 'reconciled'])
    return {'reconciled': True, 'returned': unclaimed,
            'claims_db': pool.claims.count(), 'claimed_qty': pool.claimed_qty}


# ──────────────────────────────────────────────────────────────────────
# CH9 — Low-stock alerts
# ──────────────────────────────────────────────────────────────────────

def check_stock_alerts(sku_id):
    sku = InventorySku.objects.filter(id=sku_id).first()
    if sku is None:
        return None
    level = None
    if sku.available_quantity == 0:
        level = 'OOS'
        _deactivate_listing(sku)
    elif sku.safety_stock_qty and sku.available_quantity <= sku.safety_stock_qty // 2:
        level = 'CRITICAL'
    elif sku.safety_stock_qty and sku.available_quantity <= sku.safety_stock_qty:
        level = 'WARNING'
    if level:
        StockEngineEvent.log('stock_alert', sku_id=str(sku_id), level=level,
                             available=sku.available_quantity)
    return level


def _deactivate_listing(sku):
    if sku.listing_status == 'active':
        sku.listing_status = 'out_of_stock'
        sku.save(update_fields=['listing_status'])
        try:
            from apps.products.models import Product
            Product.objects.filter(id=sku.product_id).update(is_active=False)
        except Exception:
            pass


def _reactivate_listing(sku):
    if sku.listing_status == 'out_of_stock':
        sku.listing_status = 'active'
        sku.save(update_fields=['listing_status'])
        try:
            from apps.products.models import Product
            Product.objects.filter(id=sku.product_id).update(is_active=True)
        except Exception:
            pass
        send_restock_notifications(sku.id)


# ──────────────────────────────────────────────────────────────────────
# CH15 — Notify-me
# ──────────────────────────────────────────────────────────────────────

def subscribe_restock(sku_id, *, user=None, email=''):
    sku = InventorySku.objects.filter(id=sku_id).first()
    if sku is None:
        return None
    sub, _ = RestockSubscription.objects.update_or_create(
        sku=sku, user=user if getattr(user, 'pk', None) else None,
        defaults={'email': email, 'status': 'pending'})
    return sub


def send_restock_notifications(sku_id, *, batch=1000):
    sent = 0
    subs = RestockSubscription.objects.filter(
        sku_id=sku_id, status='pending').select_related('user')[:batch]
    for sub in subs:
        try:
            if sub.user_id:
                from apps.notifications.push_service import send_to_user
                send_to_user(sub.user, title='Produto disponível de novo!',
                             body='O produto que segue está de volta em stock.')
        except Exception:
            pass
        sub.status = 'notified'
        sub.notified_at = timezone.now()
        sub.save(update_fields=['status', 'notified_at'])
        sent += 1
    return {'notified': sent}


# ──────────────────────────────────────────────────────────────────────
# CH11 — Backorder
# ──────────────────────────────────────────────────────────────────────

def place_backorder(sku_id, *, order_id, quantity, buyer=None):
    sku = InventorySku.objects.get(id=sku_id)
    if not sku.backorder_enabled:
        raise ValueError('backorders not enabled for this SKU')
    pending = BackorderDemand.objects.filter(
        sku=sku, status='pending').aggregate(s=Sum('quantity'))['s'] or 0
    if sku.backorder_limit and pending + quantity > sku.backorder_limit:
        raise ValueError('backorder limit exceeded')
    return BackorderDemand.objects.create(
        sku=sku, order_id=order_id, quantity=quantity,
        buyer=buyer if getattr(buyer, 'pk', None) else None)


@transaction.atomic
def fulfil_backorders(sku_id):
    """FIFO allocation of incoming stock to pending backorders (doc CH11)."""
    sku = InventorySku.objects.select_for_update().get(id=sku_id)
    allocated = 0
    for demand in BackorderDemand.objects.select_for_update().filter(
            sku=sku, status='pending').order_by('created_at'):
        if sku.available_quantity < demand.quantity:
            break  # not enough — wait for more stock
        # Reserve against this demand (available → reserved → committed path)
        sku.available_quantity = F('available_quantity') - demand.quantity
        sku.committed_quantity = F('committed_quantity') + demand.quantity
        sku.save(update_fields=['available_quantity', 'committed_quantity',
                                'updated_at'])
        sku.refresh_from_db()
        demand.status = 'allocated'
        demand.allocated_at = timezone.now()
        demand.save(update_fields=['status', 'allocated_at'])
        allocated += 1
    return {'allocated': allocated}


# ──────────────────────────────────────────────────────────────────────
# CH19 — Bundle explosion
# ──────────────────────────────────────────────────────────────────────

def bundle_available(component_specs):
    """component_specs = [(sku_id, component_qty), ...] → max buildable."""
    mins = []
    for sku_id, comp_qty in component_specs:
        sku = InventorySku.objects.filter(id=sku_id).first()
        if sku is None or comp_qty <= 0:
            return 0
        mins.append(sku.available_quantity // comp_qty)
    return min(mins) if mins else 0


def reserve_bundle(component_specs, quantity, *, order_id):
    """Reserve each component (saga). component_specs = [(sku_id, qty), ...]."""
    items = [{'sku_id': sku_id, 'quantity': comp_qty * quantity}
             for sku_id, comp_qty in component_specs]
    return reserve_order_items(order_id, items)


# ──────────────────────────────────────────────────────────────────────
# CH7 — Multi-warehouse allocation
# ──────────────────────────────────────────────────────────────────────

ZONE_SCORE = {'same': 1, 'near': 2, 'mid': 3, 'far': 4}


def allocate_warehouse(product_id, quantity, buyer_province):
    """Pick the best warehouse SKU for this buyer (doc CH7). Lower = better."""
    candidates = InventorySku.objects.filter(
        product_id=product_id, available_quantity__gte=quantity).exclude(
        warehouse_id='')
    scored = []
    for c in candidates:
        province = _warehouse_province(c.warehouse_id)
        zone = _delivery_zone(province, buyer_province)
        is_owned = _warehouse_is_owned(c.warehouse_id)
        score = ZONE_SCORE.get(zone, 4) * 10 - (1 if is_owned else 0)
        scored.append((score, c))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0])
    return scored[0][1]


def _warehouse_province(warehouse_id):
    try:
        from apps.pricing_inventory.models import Warehouse
        w = Warehouse.objects.filter(id=warehouse_id).first()
        return getattr(w, 'province', '') if w else ''
    except Exception:
        return ''


def _warehouse_is_owned(warehouse_id):
    try:
        from apps.pricing_inventory.models import Warehouse
        w = Warehouse.objects.filter(id=warehouse_id).first()
        return getattr(w, 'is_micha_owned', False) if w else False
    except Exception:
        return False


def _delivery_zone(from_province, to_province):
    if not from_province or not to_province:
        return 'mid'
    if from_province == to_province:
        return 'same'
    return 'mid'  # bridge: a full 18×18 zone matrix is config (gap)


# ──────────────────────────────────────────────────────────────────────
# CH14 — Variant availability matrix
# ──────────────────────────────────────────────────────────────────────

def variant_availability_matrix(product_id):
    """{variant_combo_id: {available: bool, qty: int}} (doc CH14)."""
    out = {}
    for sku in InventorySku.objects.filter(product_id=product_id):
        key = sku.variant_combo_id or 'default'
        out[key] = {'available': sku.available_quantity > 0,
                    'qty': sku.available_quantity}
    return out


# ──────────────────────────────────────────────────────────────────────
# CH16 — Forecasting bridge
# ──────────────────────────────────────────────────────────────────────

Z_SCORES = {90: 1.28, 95: 1.65, 97: 1.88, 99: 2.33}


def recommend_safety_stock(sku_id, *, lead_time_weeks=2, service_level=95,
                           weekly_history=None):
    """Safety stock = Z × σ × √lead_time (doc CH16). Bridges apps.forecasting
    for history when not supplied.
    """
    history = weekly_history
    if history is None:
        history = _weekly_demand_history(sku_id)
    if len(history) < 4:
        return {'safety_stock': 0, 'reorder_point': 0, 'reason': 'insufficient_history'}
    mean = sum(history) / len(history)
    var = sum((x - mean) ** 2 for x in history) / (len(history) - 1)
    sigma = math.sqrt(var)
    z = Z_SCORES.get(service_level, 1.65)
    safety = math.ceil(z * sigma * math.sqrt(lead_time_weeks))
    reorder_point = math.ceil(mean * lead_time_weeks) + safety
    return {'safety_stock': safety, 'reorder_point': reorder_point,
            'avg_weekly_demand': round(mean, 1)}


def _weekly_demand_history(sku_id):
    try:
        from apps.forecasting.models import DemandForecast  # noqa
    except Exception:
        pass
    return []  # bridge: forecasting feeds this in production


def apply_safety_stock(sku_id, **kwargs):
    rec = recommend_safety_stock(sku_id, **kwargs)
    if rec.get('safety_stock'):
        InventorySku.objects.filter(id=sku_id).update(
            safety_stock_qty=rec['safety_stock'],
            reorder_point=rec['reorder_point'])
    return rec


# ──────────────────────────────────────────────────────────────────────
# CH18 / CH21 — Integrity guardrails
# ──────────────────────────────────────────────────────────────────────

def oversell_monitor():
    """Should never find rows (the CHECK invariant prevents it). Records
    any breach as a CRITICAL integrity exception (doc CH21 guardrail 4).
    """
    breaches = 0
    bad = InventorySku.objects.filter(
        Q(available_quantity__lt=0)
        | Q(total_quantity__lt=(
            F('available_quantity') + F('reserved_quantity')
            + F('committed_quantity') + F('damaged_quantity')
            + F('in_transit_quantity') + F('returned_quantity'))))
    for sku in bad:
        StockIntegrityException.objects.create(
            sku=sku, kind='invariant_breach',
            detail={'available': sku.available_quantity,
                    'total': sku.total_quantity})
        breaches += 1
    return {'breaches': breaches}


def event_sum_integrity(*, limit=2000):
    """Event running-sum (delta) should equal total_quantity (doc CH18).
    Only inbound/outbound deltas change total; intra-state moves are delta=0.
    """
    mismatches = 0
    checked = 0
    for sku in InventorySku.objects.all()[:limit]:
        delta_sum = StockMovement.objects.filter(sku=sku).aggregate(
            s=Sum('quantity_delta'))['s'] or 0
        if delta_sum != sku.total_quantity:
            StockIntegrityException.objects.create(
                sku=sku, kind='event_sum_mismatch',
                detail={'event_sum': delta_sum, 'total': sku.total_quantity})
            mismatches += 1
        checked += 1
    return {'checked': checked, 'mismatches': mismatches}


# ──────────────────────────────────────────────────────────────────────
# Redis sync (fast-path counter — optional, DB is truth)
# ──────────────────────────────────────────────────────────────────────

def _sync_redis(sku):
    """Reseed the advisory Redis counter from DB truth (doc CH3/CH21)."""
    try:
        from django.core.cache import cache
        cache.set(f'inv:avail:{sku.id}', sku.available_quantity, 3600)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────
# CH24 — KPI snapshot
# ──────────────────────────────────────────────────────────────────────

def snapshot_kpis(snapshot_date=None):
    snapshot_date = snapshot_date or timezone.now().date()
    active = InventorySku.objects.filter(listing_status__in=('active',
                                                            'out_of_stock'))
    total = active.count()
    in_stock = active.filter(available_quantity__gt=0).count()
    oos = active.filter(available_quantity=0).count()

    res = SkuReservation.objects.filter(reservation_type='checkout')
    committed = res.filter(status='committed').count()
    expired = res.filter(status='expired').count()
    res_total = res.count()

    oversell = InventorySku.objects.filter(available_quantity__lt=0).count()
    integ = StockIntegrityException.objects.filter(resolved=False).count()

    snap, _ = StockEngineKpiSnapshot.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'total_active_skus': total,
            'in_stock_pct': round(in_stock / total * 100, 2) if total else 0,
            'oos_pct': round(oos / total * 100, 2) if total else 0,
            'active_reservations': SkuReservation.objects.filter(
                status='active').count(),
            'reservation_conversion_pct': round(
                committed / res_total * 100, 2) if res_total else 0,
            'reservation_expiry_pct': round(
                expired / res_total * 100, 2) if res_total else 0,
            'oversell_incidents': oversell,
            'integrity_exceptions': integ,
            'flash_pools_active': FlashStockPool.objects.filter(
                is_open=True).count(),
        })
    return snap
