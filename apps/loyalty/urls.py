from django.urls import path
from .views import (
    MyLoyaltyView, TierListView, PointsAdjustView, RecomputeMyTierView,
    DailyCheckInView, CoinTaskCompleteView, TodayCoinTasksView,
)

urlpatterns = [
    path('me/', MyLoyaltyView.as_view(), name='loyalty-me'),
    path('me/recompute/', RecomputeMyTierView.as_view(), name='loyalty-recompute'),
    path('tiers/', TierListView.as_view(), name='loyalty-tiers'),
    path('admin/adjust/', PointsAdjustView.as_view(), name='loyalty-adjust'),

    # AliExpress 2025 CH 5 — Coins / Daily Check-In / Tasks
    path('coins/check-in/', DailyCheckInView.as_view(), name='coins-checkin'),
    path('coins/tasks/', TodayCoinTasksView.as_view(), name='coins-tasks-list'),
    path('coins/tasks/complete/', CoinTaskCompleteView.as_view(), name='coins-task-complete'),
]
