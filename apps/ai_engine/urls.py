"""
apps/ai_engine/urls.py
"""
from django.urls import path
from . import views
from .content_views import (
    GenerateProductDescriptionView,
    TranslateProductView,
    ImproveDescriptionView,
    SummariseReviewsView,
)

urlpatterns = [
    path('onboarding-quiz/', views.OnboardingQuizView.as_view()),
    path('feed/', views.HyperPersonalisedFeedView.as_view(), name='hyper-feed'),
    # Product PK is an int (BigAutoField) — the <uuid:> converter meant
    # this route could NEVER match a real product id (permanent 404).
    path('similar/<int:product_id>/', views.SimilarProductsView.as_view()),
    path('event/', views.TrackEventView.as_view()),
    path('search/', views.SmartSearchView.as_view()),
    path('chat/start/', views.AIChatStartView.as_view()),
    path('chat/<uuid:conversation_id>/', views.AIChatMessageView.as_view()),
    path('price-watch/', views.WatchPriceView.as_view()),
    path('price-watch/<uuid:product_id>/', views.WatchPriceView.as_view()),
    path('size/', views.SizeRecommendationView.as_view()),
    path('size-profile/', views.SizeProfileView.as_view()),
    path('taste-profile/', views.TasteProfileView.as_view()),
    path('notification-preferences/', views.NotificationPreferenceView.as_view()),
    path('flash-sale-target/', views.FlashSaleTargetView.as_view()),
    path('admin/stats/', views.AIStatsView.as_view()),
    # Content generation (seller tools)
    path('content/generate-description/', GenerateProductDescriptionView.as_view()),
    path('content/translate/', TranslateProductView.as_view()),
    path('content/improve/', ImproveDescriptionView.as_view()),
    path('content/reviews-summary/<uuid:product_id>/', SummariseReviewsView.as_view()),
]
