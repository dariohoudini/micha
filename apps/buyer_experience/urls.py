from django.urls import path

from . import views

app_name = 'buyer_experience'

urlpatterns = [
    path('gift-options/', views.GiftOptionsView.as_view(), name='gift-options'),
    path('subscriptions/', views.SubscriptionView.as_view(),
         name='subscriptions'),
    path('subscriptions/<uuid:sub_id>/action/',
         views.SubscriptionActionView.as_view(), name='subscription-action'),
    path('products/<str:product_id>/price-history/',
         views.PriceHistoryView.as_view(), name='price-history'),
    path('questions/', views.QuestionView.as_view(), name='questions'),
    path('questions/<uuid:question_id>/answer/',
         views.QuestionAnswerView.as_view(), name='question-answer'),
    path('bulk-inquiries/', views.BulkInquiryView.as_view(),
         name='bulk-inquiries'),
    path('bulk-inquiries/<uuid:inquiry_id>/quote/',
         views.BulkQuoteView.as_view(), name='bulk-quote'),
    path('comparisons/', views.ComparisonView.as_view(), name='comparisons'),
    path('orders/<str:order_id>/reorder-check/',
         views.ReorderCheckView.as_view(), name='reorder-check'),
    path('price-watch/', views.PriceWatchView.as_view(), name='price-watch'),
    path('age-gate/', views.AgeGateView.as_view(), name='age-gate'),
    path('account-summary/', views.AccountSummaryView.as_view(),
         name='account-summary'),
    path('kpis/', views.KpiView.as_view(), name='kpis'),
]
