from rest_framework import generics, permissions
from django.shortcuts import get_object_or_404
from apps.users.models import User
from .models import AdminAction
from .serializers import AdminActionSerializer


class AdminActionCreateView(generics.CreateAPIView):
    serializer_class = AdminActionSerializer
    permission_classes = [permissions.IsAdminUser]

    def perform_create(self, serializer):
        action = serializer.validated_data["action"]
        target = serializer.validated_data["target"]

        if action == "warn":
            target.status = "warned"

        elif action == "suspend":
            target.status = "suspended"

        elif action == "ban":
            target.status = "banned"
            target.is_active = False

        target.save()
        serializer.save()
