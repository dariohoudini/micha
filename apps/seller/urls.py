from django.urls import path
from .views import (
    SellerVerificationView,
    SellerDashboardView,
    StoreCreateView,
    StoreUpdateView,
    SellerStoreListView,
    ProductCreateView,
    ProductUpdateView,
    SellerProductListView,
)

app_name = "seller"

urlpatterns = [
    # Verification
    path("verify/", SellerVerificationView.as_view(), name="seller-verification"),

    # Dashboard
    path("dashboard/", SellerDashboardView.as_view(), name="seller-dashboard"),

    # Stores
    path("store/create/", StoreCreateView.as_view(), name="store-create"),
    path("store/update/", StoreUpdateView.as_view(), name="store-update"),
    path("stores/", SellerStoreListView.as_view(), name="seller-stores"),

    # Products
    path("product/create/", ProductCreateView.as_view(), name="product-create"),
    path("product/update/<int:pk>/", ProductUpdateView.as_view(), name="product-update"),
    path("products/", SellerProductListView.as_view(), name="seller-products"),
]
