from django.urls import path
from .views import (
    PayoutScheduleView, WalletView, WalletTransactionListView,
    BankAccountListCreateView,
    BankAccountDetailView, RequestPayoutView,
    AdminPayoutListView, AdminPayoutActionView,
    WebhookView,
)
from .chargeback_views import (
    ChargebackInboundView, ChargebackListView, ChargebackDetailView,
    ChargebackRespondView, ChargebackAcceptView, ChargebackResolveView,
)
from .settlement_views import (
    SettlementUploadView, SettlementRunListView, SettlementRunDetailView,
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
    path("payouts/schedule/", PayoutScheduleView.as_view(), name="payout-schedule"),

    # R2: chargeback workflow (PSP inbound + admin handling).
    path("chargebacks/inbound/", ChargebackInboundView.as_view(),
         name="chargeback-inbound"),
    path("chargebacks/", ChargebackListView.as_view(),
         name="chargeback-list"),
    path("chargebacks/<int:pk>/", ChargebackDetailView.as_view(),
         name="chargeback-detail"),
    path("chargebacks/<int:pk>/respond/", ChargebackRespondView.as_view(),
         name="chargeback-respond"),
    path("chargebacks/<int:pk>/accept/", ChargebackAcceptView.as_view(),
         name="chargeback-accept"),
    path("chargebacks/<int:pk>/resolve/", ChargebackResolveView.as_view(),
         name="chargeback-resolve"),

    # R2: PSP settlement reconciliation (admin only).
    path("settlement/upload/", SettlementUploadView.as_view(),
         name="settlement-upload"),
    path("settlement/runs/", SettlementRunListView.as_view(),
         name="settlement-runs"),
    path("settlement/runs/<int:pk>/", SettlementRunDetailView.as_view(),
         name="settlement-run-detail"),
]
