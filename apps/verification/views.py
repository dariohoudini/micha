from rest_framework import generics, permissions, status
from rest_framework.response import Response
from django.utils import timezone

from .models import SellerVerification
from .serializers import SellerVerificationSerializer


class ApplySellerVerificationView(generics.CreateAPIView):
    serializer_class = SellerVerificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user

        if hasattr(user, 'verification'):
            return Response(
                {"detail": "Verification already submitted."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        verification = serializer.save(
            user=user,
            status='approved',  # auto-approval for now
            last_selfie_update=timezone.now()
        )

        # Update user seller flags
        user.is_seller = True
        user.is_verified_seller = True
        user.save()

        return Response(
            {"detail": "Seller verification approved."},
            status=status.HTTP_201_CREATED
        )
