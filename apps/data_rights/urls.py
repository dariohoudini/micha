from django.urls import path
from .views import DataRequestView, DataRequestDetailView
from .consent_views import CookieConsentView, CookieConsentWithdrawView

urlpatterns = [
    path('', DataRequestView.as_view(), name='data-request-list'),
    path('<int:pk>/', DataRequestDetailView.as_view(),
         name='data-request-detail'),

    # R6: cookie consent (GDPR Art.7 + Lei 22/11).
    path('consent/', CookieConsentView.as_view(), name='cookie-consent'),
    path('consent/withdraw/', CookieConsentWithdrawView.as_view(),
         name='cookie-consent-withdraw'),
]
