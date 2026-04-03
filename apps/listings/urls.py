from django.urls import path
from .views import ListingCreateView, ListingListView, ListingDetailView

urlpatterns = [
    path('create/', ListingCreateView.as_view(), name='listing-create'),
    path('list/', ListingListView.as_view(), name='listing-list'),
    path('detail/<uuid:pk>/', ListingDetailView.as_view(), name='listing-detail'),
]
