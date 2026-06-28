from django.urls import path

from . import views

app_name = 'seller_tools'

urlpatterns = [
    # CH3 bulk edit + revert
    path('bulk-edit/', views.BulkEditView.as_view(), name='bulk-edit'),
    path('bulk-edit/<int:job_id>/revert/', views.BulkEditRevertView.as_view(),
         name='bulk-edit-revert'),
    # CH8 return policy
    path('return-policies/', views.ReturnPolicyView.as_view(),
         name='return-policies'),
    # CH9 holiday mode
    path('holiday-mode/', views.HolidayModeView.as_view(), name='holiday-mode'),
    # CH10 Q&A helpfulness
    path('qa/<int:qa_id>/vote/', views.QaVoteView.as_view(), name='qa-vote'),
    # CH11 followers + broadcast
    path('stores/<int:seller_id>/follow/', views.FollowStoreView.as_view(),
         name='follow-store'),
    path('broadcasts/', views.BroadcastView.as_view(), name='broadcasts'),
    # CH12 commission statements
    path('commission-statements/', views.CommissionStatementView.as_view(),
         name='commission-statements'),
    # CH13 listing quality score
    path('listings/<int:product_id>/quality/',
         views.ListingQualityView.as_view(), name='listing-quality'),
    # CH14 price competitiveness
    path('listings/<int:product_id>/price-competitiveness/',
         views.PriceCompetitivenessView.as_view(),
         name='price-competitiveness'),
    # CH17 VAT
    path('vat-registrations/', views.VatRegistrationView.as_view(),
         name='vat-registrations'),
    # CH18 multi-store
    path('linked-stores/', views.LinkedStoresView.as_view(),
         name='linked-stores'),
    # CH19 dispute appeal
    path('disputes/<int:dispute_id>/appeal/', views.DisputeAppealView.as_view(),
         name='dispute-appeal'),
    # CH20 payout config
    path('payout/bank-accounts/', views.BankAccountView.as_view(),
         name='bank-accounts'),
    path('payout/withdraw/', views.WithdrawView.as_view(), name='withdraw'),
    # CH22 compliance labels
    path('listings/<int:product_id>/compliance/',
         views.ComplianceLabelView.as_view(), name='compliance-label'),
    # CH23 API quota
    path('api-quota/', views.QuotaStatusView.as_view(), name='api-quota'),
    # CH24 KPIs
    path('kpis/', views.KpiView.as_view(), name='kpis'),
]
