from django.urls import path

from .views import (
    AuditRunView, DynamicPricingConfigView, MyStockAlertsView,
    PIKpiView, PreOrderConfigView, PriceRuleListCreateView,
    ProductHazmatView, RegionalAdjustmentView,
    SellerInventoryDashboardView, WarehouseView,
    audit_finalise, audit_record_entry, backorder_queue_view,
    competitor_record, compute_safety, dropship_route,
    evaluate_dynamic, floor_cap_check, hazmat_check,
    inventory_webhook_ingest, oversize_surcharge,
    preorder_reserve_view, price_resolve, reevaluate_alerts,
    return_receive, virtual_bundle_recompute, warehouse_reserve,
    warehouse_route, was_price,
)


urlpatterns = [
    # CH1 — price resolution
    path('price/resolve/',          price_resolve, name='pi-price-resolve'),
    path('price/rules/',            PriceRuleListCreateView.as_view(), name='pi-price-rules'),
    path('price/was-price/',        was_price, name='pi-was-price'),
    # CH2 — dynamic pricing
    path('dynamic/configs/',        DynamicPricingConfigView.as_view(), name='pi-dynamic-configs'),
    path('dynamic/evaluate/',       evaluate_dynamic, name='pi-dynamic-evaluate'),
    # CH3/4 — floor + cap
    path('price/floor-cap-check/',  floor_cap_check, name='pi-floor-cap'),
    # CH6 — competitor
    path('competitor/observe/',     competitor_record, name='pi-competitor'),
    # CH7.2 — PPP
    path('regional/adjustments/',   RegionalAdjustmentView.as_view(), name='pi-regional'),
    # CH9 — safety stock
    path('safety-stock/compute/',   compute_safety, name='pi-safety'),
    # CH12 — pre-order
    path('preorder/configs/',       PreOrderConfigView.as_view(), name='pi-preorder-configs'),
    path('preorder/reserve/',       preorder_reserve_view, name='pi-preorder-reserve'),
    # CH13 — backorder
    path('backorder/queue/',        backorder_queue_view, name='pi-backorder-queue'),
    # CH14 — dropship
    path('dropship/route/',         dropship_route, name='pi-dropship-route'),
    # CH15 — warehouses
    path('warehouses/',             WarehouseView.as_view(), name='pi-warehouses'),
    path('warehouses/route/',       warehouse_route, name='pi-wh-route'),
    path('warehouses/reserve/',     warehouse_reserve, name='pi-wh-reserve'),
    # CH16 — webhook ingest
    path('inventory/webhook/',      inventory_webhook_ingest, name='pi-wh-webhook'),
    # CH17 — stock alerts
    path('stock-alerts/me/',        MyStockAlertsView.as_view(), name='pi-stock-alerts'),
    path('stock-alerts/reevaluate/', reevaluate_alerts, name='pi-reeval-alerts'),
    # CH18 — returns
    path('returns/receive/',        return_receive, name='pi-return-receive'),
    # CH19 — audit
    path('audit/runs/',             AuditRunView.as_view(), name='pi-audit-runs'),
    path('audit/runs/entry/',       audit_record_entry, name='pi-audit-entry'),
    path('audit/runs/finalise/',    audit_finalise, name='pi-audit-finalise'),
    # CH20 — hazmat
    path('hazmat/declarations/',    ProductHazmatView.as_view(), name='pi-hazmat'),
    path('hazmat/check/',           hazmat_check, name='pi-hazmat-check'),
    # CH21 — oversize surcharge
    path('shipping/oversize-surcharge/', oversize_surcharge, name='pi-oversize'),
    # CH22 — virtual bundle
    path('virtual-bundles/recompute/', virtual_bundle_recompute, name='pi-vbundle'),
    # CH23 — seller dashboard
    path('dashboard/me/',           SellerInventoryDashboardView.as_view(), name='pi-dashboard'),
    # CH24 — KPI
    path('admin/kpi/',              PIKpiView.as_view(), name='pi-kpi'),
]
