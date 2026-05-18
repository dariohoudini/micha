from rest_framework import generics, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import FraudAlert, IPBan, BannedKeyword, ContentModerationFlag
from apps.users.permissions import IsAdminOrSuperuser


class FraudAlertSerializer(serializers.ModelSerializer):
    user_email = serializers.ReadOnlyField(source='user.email')

    class Meta:
        model = FraudAlert
        fields = ['id', 'user_email', 'order', 'type', 'severity', 'description', 'is_resolved', 'created_at']


class IPBanSerializer(serializers.ModelSerializer):
    class Meta:
        model = IPBan
        fields = ['id', 'ip_address', 'reason', 'expires_at', 'created_at']


class BannedKeywordSerializer(serializers.ModelSerializer):
    class Meta:
        model = BannedKeyword
        fields = ['id', 'keyword', 'severity', 'created_at']


class ContentFlagSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContentModerationFlag
        fields = ['id', 'content_type', 'content_id', 'reason', 'keyword_matched', 'is_resolved', 'action_taken', 'created_at']


class FraudAlertListView(generics.ListAPIView):
    """GET /api/security/fraud-alerts/ — Admin views all fraud alerts."""
    serializer_class = FraudAlertSerializer
    permission_classes = [IsAdminOrSuperuser]

    def get_queryset(self):
        qs = FraudAlert.objects.all()
        severity = self.request.query_params.get('severity')
        if severity:
            qs = qs.filter(severity=severity)
        return qs.filter(is_resolved=False)


class ResolveFraudAlertView(APIView):
    """PATCH /api/security/fraud-alerts/<id>/resolve/"""
    permission_classes = [IsAdminOrSuperuser]

    def patch(self, request, pk):
        alert = get_object_or_404(FraudAlert, pk=pk)
        alert.is_resolved = True
        alert.resolved_by = request.user
        alert.resolved_at = timezone.now()
        alert.save()
        return Response({"detail": "Fraud alert resolved."})


class IPBanListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/security/ip-bans/"""
    serializer_class = IPBanSerializer
    permission_classes = [IsAdminOrSuperuser]
    queryset = IPBan.objects.all()

    def perform_create(self, serializer):
        serializer.save(banned_by=self.request.user)


class IPBanDeleteView(generics.DestroyAPIView):
    """DELETE /api/security/ip-bans/<id>/"""
    permission_classes = [IsAdminOrSuperuser]
    queryset = IPBan.objects.all()


class BannedKeywordListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/security/banned-keywords/"""
    serializer_class = BannedKeywordSerializer
    permission_classes = [IsAdminOrSuperuser]
    queryset = BannedKeyword.objects.all()


class ContentFlagListView(generics.ListAPIView):
    """GET /api/security/content-flags/"""
    serializer_class = ContentFlagSerializer
    permission_classes = [IsAdminOrSuperuser]

    def get_queryset(self):
        return ContentModerationFlag.objects.filter(is_resolved=False)


class ResolveContentFlagView(APIView):
    """PATCH /api/security/content-flags/<id>/resolve/"""
    permission_classes = [IsAdminOrSuperuser]

    def patch(self, request, pk):
        flag = get_object_or_404(ContentModerationFlag, pk=pk)
        flag.is_resolved = True
        flag.action_taken = request.data.get('action_taken', '')
        flag.save()
        return Response({"detail": "Flag resolved."})


class AdminUnlockAccountView(APIView):
    """POST /api/security/unlock-account/  body: {email}

    Support tool. Clears the cache-side lockout AND the legacy DB-side
    counter for a single user. Audited via AdminActionLog so we know
    which admin unlocked whom.

    Use when:
      • A legitimate user calls support after being locked out and
        can't wait for the TTL.
      • A pen-test or bulk import triggered a false-positive lockout.
    """
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request):
        from apps.security.lockout import clear_lockout
        from django.contrib.auth import get_user_model
        email = (request.data.get('email') or '').strip().lower()
        if not email:
            return Response(
                {'error': 'validation_error', 'detail': 'email required.'},
                status=400,
            )
        was_locked = clear_lockout(email, reason=f'admin:{request.user.id}')
        UserModel = get_user_model()
        user = UserModel.objects.filter(email=email).first()
        if user is not None:
            UserModel.objects.filter(pk=user.pk).update(
                failed_login_attempts=0, locked_until=None,
            )
        try:
            from apps.admin_actions.models import AdminActionLog
            AdminActionLog.log(
                request, 'admin_unlock_account', user,
                metadata={'email': email, 'was_locked': was_locked},
            )
        except Exception:
            pass
        return Response({
            'detail': 'Account unlocked.' if was_locked
                      else 'Account was not locked; counter cleared.',
            'was_locked': was_locked,
        })


class LoginAttemptHistoryView(APIView):
    """GET /api/security/login-attempts/?email=<email>&limit=50

    Admin forensic view: walks the LoginAttempt audit table for one
    email. Use during incident response to see the actual hit pattern
    (IPs, timing, UAs) — not just the lockout state.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        from apps.security.login_attempt_models import LoginAttempt
        email = (request.query_params.get('email') or '').strip().lower()
        try:
            limit = min(int(request.query_params.get('limit', 50)), 500)
        except (TypeError, ValueError):
            limit = 50
        if not email:
            return Response(
                {'error': 'validation_error', 'detail': 'email required.'},
                status=400,
            )
        rows = (
            LoginAttempt.objects.filter(email=email)
            .order_by('-created_at')[:limit]
            .values('ip', 'user_agent', 'succeeded', 'failure_reason',
                    'triggered_lockout', 'created_at')
        )
        return Response({'results': list(rows)})


# URLs
from django.urls import path

urlpatterns = [
    path('fraud-alerts/', FraudAlertListView.as_view(), name='fraud-alerts'),
    path('fraud-alerts/<int:pk>/resolve/', ResolveFraudAlertView.as_view(), name='resolve-fraud'),
    path('ip-bans/', IPBanListCreateView.as_view(), name='ip-bans'),
    path('ip-bans/<int:pk>/', IPBanDeleteView.as_view(), name='ip-ban-delete'),
    path('banned-keywords/', BannedKeywordListCreateView.as_view(), name='banned-keywords'),
    path('content-flags/', ContentFlagListView.as_view(), name='content-flags'),
    path('content-flags/<int:pk>/resolve/', ResolveContentFlagView.as_view(), name='resolve-flag'),
    path('unlock-account/', AdminUnlockAccountView.as_view(), name='admin-unlock-account'),
    path('login-attempts/', LoginAttemptHistoryView.as_view(), name='login-attempts'),
]
