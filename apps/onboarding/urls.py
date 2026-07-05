from django.urls import path
from . import views

urlpatterns = [
    path('guest/session/', views.GuestSessionView.as_view(), name='guest-session'),
    path('guest/profile/', views.GuestProfileView.as_view(), name='guest-profile'),
    path('onboarding/interests/', views.OnboardingInterestsView.as_view(),
         name='onboarding-interests'),
    path('onboarding/complete/', views.OnboardingCompleteView.as_view(),
         name='onboarding-complete'),
]
