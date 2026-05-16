from django.urls import path
from .views import MyLoyaltyView, TierListView, PointsAdjustView, RecomputeMyTierView

urlpatterns = [
    path('me/', MyLoyaltyView.as_view(), name='loyalty-me'),
    path('me/recompute/', RecomputeMyTierView.as_view(), name='loyalty-recompute'),
    path('tiers/', TierListView.as_view(), name='loyalty-tiers'),
    path('admin/adjust/', PointsAdjustView.as_view(), name='loyalty-adjust'),
]
