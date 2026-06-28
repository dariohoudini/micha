"""
Pricing & Inventory Intelligence — domain services.
"""
from __future__ import annotations

import logging
import math
from datetime import date as date_cls
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models as django_models
from django.db import transaction
from django.utils import timezone

from .models import (
    BackorderConfig, BackorderRequest, CompetitorObservation,
    DropshipMapping, DropshipOrder, DropshipSupplier,
    DynamicPriceSignal, DynamicPricingConfig,
    HazmatClass, InventoryAuditEntry, InventoryAuditRun,
    InventorySyncJob, InventoryWebhook, OversizeSurchargeRule,
    PreOrderConfig, PreOrderReservation, PriceCap, PriceFloor,
    PriceHistory, PriceRule, PricingInventoryEvent,
    PricingInventoryKpiSnapshot, ProductHazmat,
    RegionalPriceAdjustment, ReturnInventoryReceipt, StockAlert,
    VirtualBundleInventory, Warehouse, WarehouseStock,
)

User = get_user_model()
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# CH1 — Price resolution chain
# ═══════════════════════════════════════════════════════════════════

# Layer priority for resolution. Higher = applied last (wins).  We
# walk in order, applying each layer's modification to the running
# price; a fixed-price layer (e.g. flash) replaces; a delta layer
# (promotional) reduces.
LAYER_RANK = {
    'base':            0,
    'seller_override': 1,
    'regional':        2,
    'experimental':    3,
    'promotional':     4,
    'personalised':    5,
}


def resolve_price(*, product_id: str, sku_id: str = '',
                   country: str = '', user=None) -> dict:
    """CH1.2 walk: base → seller_override → regional → experimental
    → promotional → personalised.

    Returns:
      {
        'final_price': Decimal,
        'currency': str,
        'layers_applied': [{'layer','rule_id','amount'}],
        'rule_id': UUID of the winning rule (the highest-priority one
          that set the final price),
      }
    """
    now = timezone.now()
    qs = PriceRule.objects.filter(
        product_id=product_id, status='active',
        valid_from__lte=now,
    ).filter(
        django_models.Q(valid_until__isnull=True) |
        django_models.Q(valid_until__gte=now)
    )
    if sku_id:
        qs = qs.filter(django_models.Q(sku_id=sku_id) | django_models.Q(sku_id=''))
    if country:
        qs = qs.filter(django_models.Q(country=country.upper()) | django_models.Q(country=''))
    rules = list(qs.order_by('priority_score').reverse())
    if not rules:
        return {'final_price': None, 'currency': '',
                'layers_applied': [], 'rule_id': None}

    # Bucket by layer.
    by_layer = {}
    for r in rules:
        by_layer.setdefault(r.layer, []).append(r)

    final = None
    currency = ''
    layers_applied = []
    winning_rule = None

    for layer in sorted(by_layer.keys(), key=lambda l: LAYER_RANK.get(l, 99)):
        # Pick highest priority rule within the layer.
        rule = by_layer[layer][0]
        if final is None:
            final = rule.price_amount
            currency = rule.currency
        elif layer == 'promotional':
            # Promotional uses discount_pct off the running price.
            if rule.discount_pct > 0:
                final = (final * (Decimal(100) - rule.discount_pct) / Decimal(100)).quantize(Decimal('0.01'))
            else:
                final = min(final, rule.price_amount)
        elif layer == 'regional':
            # Multiplied through regional adjustment lookup below.
            final = (final * Decimal(str(_regional_multiplier(
                country=country,
                product_id=product_id,
                category_id=rule.metadata.get('category_id', ''),
            )))).quantize(Decimal('0.01'))
        else:
            # All other layers replace the running price.
            final = rule.price_amount
            currency = rule.currency
        layers_applied.append({'layer': layer, 'rule_id': str(rule.id),
                               'amount': str(final)})
        winning_rule = rule

    # Enforce floor / cap.
    floor_val = _resolve_floor(product_id, country)
    cap_val = _resolve_cap(product_id, country)
    if floor_val and final < floor_val:
        final = floor_val
        layers_applied.append({'layer': 'floor_enforced', 'amount': str(final)})
    if cap_val and final > cap_val:
        final = cap_val
        layers_applied.append({'layer': 'cap_enforced', 'amount': str(final)})

    return {
        'final_price': final, 'currency': currency,
        'layers_applied': layers_applied,
        'rule_id': str(winning_rule.id) if winning_rule else None,
    }


