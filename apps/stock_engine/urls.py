from django.urls import path

from . import views

app_name = 'stock_engine'

urlpatterns = [
    # CH14 variant availability (buyer)
    path('products/<str:product_id>/variant-availability/',
         views.VariantAvailabilityView.as_view(), name='variant-availability'),
    # CH3/5/20 reserve
    path('reserve/', views.ReserveView.as_view(), name='reserve'),
    path('reservations/<uuid:reservation_id>/extend/',
         views.ReservationExtendView.as_view(), name='reservation-extend'),
    path('reservations/<uuid:reservation_id>/release/',
         views.ReservationReleaseView.as_view(), name='reservation-release'),
    # CH15 notify-me
    path('skus/<uuid:sku_id>/notify-me/', views.NotifyMeView.as_view(),
         name='notify-me'),
    # CH6 flash claim
    path('flash/<int:pool_id>/claim/', views.FlashClaimView.as_view(),
         name='flash-claim'),
    # CH8 bulk update
    path('bulk-update/', views.BulkUpdateView.as_view(), name='bulk-update'),
    # CH17 seller health
    path('health/', views.InventoryHealthView.as_view(), name='health'),
    # CH24 KPIs
    path('kpis/', views.KpiView.as_view(), name='kpis'),
]
