from django.urls import path
from .views import (
    ShippingAddressListCreateView,
    ShippingAddressDetailView,
    SetDefaultAddressView,
    DeliveryZoneListView,
    ShippingCostEstimateView,
    ShippingTemplateListCreateView,
    ShippingTemplateDetailView,
    ReverseGeocodeView,
)


urlpatterns = [
    path('addresses/', ShippingAddressListCreateView.as_view(), name='address-list'),
    path('addresses/<int:pk>/', ShippingAddressDetailView.as_view(), name='address-detail'),
    path('addresses/<int:pk>/set-default/', SetDefaultAddressView.as_view(), name='set-default'),
    path('zones/', DeliveryZoneListView.as_view(), name='zone-list'),
    path('estimate/', ShippingCostEstimateView.as_view(), name='estimate'),
    # User Process Flow §9.2 — Use My Location autofill.
    path('geocode/reverse/', ReverseGeocodeView.as_view(), name='reverse-geocode'),

    # AliExpress §14.1 shipping templates
    path('templates/', ShippingTemplateListCreateView.as_view(), name='shipping-template-list'),
    path('templates/<int:pk>/', ShippingTemplateDetailView.as_view(), name='shipping-template-detail'),
]
