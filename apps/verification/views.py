from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import SellerVerification, VerificationLog
from .serializers import (
    SellerVerificationSerializer,
    SelfieUpdateSerializer,
    AdminVerificationActionSerializer,
)
from apps.users.permissions import IsNotSuspended, IsAdminOrSuperuser


class ApplySellerVerificationView(generics.CreateAPIView):
    """
    POST /api/verification/apply/
    Submit seller verification documents. Status starts as 'pending'.
    Admin must approve before seller flags are set.
    """
    serializer_class = SellerVerificationSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request, *args, **kwargs):
        user = request.user

        if hasattr(user, 'verification'):
            existing = user.verification
            if existing.status in ('pending', 'approved'):
                return Response(
                    {"detail": f"Verification already exists with status: {existing.status}."},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # Allow resubmission if rejected/expired
            existing.delete()

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        verification = serializer.save(user=user)

        VerificationLog.objects.create(
            verification=verification,
            action='submitted',
            note='Verification documents submitted by seller.',
        )

        return Response(
            {"detail": "Verification submitted. Awaiting admin review."},
            status=status.HTTP_201_CREATED
        )


class MyVerificationStatusView(generics.RetrieveAPIView):
    """GET /api/verification/status/ — Check own verification status."""
    serializer_class = SellerVerificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return get_object_or_404(SellerVerification, user=self.request.user)


class UpdateSelfieView(APIView):
    """
    POST /api/verification/selfie/
    Update monthly selfie to keep verification active.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request):
        verification = get_object_or_404(SellerVerification, user=request.user)

        if verification.status != 'approved':
            return Response(
                {"detail": "Only approved sellers can update their selfie."},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = SelfieUpdateSerializer(verification, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        VerificationLog.objects.create(
            verification=verification,
            action='selfie_updated',
            note='Monthly selfie updated.',
        )

        return Response({"detail": "Selfie updated successfully."}, status=status.HTTP_200_OK)


class AdminVerificationListView(generics.ListAPIView):
    """GET /api/verification/admin/ — List all verifications (admin only)."""
    serializer_class = SellerVerificationSerializer
    permission_classes = [IsAdminOrSuperuser]

    def get_queryset(self):
        status_filter = self.request.query_params.get('status')
        qs = SellerVerification.objects.select_related('user').prefetch_related('logs')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs.order_by('-created_at')


class AdminVerificationActionView(APIView):
    """
    POST /api/verification/admin/<id>/action/
    Admin approves, rejects, or suspends a seller verification.
    """
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, pk):
        verification = get_object_or_404(SellerVerification, pk=pk)
        serializer = AdminVerificationActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data['action']
        note = serializer.validated_data.get('note', '')

        verification.status = action
        verification.rejection_reason = note if action == 'rejected' else None
        verification.save()

        # Sync user flags
        user = verification.user
        if action == 'approved':
            user.is_seller = True
            user.is_verified_seller = True
        elif action in ('rejected', 'suspended', 'expired'):
            user.is_verified_seller = False
        user.save()

        VerificationLog.objects.create(
            verification=verification,
            action=action,
            note=note,
            performed_by=request.user,
        )

        return Response(
            {"detail": f"Verification {action} successfully."},
            status=status.HTTP_200_OK
        )
