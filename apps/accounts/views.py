from rest_framework import generics, permissions, status
from rest_framework.response import Response
from .models import Block
from .serializers import BlockSerializer


class BlockUserView(generics.CreateAPIView):
    serializer_class = BlockSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_context(self):
        return {"request": self.request}


class UnblockUserView(generics.DestroyAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, user_id):
        Block.objects.filter(
            blocker=request.user,
            blocked_id=user_id
        ).delete()
        return Response(
            {"detail": "User unblocked"},
            status=status.HTTP_204_NO_CONTENT
        )


class BlockedUsersListView(generics.ListAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = BlockSerializer

    def get_queryset(self):
        return Block.objects.filter(blocker=self.request.user)
