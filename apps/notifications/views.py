"""
Notifications Views
FIX: FeedCursorPagination used — no duplicates on infinite scroll
     Page-based pagination breaks when new notifications arrive between pages
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, serializers
from django.utils import timezone

from apps.users.permissions import IsNotSuspended
from middleware.pagination import FeedCursorPagination
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "type", "title", "message", "is_read", "read_at", "data", "created_at"]
        read_only_fields = fields


class NotificationListView(APIView):
    """
    GET /api/notifications/
    FIX: Cursor pagination — no duplicates when new notifications arrive
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get(self, request):
        qs = Notification.objects.filter(user=request.user).order_by("-created_at")
        paginator = FeedCursorPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = NotificationSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class UnreadCountView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(user=request.user, is_read=False).count()
        return Response({"unread_count": count})


class MarkReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        from django.shortcuts import get_object_or_404
        notification = get_object_or_404(Notification, pk=pk, user=request.user)
        notification.mark_read()
        return Response({"detail": "Marked as read."})


class MarkAllReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        Notification.objects.filter(
            user=request.user, is_read=False
        ).update(is_read=True, read_at=timezone.now())
        return Response({"detail": "All notifications marked as read."})
