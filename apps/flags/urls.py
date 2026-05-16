from django.urls import path
from .views import (
    FlagListView, FlagDetailView, FlagExposureStatsView,
    FlagEvaluateView, FlagOverrideView,
)

urlpatterns = [
    path('', FlagListView.as_view(), name='flags-list'),
    path('<str:name>/', FlagDetailView.as_view(), name='flags-detail'),
    path('<str:name>/exposures/', FlagExposureStatsView.as_view(), name='flags-exposures'),
    path('<str:name>/override/', FlagOverrideView.as_view(), name='flags-override'),
    path('evaluate/<str:name>/', FlagEvaluateView.as_view(), name='flags-evaluate'),
]
