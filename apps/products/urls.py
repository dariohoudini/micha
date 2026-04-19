from django.urls import path
from .views import (
    CategoryListView,
    ProductListView, ProductDetailView,
    SellerProductListView, ProductCreateView, ProductUpdateView,
    ProductImageUploadView, BulkProductCreateView,
    ProductCompareView, ProductQAListCreateView, ProductDuplicateView,
)


urlpatterns = [
    path("", ProductListView.as_view(), name="list"),
    path("categories/", CategoryListView.as_view(), name="categories"),
    path("compare/", ProductCompareView.as_view(), name="compare"),
    path("bulk/", BulkProductCreateView.as_view(), name="bulk-create"),
    path("my/", SellerProductListView.as_view(), name="my-products"),
    path("create/", ProductCreateView.as_view(), name="create"),
    path("<slug:slug>/", ProductDetailView.as_view(), name="detail"),
    path("<int:pk>/update/", ProductUpdateView.as_view(), name="update"),
    path("<int:pk>/images/", ProductImageUploadView.as_view(), name="upload-image"),
    path("<int:pk>/qa/", ProductQAListCreateView.as_view(), name="qa"),
    path("<int:pk>/duplicate/", ProductDuplicateView.as_view(), name="duplicate"),
]
