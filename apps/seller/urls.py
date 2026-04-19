from django.urls import path
from .views import *
urlpatterns=[
    path('dashboard/',SellerDashboardView.as_view(),name='seller-dashboard'),
    path('profile/',SellerProfileView.as_view(),name='seller-profile'),
    path('faq/',SellerFAQView.as_view(),name='seller-faq'),
    path('faq/<int:pk>/',SellerFAQDetailView.as_view(),name='seller-faq-detail'),
    path('announcements/',SellerAnnouncementView.as_view(),name='seller-announcements'),
    path('holiday/',ToggleHolidayModeView.as_view(),name='toggle-holiday'),
    path('onboarding/',OnboardingView.as_view(),name='onboarding'),
]
