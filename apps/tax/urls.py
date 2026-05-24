from django.urls import path
from .views import (
    JurisdictionListView, RateUpdateView, RateHistoryView,
    CalculateView, CalculationAuditView,
)
from .agt_report import AGTReportView

urlpatterns = [
    path('jurisdictions/', JurisdictionListView.as_view()),
    path('jurisdictions/<int:jurisdiction_id>/rates/', RateUpdateView.as_view()),
    path('jurisdictions/<int:jurisdiction_id>/rates/history/', RateHistoryView.as_view()),
    path('calculate/', CalculateView.as_view()),
    path('calculations/', CalculationAuditView.as_view()),
    # R2: AGT IVA filing report (admin-only).
    path('report/agt/', AGTReportView.as_view(), name='tax-agt-report'),
]