def _regional_multiplier(*, country: str, product_id: str,
                         category_id: str = '') -> float:
    if not country:
        return 1.0
    now = timezone.now()
    qs = RegionalPriceAdjustment.objects.filter(
        country=country.upper(), is_active=True,
        valid_from__lte=now,
    ).filter(
        django_models.Q(valid_until__isnull=True) |
        django_models.Q(valid_until__gte=now)
    )
    # Most specific wins: product_id > category_id > country-only.
    prod_q = qs.filter(product_id=product_id).order_by('-id').first()
    if prod_q:
        return float(prod_q.multiplier)
    if category_id:
        cat_q = qs.filter(category_id=category_id, product_id='').order_by('-id').first()
        if cat_q:
            return float(cat_q.multiplier)
    cn_q = qs.filter(product_id='', category_id='').order_by('-id').first()
    if cn_q:
        return float(cn_q.multiplier)
    return 1.0


def _resolve_floor(product_id: str, country: str) -> Decimal | None:
    """Highest floor across product/category/country wins."""
    floors = PriceFloor.objects.filter(is_active=True).filter(
        django_models.Q(country=country.upper()) | django_models.Q(country='')
    )
    best = None
    for f in floors:
        candidate = f.abs_floor
        if candidate and (best is None or candidate > best):
            best = candidate
    return best


def _resolve_cap(product_id: str, country: str) -> Decimal | None:
    """Lowest cap wins (most restrictive)."""
    caps = PriceCap.objects.filter(is_active=True).filter(
        django_models.Q(country=country.upper()) | django_models.Q(country='')
    )
    best = None
    for c in caps:
        if c.cap_amount and (best is None or c.cap_amount < best):
            best = c.cap_amount
    return best


# ═══════════════════════════════════════════════════════════════════
# CH5 — Record price changes
# ═══════════════════════════════════════════════════════════════════

@transaction.atomic
def record_price_change(*, product_id: str, sku_id: str = '',
                         country: str = '', new_price: Decimal,
                         currency: str = 'AOA', source: str = '',
                         actor=None, rule: PriceRule = None,
                         metadata: dict = None) -> PriceHistory:
    prev = (
        PriceHistory.objects.filter(
            product_id=product_id, sku_id=sku_id, country=country.upper(),
        ).order_by('-recorded_at').first()
    )
    prev_price = prev.new_price if prev else None
    delta_pct = Decimal('0')
    if prev_price and prev_price > 0:
        delta_pct = ((new_price - prev_price) / prev_price * Decimal(100)).quantize(Decimal('0.01'))
    obj = PriceHistory.objects.create(
        product_id=product_id, sku_id=sku_id, country=country.upper(),
        previous_price=prev_price, new_price=new_price,
        currency=currency, delta_pct=delta_pct, source=source[:40],
        actor=actor, rule=rule, metadata=metadata or {},
    )
    PricingInventoryEvent.log(
        actor=actor, kind='price.changed', product_id=product_id,
        payload={'from': str(prev_price) if prev_price else None,
                 'to': str(new_price), 'delta_pct': str(delta_pct),
                 'source': source},
    )
    return obj


def was_price_30d(*, product_id: str, sku_id: str = '',
                   country: str = '') -> Decimal | None:
    """CH5.2 — the highest price seen in the last 30 days. Used by
    the "was price" reference for legal compliance."""
    cutoff = timezone.now() - timedelta(days=30)
    agg = PriceHistory.objects.filter(
        product_id=product_id, sku_id=sku_id,
        country=country.upper() if country else '',
        recorded_at__gte=cutoff,
    ).aggregate(m=django_models.Max('new_price'))
    return agg['m']


# ═══════════════════════════════════════════════════════════════════
# CH2 — Dynamic pricing engine
# ═══════════════════════════════════════════════════════════════════

def evaluate_dynamic_pricing(config: DynamicPricingConfig) -> dict:
    """CH2.5 — combine the active signals into a final recommended
    price. Each signal contributes a (price, strength) pair; we pick
    the strongest signal and clip into [min_price, max_price]."""
    candidates = []
    if config.use_time_signal:
        s = _time_signal(config)
        if s:
            candidates.append(s)
    if config.use_demand_signal:
        s = _demand_signal(config)
        if s:
            candidates.append(s)
    if config.use_competitor_signal:
        s = _competitor_signal(config)
        if s:
            candidates.append(s)
    if not candidates:
        return {'applied': False, 'reason': 'NO_SIGNALS'}

    candidates.sort(key=lambda c: c['strength'], reverse=True)
    pick = candidates[0]
    suggested = max(config.min_price, min(config.max_price, pick['price']))

    # Persist the signal for traceability.
    DynamicPriceSignal.objects.create(
        config=config, kind=pick['kind'],
        suggested_price=suggested, strength=pick['strength'],
        payload=pick.get('payload', {}),
    )
    # Write a PriceRule(layer=experimental) — the resolver picks it up
    # immediately for the next read.
    PriceRule.objects.create(
        layer='experimental', seller=config.seller,
        product_id=config.product_id, sku_id=config.sku_id,
        price_amount=suggested, currency='AOA',
        priority_score=60,
        valid_from=timezone.now(),
        valid_until=timezone.now() + timedelta(hours=6),
        source=f'dynamic_engine:{pick["kind"]}',
        metadata={'strength': pick['strength']},
    )
    record_price_change(
        product_id=config.product_id, sku_id=config.sku_id,
        new_price=suggested, source=f'dynamic_engine:{pick["kind"]}',
    )
    config.last_applied_at = timezone.now()
    config.save(update_fields=['last_applied_at'])
    return {'applied': True, 'kind': pick['kind'],
            'suggested_price': str(suggested),
            'strength': pick['strength']}


