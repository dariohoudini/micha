"""
Celery beat jobs for Pricing & Inventory.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone


log = logging.getLogger(__name__)


@shared_task(name='pricing_inventory.evaluate_dynamic_pricing_all')
def evaluate_dynamic_pricing_all():
    """CH2 — walk every enabled dynamic-pricing config."""
    from . import services
    from .models import DynamicPricingConfig
    n = 0
    for cfg in DynamicPricingConfig.objects.filter(enabled=True).iterator(chunk_size=200):
        try:
            r = services.evaluate_dynamic_pricing(cfg)
            if r.get('applied'):
                n += 1
        except Exception as e:
            log.exception('dynamic eval failed cfg=%s err=%s', cfg.pk, e)
    return {'applied': n}


@shared_task(name='pricing_inventory.evaluate_stock_alerts')
def evaluate_stock_alerts_task():
    """CH17 — re-tier every SKU's stock alert state."""
    from . import services
    return {'transitions': services.evaluate_stock_alerts()}


@shared_task(name='pricing_inventory.expire_preorder_holds')
def expire_preorder_holds():
    """Pre-order cancellations beyond the grace period reduce
    reserved_units so the next buyer can pre-order."""
    from .models import PreOrderConfig, PreOrderReservation
    cutoff = timezone.now()
    cancelled_recently = PreOrderReservation.objects.filter(
        status='cancelled', cancelled_at__lt=cutoff,
    )
    n = 0
    for res in cancelled_recently[:200]:
        cfg = res.config
        cfg.reserved_units = max(0, cfg.reserved_units - res.quantity)
        cfg.save(update_fields=['reserved_units'])
        n += 1
    return {'cleaned': n}


@shared_task(name='pricing_inventory.expire_backorder_sla')
def expire_backorder_sla():
    """CH13 — refund + cancel backorders past their SLA."""
    from .models import BackorderRequest
    now = timezone.now()
    qs = BackorderRequest.objects.filter(
        status='queued', deadline_at__lt=now,
    )
    n = qs.update(status='expired')
    return {'expired': n}


@shared_task(name='pricing_inventory.snapshot_pi_kpis')
def snapshot_pi_kpis_task():
    from . import services
    snap = services.snapshot_pi_kpis()
    return {'date': str(snap.snapshot_date)}


@shared_task(name='pricing_inventory.recompute_virtual_bundles')
def recompute_virtual_bundles_task():
    """Daily — recompute the available_bundles count for every
    registered virtual bundle. Reads the underlying components from
    apps.marketing_engine.BundleDeal if installed."""
    from . import services
    from .models import VirtualBundleInventory
    n = 0
    try:
        from apps.marketing_engine.models import BundleDeal
        for b in BundleDeal.objects.filter(status='active').iterator():
            components = []
            for c in (b.components or []):
                components.append({
                    'product_id': c.get('product_id', ''),
                    'sku_id': c.get('sku_id', ''),
                    'quantity_per_bundle': c.get('quantity', 1),
                })
            services.recompute_virtual_bundle(
                bundle_id=str(b.id), components=components,
            )
            n += 1
    except Exception:
        # Fall back to whatever VirtualBundleInventory rows already
        # exist — re-running them refreshes against current stock.
        for v in VirtualBundleInventory.objects.iterator():
            services.recompute_virtual_bundle(
                bundle_id=v.bundle_id, components=v.components or [],
            )
            n += 1
    return {'recomputed': n}
