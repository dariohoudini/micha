from django.urls import path
from .views import (
    CollectionListView, CollectionDetailView, AdminCollectionCreateView,
    ProductOfTheDayView, AdminSetProductOfDayView,
    SellerSpotlightView, PlatformAnnouncementView, PriceHistoryView,
)


urlpatterns = [
    path('', CollectionListView.as_view(), name='list'),
    path('admin/', AdminCollectionCreateView.as_view(), name='admin-create'),
    path('product-of-day/', ProductOfTheDayView.as_view(), name='product-of-day'),
    path('admin/product-of-day/', AdminSetProductOfDayView.as_view(), name='admin-potd'),
    path('seller-spotlight/', SellerSpotlightView.as_view(), name='seller-spotlight'),
    path('announcements/', PlatformAnnouncementView.as_view(), name='announcements'),
    path('price-history/<int:product_id>/', PriceHistoryView.as_view(), name='price-history'),
    # Must be last — slug catch-all
    path('<slug:slug>/', CollectionDetailView.as_view(), name='detail'),
]
