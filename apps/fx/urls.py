from django.urls import path
from .views import (
    FXRateListView, FXRateHistoryView, FXConvertView, FXConversionAuditView,
)

urlpatterns = [
    path('rates/', FXRateListView.as_view(), name='fx-rates'),
    path('rates/<str:source>/<str:target>/history/', FXRateHistoryView.as_view()),
    path('convert/', FXConvertView.as_view(), name='fx-convert'),
    path('conversions/', FXConversionAuditView.as_view(), name='fx-conversions'),
]
