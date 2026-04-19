from rest_framework import generics, permissions, status
from rest_framework.response import Response
from .models import Block
from .serializers import BlockSerializer
from apps.users.permissions import IsNotSuspended


class BlockUserView(generics.CreateAPIView):
    """POST /api/accounts/block/ — Block a user."""
    serializer_class = BlockSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get_serializer_context(self):
        return {'request': self.request}


class UnblockUserView(generics.DestroyAPIView):
    """DELETE /api/accounts/unblock/<user_id>/ — Unblock a user."""
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, user_id):
        deleted, _ = Block.objects.filter(
            blocker=request.user, blocked_id=user_id
        ).delete()
        if deleted:
            return Response({"detail": "User unblocked."}, status=status.HTTP_200_OK)
        return Response({"detail": "Block not found."}, status=status.HTTP_404_NOT_FOUND)


class BlockedUsersListView(generics.ListAPIView):
    """GET /api/accounts/blocked/ — List all users you have blocked."""
    serializer_class = BlockSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Block.objects.filter(blocker=self.request.user).select_related('blocked')
