from django.urls import path
from .views import IssueCardView, ClaimCardView, MyCardsView, CardDetailView

urlpatterns = [
    path('issue/', IssueCardView.as_view(), name='gift-cards-issue'),
    path('claim/', ClaimCardView.as_view(), name='gift-cards-claim'),
    path('me/', MyCardsView.as_view(), name='gift-cards-me'),
    path('<int:pk>/', CardDetailView.as_view(), name='gift-cards-detail'),
]
