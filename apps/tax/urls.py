from django.urls import path
from .views import (
    JurisdictionListView, RateUpdateView, RateHistoryView,
    CalculateView, CalculationAuditView,
)

urlpatterns = [
    path('jurisdictions/', JurisdictionListView.as_view()),
    path('jurisdictions/<int:jurisdiction_id>/rates/', RateUpdateView.as_view()),
    path('jurisdictions/<int:jurisdiction_id>/rates/history/', RateHistoryView.as_view()),
    path('calculate/', CalculateView.as_view()),
    path('calculations/', CalculationAuditView.as_view()),
]