def _time_signal(config: DynamicPricingConfig) -> dict | None:
    """Inventory aging — if SKU has been listed > 30 days without
    sale, recommend a 5% drop per 10 idle days."""
    # Best-effort lookup of last order date for this SKU.
    try:
        from apps.orders.models import OrderItem
        last_sale = OrderItem.objects.filter(
            product__id=config.product_id,
        ).order_by('-created_at').values_list('created_at', flat=True).first()
    except Exception:
        last_sale = None
    days_idle = (timezone.now() - last_sale).days if last_sale else 60
    if days_idle < 30:
        return None
    drop_pct = Decimal(min(20, (days_idle // 10) * 5))
    last_rule = PriceRule.objects.filter(
        product_id=config.product_id, sku_id=config.sku_id,
        layer__in=('base', 'seller_override'),
        status='active',
    ).order_by('-priority_score', '-created_at').first()
    base = last_rule.price_amount if last_rule else config.max_price
    price = (base * (Decimal(100) - drop_pct) / Decimal(100)).quantize(Decimal('0.01'))
    return {'kind': 'time_decay', 'price': price,
            'strength': min(1.0, drop_pct / Decimal(20)),
            'payload': {'days_idle': days_idle, 'drop_pct': str(drop_pct)}}


def _demand_signal(config: DynamicPricingConfig) -> dict | None:
    """If demand spiked in the last 7 days vs trailing 30 → surge.
    If dropped sharply → slump."""
    try:
        from apps.forecasting.models import DailyDemand
        recent = DailyDemand.objects.filter(
            product_id=config.product_id,
            day__gte=timezone.now().date() - timedelta(days=7),
        ).aggregate(s=django_models.Sum('units_sold'))['s'] or 0
        baseline = DailyDemand.objects.filter(
            product_id=config.product_id,
            day__gte=timezone.now().date() - timedelta(days=30),
            day__lt=timezone.now().date() - timedelta(days=7),
        ).aggregate(s=django_models.Sum('units_sold'))['s'] or 0
    except Exception:
        return None
    if baseline == 0:
        return None
    weekly_avg = baseline / 23 * 7  # 23 days baseline window
    if weekly_avg == 0:
        return None
    ratio = recent / weekly_avg
    last_rule = PriceRule.objects.filter(
        product_id=config.product_id, sku_id=config.sku_id,
        layer__in=('base', 'seller_override'),
    ).order_by('-priority_score').first()
    base = last_rule.price_amount if last_rule else config.max_price
    if ratio > 1.5:  # surge
        bump_pct = Decimal(min(15, int((ratio - 1) * 10) * config.aggressiveness))
        price = (base * (Decimal(100) + bump_pct) / Decimal(100)).quantize(Decimal('0.01'))
        return {'kind': 'demand_surge', 'price': price,
                'strength': min(1.0, float(ratio) / 3),
                'payload': {'ratio': round(ratio, 2)}}
    if ratio < 0.5:
        drop_pct = Decimal(min(20, int((1 - ratio) * 10) * config.aggressiveness))
        price = (base * (Decimal(100) - drop_pct) / Decimal(100)).quantize(Decimal('0.01'))
        return {'kind': 'demand_slump', 'price': price,
                'strength': min(1.0, float(1 - ratio)),
                'payload': {'ratio': round(ratio, 2)}}
    return None


def _competitor_signal(config: DynamicPricingConfig) -> dict | None:
    """Avg competitor price in last 24h → recommend undercut by 3%."""
    cutoff = timezone.now() - timedelta(hours=24)
    avg = CompetitorObservation.objects.filter(
        product_id=config.product_id, observed_at__gte=cutoff,
    ).aggregate(a=django_models.Avg('observed_price'))['a']
    if not avg:
        return None
    undercut = (Decimal(str(avg)) * Decimal('0.97')).quantize(Decimal('0.01'))
    return {'kind': 'competitor_under', 'price': undercut,
            'strength': 0.7,
            'payload': {'competitor_avg': str(avg)}}


# ═══════════════════════════════════════════════════════════════════
# CH3/4 — Floor + cap enforcement at listing time
# ═══════════════════════════════════════════════════════════════════

def check_floor_cap(*, price: Decimal, currency: str = 'AOA',
                    category_id: str = '', country: str = '',
                    cost_basis: Decimal = None) -> dict:
    """Returns {ok: bool, code, floor?, cap?}."""
    country = (country or '').upper()
    # Floor lookup — most-specific first.
    floor = (
        PriceFloor.objects.filter(
            category_id=category_id, country=country, is_active=True,
        ).first()
        or PriceFloor.objects.filter(
            category_id=category_id, country='', is_active=True,
        ).first()
    )
    if floor:
        if floor.abs_floor and price < floor.abs_floor:
            return {'ok': False, 'code': 'BELOW_ABS_FLOOR',
                    'floor': str(floor.abs_floor)}
        if floor.min_markup_pct and cost_basis and cost_basis > 0:
            required = (cost_basis * (Decimal(100) + floor.min_markup_pct) / Decimal(100))
            if price < required:
                return {'ok': False, 'code': 'BELOW_MARKUP_FLOOR',
                        'min_required': str(required.quantize(Decimal('0.01')))}
    cap = PriceCap.objects.filter(is_active=True).filter(
        django_models.Q(country=country) | django_models.Q(country='')
    ).first()
    if cap and cap.cap_amount and price > cap.cap_amount:
        return {'ok': False, 'code': 'ABOVE_CAP', 'cap': str(cap.cap_amount)}
    return {'ok': True}


# ═══════════════════════════════════════════════════════════════════
# CH6 — Competitor observation ingest
# ═══════════════════════════════════════════════════════════════════

def record_competitor_observation(*, product_id: str, source: str,
                                    observed_price, currency: str = 'AOA',
                                    competitor_url: str = '',
                                    competitor_seller: str = '',
                                    in_stock: bool = True) -> CompetitorObservation:
    return CompetitorObservation.objects.create(
        product_id=product_id, source=source[:16],
        observed_price=Decimal(str(observed_price)),
        currency=currency, competitor_url=competitor_url[:200],
        competitor_seller=competitor_seller[:120], in_stock=in_stock,
    )


# ═══════════════════════════════════════════════════════════════════
# CH9 — Safety stock + reorder
# ═══════════════════════════════════════════════════════════════════

def compute_safety_stock(*, daily_avg: float, lead_time_days: int,
                          service_level_z: float = 1.65,
                          std_dev: float = None) -> int:
    """Classic safety-stock formula:
        SS = z × σ × √L
       where z = service level factor (1.65 ≈ 95%), σ = std-dev of
       daily demand, L = lead time in days. If σ isn't supplied we
       use 30% of mean as a conservative default."""
    sigma = std_dev if std_dev is not None else (daily_avg * 0.3)
    return int(math.ceil(service_level_z * sigma * math.sqrt(max(1, lead_time_days))))


def compute_reorder_point(*, daily_avg: float, lead_time_days: int,
                           safety_stock: int) -> int:
    return int(math.ceil(daily_avg * lead_time_days + safety_stock))


# ═══════════════════════════════════════════════════════════════════
# CH15 — Warehouse routing
# ═══════════════════════════════════════════════════════════════════

# Approximate distance buckets when coords are unknown — by country.
_COUNTRY_FALLBACK_KM = {
    ('AO', 'AO'): 50, ('AO', 'PT'): 6500, ('AO', 'BR'): 6500,
    ('AO', 'ZA'): 2800, ('AO', 'CD'): 1200,
    ('PT', 'AO'): 6500, ('BR', 'AO'): 6500,
}


def _km(a: dict, b: dict) -> float:
    """Haversine in km. Falls back to country-pair table if coords
    missing."""
    try:
        from math import sin, cos, sqrt, atan2, radians
        lat1, lon1 = float(a['lat']), float(a['lng'])
        lat2, lon2 = float(b['lat']), float(b['lng'])
        R = 6371.0
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        x = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
        return R * 2 * atan2(sqrt(x), sqrt(1 - x))
    except Exception:
        return float('inf')


def route_to_warehouse(*, product_id: str, sku_id: str,
                        quantity: int, destination_country: str,
                        destination_coords: dict = None) -> dict:
    """CH15.2 — pick the closest warehouse with available stock
    sufficient to fulfil. Falls back to split-shipment if no single
    warehouse has enough."""
    qs = WarehouseStock.objects.filter(
        product_id=product_id, sku_id=sku_id,
    ).select_related('warehouse').filter(
        warehouse__is_active=True,
    )
    options = []
    for ws in qs:
        if ws.available <= 0:
            continue
        dist = float('inf')
        if destination_coords and ws.warehouse.coords:
            dist = _km(ws.warehouse.coords, destination_coords)
        else:
            dist = _COUNTRY_FALLBACK_KM.get(
                (ws.warehouse.country, (destination_country or '').upper()),
                10000,
            )
        # Same-country bonus.
        if ws.warehouse.country == (destination_country or '').upper():
            dist *= 0.5
        options.append((dist, ws))
    options.sort(key=lambda t: t[0])

    if not options:
        return {'ok': False, 'code': 'NO_STOCK_ANY_WAREHOUSE'}
    # Single-warehouse fulfilment if possible.
    for dist, ws in options:
        if ws.available >= quantity:
            return {'ok': True, 'route_kind': 'single',
                    'warehouse_code': ws.warehouse.code,
                    'distance_km': round(dist, 1),
                    'allocations': [{'warehouse_code': ws.warehouse.code,
                                      'quantity': quantity}]}
    # CH15.3 split shipment.
    allocations = []
    remaining = quantity
    for dist, ws in options:
        if remaining <= 0:
            break
        take = min(ws.available, remaining)
        allocations.append({'warehouse_code': ws.warehouse.code,
                            'quantity': take, 'distance_km': round(dist, 1)})
        remaining -= take
    if remaining > 0:
        return {'ok': False, 'code': 'PARTIAL_ONLY',
                'short_by': remaining, 'allocations': allocations}
    return {'ok': True, 'route_kind': 'split', 'allocations': allocations}


@transaction.atomic
def reserve_warehouse_stock(*, warehouse_code: str, product_id: str,
                              sku_id: str, quantity: int) -> bool:
    ws = WarehouseStock.objects.select_for_update().filter(
        warehouse__code=warehouse_code, product_id=product_id, sku_id=sku_id,
    ).first()
    if not ws or ws.available < quantity:
        return False
    ws.reserved += quantity
    ws.save(update_fields=['reserved'])
    return True


# ═══════════════════════════════════════════════════════════════════
# CH12 — Pre-order
# ═══════════════════════════════════════════════════════════════════

@transaction.atomic
def reserve_preorder(*, config: PreOrderConfig, user, quantity: int,
                      full_amount: Decimal,
                      currency: str = 'AOA',
                      psp_intent_id: str = '') -> PreOrderReservation:
    locked = PreOrderConfig.objects.select_for_update().get(pk=config.pk)
    if not locked.enabled:
        raise ValueError('PREORDER_NOT_ENABLED')
    if locked.reserved_units + quantity > locked.max_units:
        raise ValueError('PREORDER_FULL')
    deposit_amount = (full_amount * Decimal(locked.deposit_pct) / Decimal(100)).quantize(Decimal('0.01'))
    res = PreOrderReservation.objects.create(
        config=locked, user=user, quantity=quantity,
        deposit_amount=deposit_amount, full_amount=full_amount,
        currency=currency, psp_intent_id=psp_intent_id[:120],
    )
    locked.reserved_units += quantity
    locked.save(update_fields=['reserved_units'])
    PricingInventoryEvent.log(
        seller=locked.seller, actor=user, kind='preorder.reserved',
        product_id=locked.product_id,
        payload={'qty': quantity, 'deposit': str(deposit_amount)},
    )
    return res


def fulfil_preorder(*, reservation: PreOrderReservation, order_id: str) -> bool:
    if reservation.status != 'reserved':
        return False
    reservation.status = 'fulfilled'
    reservation.fulfilled_at = timezone.now()
    reservation.save(update_fields=['status', 'fulfilled_at'])
    PricingInventoryEvent.log(
        seller=reservation.config.seller, kind='preorder.fulfilled',
        product_id=reservation.config.product_id,
        payload={'order_id': order_id},
    )
    return True


# ═══════════════════════════════════════════════════════════════════
# CH13 — Backorder
# ═══════════════════════════════════════════════════════════════════

@transaction.atomic
def queue_backorder(*, config: BackorderConfig, user, quantity: int,
                      order_id: str = '') -> BackorderRequest:
    locked = BackorderConfig.objects.select_for_update().get(pk=config.pk)
    if not locked.enabled:
        raise ValueError('BACKORDER_NOT_ENABLED')
    if locked.max_queue and locked.queue_count + quantity > locked.max_queue:
        raise ValueError('BACKORDER_QUEUE_FULL')
    locked.queue_count += quantity
    locked.save(update_fields=['queue_count'])
    deadline = timezone.now() + timedelta(days=locked.max_wait_days)
    req = BackorderRequest.objects.create(
        config=locked, user=user, quantity=quantity,
        queue_position=locked.queue_count,
        order_id=order_id[:64], deadline_at=deadline,
    )
    PricingInventoryEvent.log(
        seller=locked.seller, actor=user, kind='backorder.queued',
        product_id=locked.product_id,
        payload={'queue_position': req.queue_position,
                 'deadline': deadline.isoformat()},
    )
    return req


def release_backorder_queue(config: BackorderConfig, *, restocked_qty: int) -> int:
    """When restock arrives, fulfil FIFO until restocked_qty
    exhausted."""
    queued = list(BackorderRequest.objects.filter(
        config=config, status='queued',
    ).order_by('queue_position'))
    remaining = restocked_qty
    n = 0
    for req in queued:
        if remaining <= 0:
            break
        if req.quantity <= remaining:
            req.status = 'fulfilled'
            req.fulfilled_at = timezone.now()
            req.save(update_fields=['status', 'fulfilled_at'])
            remaining -= req.quantity
            n += 1
    BackorderConfig.objects.filter(pk=config.pk).update(
        queue_count=django_models.F('queue_count') - sum(r.quantity for r in queued[:n]),
    )
    return n


# ═══════════════════════════════════════════════════════════════════
# CH14 — Dropship routing
# ═══════════════════════════════════════════════════════════════════

def route_to_dropship(*, seller_product_id: str, seller_sku_id: str = '',
                        order_id: str = '', quantity: int = 1) -> DropshipOrder | None:
    """Find the best supplier mapping and create a DropshipOrder.
    Selection: active supplier, highest on_time_rate."""
    mapping = (
        DropshipMapping.objects.filter(
            seller_product_id=seller_product_id,
            seller_sku_id=seller_sku_id,
            is_active=True, supplier__is_active=True,
        ).order_by('-supplier__on_time_rate').first()
    )
    if not mapping:
        return None
    sla = timezone.now() + timedelta(days=mapping.supplier.average_lead_days)
    obj = DropshipOrder.objects.create(
        supplier=mapping.supplier, order_id=order_id[:64],
        seller_product_id=seller_product_id, seller_sku_id=seller_sku_id,
        quantity=quantity, sla_deadline_at=sla,
    )
    PricingInventoryEvent.log(
        kind='dropship.routed', product_id=seller_product_id,
        payload={'supplier_id': mapping.supplier_id,
                 'sla_deadline': sla.isoformat()},
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH16 — Inventory webhook + sync
# ═══════════════════════════════════════════════════════════════════

@transaction.atomic
def apply_inventory_webhook(webhook: InventoryWebhook) -> bool:
    """Process one inbound stock-change webhook idempotently.
    Updates the WarehouseStock row(s) for the seller's SKUs."""
    if webhook.processed:
        return False
    rows = WarehouseStock.objects.filter(
        warehouse__seller=webhook.seller,
        product_id=webhook.product_id, sku_id=webhook.sku_id,
    )
    # If multiple warehouses, allocate proportionally — best effort.
    n = len(rows)
    if n == 0:
        webhook.processed = True
        webhook.save(update_fields=['processed'])
        return False
    new_total = max(0, webhook.new_on_hand)
    per_wh = new_total // n
    remainder = new_total - (per_wh * n)
    for i, row in enumerate(rows):
        row.on_hand = per_wh + (1 if i < remainder else 0)
        row.save(update_fields=['on_hand', 'updated_at'])
    webhook.processed = True
    webhook.save(update_fields=['processed'])
    return True


# ═══════════════════════════════════════════════════════════════════
# CH17 — Stock alert tiering
# ═══════════════════════════════════════════════════════════════════

def evaluate_stock_alerts(seller=None) -> int:
    """Walk WarehouseStock and write StockAlert rows for tier
    transitions. `days_of_cover` uses the trailing 7-day avg sales."""
    now = timezone.now()
    qs = WarehouseStock.objects.all()
    if seller:
        qs = qs.filter(warehouse__seller=seller)
    n = 0
    for ws in qs.iterator(chunk_size=500):
        on_hand = ws.available
        # Coarse daily-sales lookup.
        try:
            from apps.forecasting.models import DailyDemand
            agg = DailyDemand.objects.filter(
                product_id=ws.product_id,
                day__gte=(now - timedelta(days=7)).date(),
            ).aggregate(s=django_models.Sum('units_sold'))['s'] or 0
            daily_avg = max(0.5, agg / 7)
        except Exception:
            daily_avg = max(0.5, 1.0)
        cover = on_hand / daily_avg
        if on_hand == 0:
            tier = 'out_of_stock'
            action = 'hide_buy_now'
        elif cover < 3:
            tier = 'critical'
            action = 'demote_in_search'
        elif cover < 7:
            tier = 'low'
            action = 'reorder_alert'
        else:
            tier = 'healthy'
            action = ''
        last = StockAlert.objects.filter(
            seller=ws.warehouse.seller,
            product_id=ws.product_id, sku_id=ws.sku_id,
        ).order_by('-transitioned_at').first()
        if last and last.tier == tier:
            continue
        StockAlert.objects.create(
            seller=ws.warehouse.seller,
            product_id=ws.product_id, sku_id=ws.sku_id,
            tier=tier, days_of_cover=round(cover, 2),
            on_hand=on_hand, auto_action=action,
        )
        n += 1
    return n


# ═══════════════════════════════════════════════════════════════════
# CH18 — Return inventory
# ═══════════════════════════════════════════════════════════════════

def receive_return(*, seller, order_id: str, product_id: str,
                    sku_id: str = '', quantity: int = 1,
                    grade: str = 'A', disposition: str = 'restock',
                    warehouse: Warehouse = None,
                    return_reason: str = '') -> ReturnInventoryReceipt:
    receipt = ReturnInventoryReceipt.objects.create(
        seller=seller, order_id=order_id[:64],
        return_reason=return_reason[:120],
        product_id=product_id, sku_id=sku_id, quantity=quantity,
        grade=grade, disposition=disposition, warehouse=warehouse,
    )
    if disposition == 'restock' and warehouse:
        WarehouseStock.objects.filter(
            warehouse=warehouse, product_id=product_id, sku_id=sku_id,
        ).update(on_hand=django_models.F('on_hand') + quantity)
    PricingInventoryEvent.log(
        seller=seller, kind='return.received',
        product_id=product_id,
        payload={'order_id': order_id, 'qty': quantity,
                 'grade': grade, 'disposition': disposition},
    )
    return receipt


# ═══════════════════════════════════════════════════════════════════
# CH19 — Audit + discrepancy
# ═══════════════════════════════════════════════════════════════════

@transaction.atomic
def finalise_audit_run(audit_run: InventoryAuditRun) -> dict:
    """Compute discrepancy_count + accuracy_rate from entries."""
    entries = audit_run.entries.all()
    total = entries.count()
    disc = sum(1 for e in entries if e.delta != 0)
    acc = 1.0 - (disc / total) if total else 1.0
    audit_run.skus_audited = total
    audit_run.discrepancy_count = disc
    audit_run.accuracy_rate = acc
    audit_run.status = 'completed'
    audit_run.finished_at = timezone.now()
    audit_run.save()
    return {'skus_audited': total, 'discrepancy_count': disc,
            'accuracy_rate': acc}


# ═══════════════════════════════════════════════════════════════════
# CH20 — Hazmat enforcement
# ═══════════════════════════════════════════════════════════════════

def check_hazmat_allowed(*, product_id: str, sku_id: str = '',
                          carrier: str = '') -> dict:
    decl = ProductHazmat.objects.filter(
        product_id=product_id, sku_id=sku_id,
    ).select_related('hazmat_class').first()
    if not decl:
        return {'ok': True, 'level': 'none'}
    cls = decl.hazmat_class
    if cls.level == 'prohibited':
        return {'ok': False, 'code': 'HAZMAT_PROHIBITED'}
    allowed = cls.allowed_carriers or []
    if carrier and allowed and carrier not in allowed:
        return {'ok': False, 'code': 'CARRIER_NOT_ALLOWED',
                'allowed_carriers': allowed}
    if cls.requires_un_number and not decl.un_number:
        return {'ok': False, 'code': 'UN_NUMBER_REQUIRED'}
    if cls.requires_safety_data_sheet and not decl.safety_data_sheet_key:
        return {'ok': False, 'code': 'SDS_REQUIRED'}
    return {'ok': True, 'level': cls.level}


# ═══════════════════════════════════════════════════════════════════
# CH21 — Oversize surcharge
# ═══════════════════════════════════════════════════════════════════

def compute_oversize_surcharge(*, country: str = '', carrier: str = '',
                                 weight_kg: Decimal, length_cm: int,
                                 width_cm: int, height_cm: int) -> dict:
    """Returns the surcharge to add to shipping for this parcel,
    based on dimensional weight or single-dimension oversize."""
    rule = OversizeSurchargeRule.objects.filter(
        is_active=True,
    ).filter(
        django_models.Q(country=country.upper()) | django_models.Q(country='')
    ).filter(
        django_models.Q(carrier=carrier) | django_models.Q(carrier='')
    ).first()
    if not rule:
        return {'surcharge': '0', 'currency': 'AOA', 'reason': ''}
    dim_weight = Decimal(length_cm * width_cm * height_cm) / Decimal(rule.dim_factor)
    chargeable = max(Decimal(str(weight_kg)), dim_weight)
    reasons = []
    apply = False
    if chargeable > rule.weight_threshold_kg:
        reasons.append('WEIGHT_OVER_THRESHOLD')
        apply = True
    if max(length_cm, width_cm, height_cm) > rule.length_threshold_cm:
        reasons.append('DIMENSION_OVER_THRESHOLD')
        apply = True
    if not apply:
        return {'surcharge': '0', 'currency': rule.currency, 'reason': ''}
    return {'surcharge': str(rule.surcharge_amount),
            'currency': rule.currency,
            'reason': '+'.join(reasons),
            'chargeable_weight_kg': str(chargeable.quantize(Decimal('0.01')))}


# ═══════════════════════════════════════════════════════════════════
# CH22 — Virtual bundle inventory
# ═══════════════════════════════════════════════════════════════════

def recompute_virtual_bundle(bundle_id: str, components: list[dict]) -> int:
    """`components` shape:
    [{product_id, sku_id, quantity_per_bundle}]. Returns the floor
    bundle count."""
    floors = []
    for c in components:
        agg = WarehouseStock.objects.filter(
            product_id=str(c.get('product_id', '')),
            sku_id=str(c.get('sku_id', '')),
        ).aggregate(s=django_models.Sum('on_hand'))['s'] or 0
        per = int(c.get('quantity_per_bundle', 1)) or 1
        floors.append(agg // per)
    n = min(floors) if floors else 0
    VirtualBundleInventory.objects.update_or_create(
        bundle_id=bundle_id[:64],
        defaults={'components': components, 'available_bundles': n},
    )
    return n


# ═══════════════════════════════════════════════════════════════════
# CH24 — KPI snapshot
# ═══════════════════════════════════════════════════════════════════

def snapshot_pi_kpis(snapshot_date=None) -> PricingInventoryKpiSnapshot:
    if snapshot_date is None:
        snapshot_date = timezone.now().date()
    start = timezone.make_aware(timezone.datetime.combine(snapshot_date,
                                                          timezone.datetime.min.time()))
    end = start + timedelta(days=1)
    # Pricing KPIs.
    price_changes = PriceHistory.objects.filter(
        recorded_at__gte=start, recorded_at__lt=end,
    ).count()
    floor_violations = PricingInventoryEvent.objects.filter(
        kind='price.floor_violation',
        created_at__gte=start, created_at__lt=end,
    ).count()
    cap_violations = PricingInventoryEvent.objects.filter(
        kind='price.cap_violation',
        created_at__gte=start, created_at__lt=end,
    ).count()
    # Inventory KPIs.
    stockout = WarehouseStock.objects.filter(on_hand=0).count()
    critical = StockAlert.objects.filter(tier='critical').count()
    pre_units = PreOrderReservation.objects.filter(
        status='reserved',
    ).aggregate(s=django_models.Sum('quantity'))['s'] or 0
    back_units = BackorderRequest.objects.filter(
        status='queued',
    ).aggregate(s=django_models.Sum('quantity'))['s'] or 0
    dropship = DropshipOrder.objects.filter(
        created_at__gte=start, created_at__lt=end,
    ).count()
    # Stock accuracy from latest audit runs.
    avg_acc = InventoryAuditRun.objects.filter(
        status='completed',
    ).aggregate(a=django_models.Avg('accuracy_rate'))['a'] or 1.0
    # By-warehouse rollup.
    by_wh = dict(
        WarehouseStock.objects.values_list('warehouse__code').annotate(s=django_models.Sum('on_hand'))
    )
    obj, _ = PricingInventoryKpiSnapshot.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'price_change_count': price_changes,
            'price_floor_violations': floor_violations,
            'price_cap_violations': cap_violations,
            'avg_stock_accuracy': avg_acc,
            'stockout_skus': stockout,
            'critical_skus': critical,
            'preorder_units': pre_units,
            'backorder_units': back_units,
            'dropship_orders': dropship,
            'by_warehouse': {k or '': v for k, v in by_wh.items()},
        },
    )
    return obj
