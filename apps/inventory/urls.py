from django.urls import path
from .views import (
    VariantListCreateView,
    VariantDetailView,
    StockReservationView,
    LowStockAlertView,
)


urlpatterns = [
    path("variants/", VariantListCreateView.as_view(), name="variant-list"),
    path("variants/<int:pk>/", VariantDetailView.as_view(), name="variant-detail"),
    path("reserve/", StockReservationView.as_view(), name="reserve"),
    path("low-stock-alerts/", LowStockAlertView.as_view(), name="low-stock-alerts"),
]
