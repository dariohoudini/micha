from django.urls import path
from .views import (
    ListingListView,
    ListingDetailView,
    ListingCreateView,
    MyListingsView,
    ListingUpdateDeleteView,
)


urlpatterns = [
    path('', ListingListView.as_view(), name='listing-list'),
    path('create/', ListingCreateView.as_view(), name='listing-create'),
    path('my/', MyListingsView.as_view(), name='my-listings'),
    path('<uuid:pk>/', ListingDetailView.as_view(), name='listing-detail'),
    path('<uuid:pk>/edit/', ListingUpdateDeleteView.as_view(), name='listing-edit'),
]
