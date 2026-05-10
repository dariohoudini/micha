from django.urls import path
from .views import (
    PriceAlertView,
    CategoryListView,
    ProductListView, ProductDetailView, ProductFacetsView,
    SellerProductListView, ProductCreateView, ProductUpdateView,
    ProductImageUploadView, BulkProductCreateView,
    ProductCompareView, ProductQAListCreateView, ProductQAAnswerView, ProductDuplicateView,
    ProductGroupListView, ProductGroupSuggestView, ProductGroupOffersView,
)

urlpatterns = [
    path("", ProductListView.as_view(), name="list"),
    path("facets/", ProductFacetsView.as_view(), name="facets"),
    path("categories/", CategoryListView.as_view(), name="categories"),
    path("compare/", ProductCompareView.as_view(), name="compare"),
    path("bulk/", BulkProductCreateView.as_view(), name="bulk-create"),
    path("my/", SellerProductListView.as_view(), name="my-products"),
    path("create/", ProductCreateView.as_view(), name="create"),
    path("groups/", ProductGroupListView.as_view(), name="product-groups"),
    path("groups/suggest/", ProductGroupSuggestView.as_view(), name="product-group-suggest"),
    path("<slug:slug>/price-alert/", PriceAlertView.as_view(), name="price-alert"),
    path("groups/<int:group_id>/offers/", ProductGroupOffersView.as_view(), name="product-group-offers"),
    path("<slug:slug>/", ProductDetailView.as_view(), name="detail"),
    path("<int:pk>/update/", ProductUpdateView.as_view(), name="update"),
    path("<int:pk>/images/", ProductImageUploadView.as_view(), name="upload-image"),
    path("<int:pk>/qa/", ProductQAListCreateView.as_view(), name="qa"),
    path("qa/<int:qa_id>/answer/", ProductQAAnswerView.as_view(), name="qa-answer"),
    path("<int:pk>/duplicate/", ProductDuplicateView.as_view(), name="duplicate"),
]
