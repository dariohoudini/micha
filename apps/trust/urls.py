from django.urls import path
from . import views

urlpatterns = [
    path('seller/<uuid:seller_id>/', views.SellerTrustScoreView.as_view()),
    path('me/', views.MyTrustScoreView.as_view()),
    path('leaderboard/', views.TrustLeaderboardView.as_view()),
    path('admin/fraud-assess/', views.FraudAssessmentView.as_view()),
]
