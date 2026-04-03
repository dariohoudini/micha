from django.urls import path
from .views import UserRegisterView, UserProfileView, MyTokenObtainPairView
from rest_framework_simplejwt.views import TokenRefreshView
from .views import SellerDashboardView


urlpatterns = [
    path('register/', UserRegisterView.as_view(), name='user-register'),
    path('login/', MyTokenObtainPairView.as_view(), name='token-obtain-pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('profile/', UserProfileView.as_view(), name='user-profile'),
    path("seller/dashboard/", SellerDashboardView.as_view(), name="seller-dashboard"),

]
