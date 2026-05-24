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
from .device_models import DeviceToken
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


class SESWebhookView(APIView):
    """POST /api/v1/notifications/ses-webhook/

    Receives bounce + complaint notifications from Amazon SES via SNS.
    Routes hard bounces and spam complaints to the suppression list so
    we stop sending to addresses that bounce or get flagged — without
    this, our SES sending reputation tanks and AWS suspends the
    sending account.

    Authentication
    ───────────────
    SNS signs every message with an RSA key whose certificate is
    published at a *.amazonaws.com URL. apps.notifications.ses_webhook
    verifies the signature against the canonical SNS message string
    (RSA-PKCS1v15 / SHA1 or SHA256 depending on SignatureVersion).

    If the ``cryptography`` package isn't deployed, the verifier falls
    back to source-IP allowlist (settings.WEBHOOK_ALLOWED_IPS['ses'])
    — defence in depth, populated from AWS's published SNS egress IPs.

    Idempotency
    ───────────
    Suppression-list inserts use get_or_create — duplicate notifications
    are a no-op. SNS message_id replay protection is on the to-do list
    for the inbound_webhooks integration commit; for now, idempotent
    suppression is the structural guarantee.

    Response codes
    ───────────────
      200 — handled (subscribed / suppressed / logged / ignored)
      400 — envelope malformed / signature failed
    """
    from rest_framework.permissions import AllowAny
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        from .ses_webhook import process_sns_envelope, SNSError
        import json as _json

        # SNS sends Content-Type: text/plain even for JSON bodies, so
        # rely on raw body bytes rather than DRF's content negotiator.
        body = request.body or b''
        if not body:
            return Response({'error': 'empty_body'}, status=400)
        try:
            envelope = _json.loads(body.decode('utf-8'))
        except Exception:
            return Response({'error': 'invalid_json'}, status=400)

        try:
            result = process_sns_envelope(envelope)
        except SNSError as e:
            return Response({'error': 'sns_error', 'detail': str(e)}, status=400)

        return Response({'detail': 'ok', 'result': result})


# ─── R5: Push device registration ────────────────────────────────────

class PushTokenSerializer(serializers.Serializer):
    """Payload accepted by /push/register/.

    ``platform`` is best-effort — the frontend sends Capacitor's
    ``getPlatform()`` which returns 'ios' / 'android' / 'web'. Unknown
    values are normalised to 'web'.
    """
    token = serializers.CharField(min_length=10, max_length=4096)
    platform = serializers.CharField(
        required=False, allow_blank=True, default='', max_length=20,
    )
    device_info = serializers.DictField(
        required=False, default=dict,
    )

    def validate_platform(self, value: str) -> str:
        v = (value or '').strip().lower()
        if v in ('ios', 'android', 'web'):
            return v
        # Frontend sometimes sends "iphone" / "ipad" — map to ios.
        if v in ('iphone', 'ipad'):
            return 'ios'
        return 'web'


class PushTokenRegisterView(APIView):
    """POST /api/v1/notifications/push/register/

    Frontend (Capacitor PushNotifications.addListener('registration'))
    calls this with the FCM/APNs token. Behaviour:

      • Token already registered to THIS user → idempotent: update
        platform + last_seen_at + reactivate if previously deactivated.
      • Token registered to a DIFFERENT user → reassign FK (someone
        logged out + new user logged in on the same device). Audit
        log entry would be nice — out of scope here, the reassign
        itself is the audit (the old user no longer receives pushes).
      • Brand new token → create row.

    Auth required. Suspended users can still register (a suspended
    user might still need account-status notifications).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        ser = PushTokenSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        token = ser.validated_data['token'].strip()
        platform = ser.validated_data['platform'] or 'web'
        device_info = ser.validated_data.get('device_info') or {}

        existing = DeviceToken.objects.filter(token=token).first()
        if existing is None:
            DeviceToken.objects.create(
                user=request.user,
                token=token,
                platform=platform,
                device_info=device_info,
            )
            return Response({'detail': 'registered', 'created': True}, status=201)

        # Existing row — reactivate / reassign as needed.
        changed_fields = []
        if existing.user_id != request.user.pk:
            existing.user = request.user
            changed_fields.append('user')
        if existing.platform != platform:
            existing.platform = platform
            changed_fields.append('platform')
        if not existing.is_active:
            existing.is_active = True
            existing.deactivation_reason = ''
            changed_fields.extend(['is_active', 'deactivation_reason'])
        if device_info:
            existing.device_info = device_info
            changed_fields.append('device_info')
        # Always bump last_seen on a register call.
        existing.last_seen_at = timezone.now()
        changed_fields.append('last_seen_at')
        existing.save(update_fields=list(set(changed_fields + ['updated_at'])))
        return Response({'detail': 'registered', 'created': False}, status=200)


class PushTokenUnregisterView(APIView):
    """POST /api/v1/notifications/push/unregister/

    Called from the frontend on logout. Deactivates (soft-deletes) the
    token. Accepts ``{token}`` in the body OR no body — in the latter
    case, deactivates ALL tokens for the calling user. The "all"
    behaviour is useful when the frontend has lost the token reference
    but knows the user is signing out.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        token = (request.data.get('token') or '').strip()
        qs = DeviceToken.objects.filter(user=request.user, is_active=True)
        if token:
            qs = qs.filter(token=token)
        count = 0
        for t in qs:
            t.deactivate(reason='logout')
            count += 1
        return Response({'detail': 'unregistered', 'deactivated': count})
