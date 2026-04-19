"""
apps/ai_engine/urls.py
"""
from django.urls import path
from . import views

urlpatterns = [
    # Onboarding quiz
    path('onboarding-quiz/', views.OnboardingQuizView.as_view()),

    # Personalised feed
    path('feed/', views.PersonalisedFeedView.as_view()),

    # Similar products
    path('similar/<uuid:product_id>/', views.SimilarProductsView.as_view()),

    # Behavioral tracking
    path('event/', views.TrackEventView.as_view()),

    # Smart search
    path('search/', views.SmartSearchView.as_view()),

    # AI Chat
    path('chat/start/', views.AIChatStartView.as_view()),
    path('chat/<uuid:conversation_id>/', views.AIChatMessageView.as_view()),

    # Price drop alerts
    path('price-watch/', views.WatchPriceView.as_view()),
    path('price-watch/<uuid:product_id>/', views.WatchPriceView.as_view()),

    # Size & fit
    path('size/', views.SizeRecommendationView.as_view()),
    path('size-profile/', views.SizeProfileView.as_view()),

    # Profile & preferences
    path('taste-profile/', views.TasteProfileView.as_view()),
    path('notification-preferences/', views.NotificationPreferenceView.as_view()),

    # Admin only
    path('admin/flash-sale-target/', views.FlashSaleTargetView.as_view()),
    path('admin/stats/', views.AIStatsView.as_view()),
]
