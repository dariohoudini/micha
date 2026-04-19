from django.urls import path
from .views import (
    MyStoreListView,
    PublicStoreListView,
    PublicStoreDetailView,
    StoreReviewCreateView,
    StoreReviewListView,
)


urlpatterns = [
    path('', PublicStoreListView.as_view(), name='public-stores'),
    path('my/', MyStoreListView.as_view(), name='my-stores'),
    path('<int:pk>/', PublicStoreDetailView.as_view(), name='store-detail'),
    path('<int:pk>/review/', StoreReviewCreateView.as_view(), name='store-review-create'),
    path('<int:pk>/reviews/', StoreReviewListView.as_view(), name='store-reviews'),
]
