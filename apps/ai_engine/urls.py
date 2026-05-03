"""
apps/ai_engine/urls.py
"""
from django.urls import path
from . import views

urlpatterns = [
    path('onboarding-quiz/', views.OnboardingQuizView.as_view()),
    path('feed/', views.HyperPersonalisedFeedView.as_view(), name='hyper-feed'),
    path('similar/<uuid:product_id>/', views.SimilarProductsView.as_view()),
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
]
