from django.urls import path

from . import views

app_name = 'payments_angola'

urlpatterns = [
    # CH3 COD eligibility
    path('cod/eligibility/', views.CodEligibilityView.as_view(),
         name='cod-eligibility'),
    # CH5/6/7 flow creation + status
    path('flows/', views.CreateFlowView.as_view(), name='create-flow'),
    path('flows/<uuid:flow_id>/', views.FlowStatusView.as_view(),
         name='flow-status'),
    # CH7 bank proof
    path('flows/<uuid:flow_id>/proof/', views.BankProofUploadView.as_view(),
         name='bank-proof-upload'),
    # CH9/10 wallet + P2P
    path('wallet/balance/', views.WalletBalanceView.as_view(),
         name='wallet-balance'),
    path('wallet/transfer/', views.P2PTransferView.as_view(), name='p2p'),
    # CH17 webhook
    path('webhooks/appypay/', views.AppypayWebhookView.as_view(),
         name='appypay-webhook'),
    # admin / finance
    path('admin/proofs/', views.BankProofReviewView.as_view(),
         name='proof-review'),
    path('admin/proofs/<int:proof_id>/decision/',
         views.BankProofReviewView.as_view(), name='proof-decision'),
    path('admin/remittances/', views.CourierRemittanceView.as_view(),
         name='remittances'),
    path('admin/kpis/', views.KpiView.as_view(), name='kpis'),
]
