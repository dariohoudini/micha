from django.urls import path

from .views import (
    CarrierListView, FulfilmentWaveView, InboundShipmentView,
    LogisticsKpiView, MyLabelsView, PickupPointListView,
    StockTransferView, TrackingEtaView, TrackingStatusView,
    address_validate, carrier_select, choice_local_record,
    cod_collected, cod_issue, cod_remit, compliance_check,
    customs_exception_record, customs_generate, dg_carrier_filter,
    duty_compute, failed_delivery_record,
    fulfilment_exception_record, hs_classify, inbound_receive,
    insurance_claim, insurance_issue, label_generate,
    pickup_assign, pickup_confirm, return_label_generate,
    reverse_inspect, stock_transfer_approve, tracking_webhook,
    wave_advance,
)


urlpatterns = [
    # CH1 — carriers
    path('carriers/', CarrierListView.as_view(), name='lo-carriers'),
    # CH2 — selection
    path('carriers/select/', carrier_select, name='lo-carrier-select'),
    # CH3 — labels
    path('labels/generate/', label_generate, name='lo-label-generate'),
    path('labels/me/', MyLabelsView.as_view(), name='lo-labels-me'),
    # CH4 — customs + HS
    path('hs/classify/', hs_classify, name='lo-hs-classify'),
    path('customs/generate/', customs_generate, name='lo-customs-generate'),
    # CH5 — duty
    path('duty/compute/', duty_compute, name='lo-duty'),
    # CH6 — insurance
    path('insurance/issue/', insurance_issue, name='lo-insurance-issue'),
    path('insurance/claim/', insurance_claim, name='lo-insurance-claim'),
    # CH7 — tracking
    path('tracking/<str:carrier_code>/webhook/', tracking_webhook, name='lo-tracking-webhook'),
    path('tracking/<str:tracking_number>/status/', TrackingStatusView.as_view(), name='lo-tracking-status'),
    # CH8 — ETA
    path('tracking/<str:tracking_number>/eta/', TrackingEtaView.as_view(), name='lo-tracking-eta'),
    # CH9 — address validation
    path('address/validate/', address_validate, name='lo-address-validate'),
    # CH10 — DG filter
    path('dg/carrier-filter/', dg_carrier_filter, name='lo-dg-filter'),
    # CH12 — COD
    path('cod/issue/', cod_issue, name='lo-cod-issue'),
    path('cod/collected/', cod_collected, name='lo-cod-collected'),
    path('cod/remit/', cod_remit, name='lo-cod-remit'),
    # CH13 — return labels
    path('returns/labels/generate/', return_label_generate, name='lo-return-label'),
    # CH14 — reverse logistics
    path('returns/inspect/', reverse_inspect, name='lo-return-inspect'),
    # CH15 — inbound shipments
    path('inbound/shipments/', InboundShipmentView.as_view(), name='lo-inbound-list'),
    path('inbound/receive/', inbound_receive, name='lo-inbound-receive'),
    # CH16 — waves
    path('waves/', FulfilmentWaveView.as_view(), name='lo-waves'),
    path('waves/advance/', wave_advance, name='lo-wave-advance'),
    # CH17 — stock transfer
    path('transfers/', StockTransferView.as_view(), name='lo-transfers'),
    path('transfers/approve/', stock_transfer_approve, name='lo-transfer-approve'),
    # CH18 — failed delivery
    path('failed-delivery/record/', failed_delivery_record, name='lo-failed'),
    # CH19 — customs exception
    path('customs/exception/', customs_exception_record, name='lo-customs-exception'),
    # CH20 — fulfilment exception
    path('fulfilment/exception/', fulfilment_exception_record, name='lo-fulfilment-exception'),
    # CH21 — pickup points
    path('pickup-points/', PickupPointListView.as_view(), name='lo-pickup-points'),
    path('pickup-points/assign/', pickup_assign, name='lo-pickup-assign'),
    path('pickup-points/confirm/', pickup_confirm, name='lo-pickup-confirm'),
    # CH22 — Choice
    path('choice-local/record/', choice_local_record, name='lo-choice'),
    # CH23 — compliance
    path('compliance/check/', compliance_check, name='lo-compliance'),
    # CH24 — KPI
    path('admin/kpi/', LogisticsKpiView.as_view(), name='lo-kpi'),
]
