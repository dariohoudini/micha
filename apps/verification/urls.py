from django.urls import path
from .views import (
    ApplySellerVerificationView,
    MyVerificationStatusView,
    UpdateSelfieView,
    AdminVerificationListView,
    AdminVerificationActionView,
)

urlpatterns = [
    path('apply/', ApplySellerVerificationView.as_view(), name='verification-apply'),
    path('status/', MyVerificationStatusView.as_view(), name='verification-status'),
    path('selfie/', UpdateSelfieView.as_view(), name='verification-selfie-update'),

    # Admin
    path('admin/', AdminVerificationListView.as_view(), name='admin-verification-list'),
    path('admin/<int:pk>/action/', AdminVerificationActionView.as_view(), name='admin-verification-action'),
]
