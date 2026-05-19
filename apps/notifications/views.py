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


class UnsubscribeView(APIView):
    """GET/POST /api/v1/notifications/unsubscribe/?email=&sig=&v=

    RFC 8058 one-click unsubscribe. NO authentication — the HMAC
    signature IS the auth. Required because real-world recipients
    unsubscribe from their phone's email client without re-logging-in.

    Both GET and POST are accepted:
      • GET so a plain email-client link works
      • POST so RFC 8058 'List-Unsubscribe-Post: One-Click' header
        machinery (used by Gmail/Outlook automated unsub) can fire

    Idempotent — re-clicking the same link is a no-op (already
    suppressed → stay suppressed).
    """
    from rest_framework.permissions import AllowAny
    permission_classes = [AllowAny]
    # Disable any default authentication so an HMAC-token request from
    # an anonymous email client doesn't get rejected by JWT validation.
    authentication_classes = []

    def get(self, request):
        return self._handle(request)

    def post(self, request):
        return self._handle(request)

    def _handle(self, request):
        from .unsubscribe import verify_unsubscribe
        from .preferences import suppress
        email = (request.query_params.get('email')
                 or request.data.get('email') or '').strip().lower()
        sig = (request.query_params.get('sig')
               or request.data.get('sig') or '').strip()
        version = (request.query_params.get('v')
                   or request.data.get('v') or 'v1').strip()
        if not email or not sig:
            return Response({'error': 'validation_error',
                             'detail': 'email + sig required.'},
                            status=400)
        if not verify_unsubscribe(email, sig, version):
            # Same response for "bad sig" and "email mismatch" so we
            # don't leak whether an email is on our platform.
            return Response({'error': 'invalid_token',
                             'detail': 'Invalid unsubscribe link.'},
                            status=400)
        suppress(email, reason='unsubscribe', source='unsubscribe_link')
        return Response({'detail': 'You have been unsubscribed.',
                         'email': email})


