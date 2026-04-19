from django.urls import path
from .views import (
    AdminUserListView,
    AdminUserDetailView,
    AdminProductListView,
    AdminAnalyticsView,
    AdminPayoutListView,
    AdminPayoutActionView,
)


urlpatterns = [
    path('users/', AdminUserListView.as_view(), name='user-list'),
    path('users/<int:pk>/', AdminUserDetailView.as_view(), name='user-detail'),
    path('products/', AdminProductListView.as_view(), name='product-list'),
    path('analytics/', AdminAnalyticsView.as_view(), name='analytics'),
    path('payouts/', AdminPayoutListView.as_view(), name='payout-list'),
    path('payouts/<uuid:pk>/', AdminPayoutActionView.as_view(), name='payout-action'),
]
