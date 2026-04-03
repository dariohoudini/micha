from django.urls import path

from .views import (
    PublicProductListView,
    PublicProductDetailView,
    SellerProductCreateView,
    SellerProductUpdateView,
    SellerProductDeleteView,
    SellerMyProductsListView,
)

app_name = "products"

urlpatterns = [
    # ============================
    # PUBLIC
    # ============================
    path("", PublicProductListView.as_view(), name="public-product-list"),
    path("<int:pk>/", PublicProductDetailView.as_view(), name="public-product-detail"),

    # ============================
    # SELLER
    # ============================
    path("seller/my/", SellerMyProductsListView.as_view(), name="seller-my-products"),
    path("seller/create/", SellerProductCreateView.as_view(), name="seller-product-create"),
    path("seller/<int:pk>/update/", SellerProductUpdateView.as_view(), name="seller-product-update"),
    path("seller/<int:pk>/delete/", SellerProductDeleteView.as_view(), name="seller-product-delete"),
]
