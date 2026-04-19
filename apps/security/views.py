from rest_framework import generics, permissions, status, serializers
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
]
