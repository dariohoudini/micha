from django.urls import path

from . import views

app_name = 'seller_operations'

urlpatterns = [
    # CH2 staff
    path('staff', views.staff_collection, name='staff'),
    path('staff/<uuid:staff_id>/status', views.staff_set_status,
         name='staff-status'),
    path('staff/audit', views.staff_audit, name='staff-audit'),
    # CH3 draft/scheduled
    path('listings/<str:product_id>/transition', views.listing_transition,
         name='listing-transition'),
    path('listings/<str:product_id>/schedule', views.listing_schedule,
         name='listing-schedule'),
    # CH4 clone
    path('listings/<str:product_id>/clone', views.clone_product,
         name='listing-clone'),
    # CH5 repricing
    path('repricing/rules', views.repricing_rules, name='repricing-rules'),
    path('repricing/<str:product_id>/override', views.manual_price_override,
         name='price-override'),
    # CH6 packing / export
    path('orders/<uuid:order_id>/packing-slip', views.packing_slip,
         name='packing-slip'),
    path('orders/bulk-export', views.bulk_export, name='bulk-export'),
    # CH7 shipping recon
    path('shipping/reconciliation', views.shipping_recon, name='shipping-recon'),
    # CH8 auto-responder
    path('messages/auto-responder', views.auto_responder, name='auto-responder'),
    # CH9 refund approval
    path('refunds/requests', views.refund_requests, name='refund-requests'),
    path('refunds/requests/<uuid:request_id>/review', views.refund_review,
         name='refund-review'),
    # CH10 income tax
    path('finance/income-summary', views.income_summary, name='income-summary'),
    # CH11 store design
    path('store/<str:store_id>/design', views.store_design, name='store-design'),
    # CH13 low stock
    path('inventory/low-stock', views.low_stock, name='low-stock'),
    # CH14 SLA
    path('fulfilment/sla', views.sla_dashboard, name='sla-dashboard'),
    path('fulfilment/sla/excuse', views.sla_excuse, name='sla-excuse'),
    # CH15 payment holds
    path('finance/payment-holds', views.payment_holds, name='payment-holds'),
    # CH16 compliance
    path('compliance', views.compliance, name='compliance'),
    path('compliance/<uuid:violation_id>/fix', views.compliance_fix,
         name='compliance-fix'),
    # CH17 activation
    path('activation', views.activation, name='activation'),
    # CH18 recovery
    path('recovery/<uuid:plan_id>/submit', views.recovery_submit,
         name='recovery-submit'),
    # CH19 benchmarks
    path('benchmarks/<str:category_id>', views.benchmarks, name='benchmarks'),
    # CH20 returns
    path('returns', views.returns_centre, name='returns'),
    path('returns/inspect', views.return_inspect, name='return-inspect'),
    # CH21 bulk messaging
    path('messages/bulk', views.bulk_message, name='bulk-message'),
    # CH22 financial
    path('finance/dashboard', views.financial, name='financial'),
    # CH24 KPIs
    path('kpis', views.kpis, name='kpis'),
]
