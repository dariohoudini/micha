from rest_framework import generics, permissions, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from .serializers import UserRegisterSerializer, UserSerializer, MyTokenObtainPairSerializer
from apps.seller.models import SellerVerification
from apps.seller.serializers import SellerVerificationSerializer
from .permissions import IsNotSuspended

User = get_user_model()

# -------------------
# Seller Permissions
# -------------------
class IsSellerOrSuperuser(permissions.BasePermission):
    """
    Allows access only to sellers or superusers.
    """
    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return getattr(user, 'is_seller', False) or user.is_superuser


# -------------------
# Seller Views
# -------------------
class SellerVerificationView(generics.RetrieveUpdateAPIView):
    serializer_class = SellerVerificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        obj, created = SellerVerification.objects.get_or_create(user=self.request.user)
        return obj


class SellerDashboardView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser]

    def get(self, request):
        user = request.user
        if not getattr(user, 'is_seller', False) and not user.is_superuser:
            return Response({"detail": "You do not have permission to view this."}, status=403)

        data = {
            "user_id": user.id,
            "email": user.email,
            "is_seller": getattr(user, 'is_seller', False),
            "message": "Welcome to your seller dashboard!"
        }
        return Response(data)


# -------------------
# JWT Views
# -------------------
class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


class MyTokenRefreshView(TokenRefreshView):
    pass


# -------------------
# User Views
# -------------------
class UserRegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = UserRegisterSerializer
    permission_classes = [permissions.AllowAny]


class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get_object(self):
        return self.request.user