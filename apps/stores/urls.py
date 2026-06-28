from django.urls import path
from .views import (
    MyStoreListCreateView,
    MyStoreDetailView,
    PublicStoreListView,
    PublicStoreDetailView,
    StoreReviewCreateView,
    StoreReviewListView,
    ToggleStoreOpenView,
)

urlpatterns = [
    path('', PublicStoreListView.as_view(), name='public-stores'),

    # Seller-facing endpoints — owner-scoped, write-capable.
    # GET list owned stores · POST create a new one
    path('my/', MyStoreListCreateView.as_view(), name='my-stores'),
    # GET load · PATCH update · DELETE close — all owner-scoped.
    path('my/<int:pk>/', MyStoreDetailView.as_view(), name='my-store-detail'),

    path('toggle-open/', ToggleStoreOpenView.as_view(), name='toggle-store-open'),

    # Public read-only endpoints (kept AFTER the /my/ paths so the
    # URL resolver doesn't shadow "my" as a slug/pk).
    path('<int:pk>/', PublicStoreDetailView.as_view(), name='store-detail'),
    path('<int:pk>/review/', StoreReviewCreateView.as_view(), name='store-review-create'),
    path('<int:pk>/reviews/', StoreReviewListView.as_view(), name='store-reviews'),
]
