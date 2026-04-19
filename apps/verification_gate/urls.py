"""
apps/verification_gate/urls.py
"""
from django.urls import path
from . import views

urlpatterns = [
    # Seller-facing
    path('status/', views.VerificationStatusView.as_view()),
    path('submit/', views.SubmitVerificationView.as_view()),
    path('monthly-selfie/', views.SubmitMonthlySelfieView.as_view()),

    # Admin-facing
    path('admin/list/', views.AdminVerificationListView.as_view()),
    path('admin/<uuid:verification_id>/action/', views.AdminVerificationActionView.as_view()),
    path('admin/selfies/', views.AdminMonthlySelfieListView.as_view()),
    path('admin/selfies/<uuid:selfie_id>/action/', views.AdminMonthlySelfieActionView.as_view()),
]
