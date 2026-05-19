"""Ledger admin URL routing. Mounted at /api/v1/admin/ledger/."""
from django.urls import path
from .admin_views import (
    LedgerHealthView, LedgerUnbalancedJournalsView,
    LedgerDriftView, LedgerDriftScanView, LedgerDriftFixView,
)


urlpatterns = [
    path('health/', LedgerHealthView.as_view(), name='ledger-health'),
    path('unbalanced/', LedgerUnbalancedJournalsView.as_view(),
         name='ledger-unbalanced'),
    path('drift/', LedgerDriftView.as_view(), name='ledger-drift'),
    path('drift-scan/', LedgerDriftScanView.as_view(), name='ledger-drift-scan'),
    path('drift/<int:user_id>/fix/', LedgerDriftFixView.as_view(),
         name='ledger-drift-fix'),
]
