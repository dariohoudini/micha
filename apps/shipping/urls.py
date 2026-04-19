from django.urls import path
from .views import (
    ShippingAddressListCreateView,
    ShippingAddressDetailView,
    SetDefaultAddressView,
    DeliveryZoneListView,
    ShippingCostEstimateView,
)


urlpatterns = [
    path('addresses/', ShippingAddressListCreateView.as_view(), name='address-list'),
    path('addresses/<int:pk>/', ShippingAddressDetailView.as_view(), name='address-detail'),
    path('addresses/<int:pk>/set-default/', SetDefaultAddressView.as_view(), name='set-default'),
    path('zones/', DeliveryZoneListView.as_view(), name='zone-list'),
    path('estimate/', ShippingCostEstimateView.as_view(), name='estimate'),
]
