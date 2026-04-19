from django.urls import path
from .views import (
    WalletView, WalletTransactionListView,
    BankAccountListCreateView, BankAccountDetailView,
    RequestPayoutView, AdminPayoutListView, AdminPayoutActionView,
    WebhookView,
)


urlpatterns = [
    path("wallet/", WalletView.as_view(), name="wallet"),
    path("wallet/transactions/", WalletTransactionListView.as_view(), name="wallet-transactions"),
    path("bank-accounts/", BankAccountListCreateView.as_view(), name="bank-accounts"),
    path("bank-accounts/<int:pk>/", BankAccountDetailView.as_view(), name="bank-account-detail"),
    path("payout/request/", RequestPayoutView.as_view(), name="request-payout"),
    path("payout/admin/", AdminPayoutListView.as_view(), name="admin-payouts"),
    path("payout/admin/<uuid:pk>/", AdminPayoutActionView.as_view(), name="admin-payout-action"),
    path("webhook/", WebhookView.as_view(), name="payment-webhook"),
]
