from django.urls import path

from . import views

app_name = 'last_mile'

urlpatterns = [
    # CH2 rate quote
    path('rate-quote/', views.RateQuoteView.as_view(), name='rate-quote'),
    # CH8 windows
    path('windows/', views.WindowsView.as_view(), name='windows'),
    # CH3 GPS addresses
    path('addresses/', views.GpsAddressView.as_view(), name='addresses'),
    # CH13 tracking
    path('tracking/<str:tracking_id>/', views.TrackingView.as_view(),
         name='tracking'),
    # CH6 POD
    path('shipments/<uuid:shipment_id>/pod/', views.PodCaptureView.as_view(),
         name='pod'),
    # CH7 fail
    path('shipments/<uuid:shipment_id>/fail/', views.FailDeliveryView.as_view(),
         name='fail'),
    # CH5 route
    path('couriers/<uuid:courier_id>/route/', views.CourierRouteView.as_view(),
         name='route'),
    # CH24 KPIs
    path('kpis/', views.KpiView.as_view(), name='kpis'),
]
