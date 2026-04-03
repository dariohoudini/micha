from django.urls import path
from .views import ApplySellerVerificationView

urlpatterns = [
    path('apply/', ApplySellerVerificationView.as_view(), name='apply-seller'),
]
