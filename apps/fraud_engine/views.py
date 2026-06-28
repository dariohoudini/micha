from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import FraudDecision, IpReputation, VelocityRule


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        u = getattr(request, 'user', None)
        return bool(u and u.is_authenticated and getattr(u, 'is_staff', False))


@api_view(['POST'])
@permission_classes([AllowAny])
def register_device_view(request):
    """POST /devices/register  body:
    {ua, language, screen, timezone, platform, canvas_hash}.
    Returns the fingerprint hash."""
    fp = services.register_device(
        ua=request.data.get('ua') or request.META.get('HTTP_USER_AGENT', ''),
        language=request.data.get('language', ''),
        screen=request.data.get('screen', ''),
        timezone_str=request.data.get('timezone', ''),
        platform=request.data.get('platform', ''),
        canvas_hash=request.data.get('canvas_hash', ''),
    )
    if request.user.is_authenticated:
        services.link_device_to_user(device_hash=fp, user=request.user)
    return Response({'fingerprint': fp})


@api_view(['POST'])
@permission_classes([IsAdmin])
def evaluate_view(request):
    """Admin/internal — explicit evaluate call. Body: {action, user_id, ip,
    device_hash, email, amount}."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = None
    if request.data.get('user_id'):
        user = User.objects.filter(pk=request.data['user_id']).first()
    d = services.evaluate_fraud(
        action=request.data.get('action', 'signup'),
        user=user, ip=request.data.get('ip', ''),
        device_hash=request.data.get('device_hash', ''),
        email=request.data.get('email', ''),
        amount=request.data.get('amount'),
    )
    return Response({
        'decision_id': str(d.id), 'decision': d.decision,
        'score': d.score, 'reasons': d.reasons,
    })


class AdminFraudDecisionsView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        rows = FraudDecision.objects.values(
            'id', 'action', 'user_id', 'ip_address', 'score',
            'decision', 'reasons', 'created_at',
        )[:100]
        return Response(list(rows))


class AdminRulesView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        rows = VelocityRule.objects.values(
            'id', 'name', 'action', 'is_active', 'scope',
            'window_seconds', 'max_count', 'on_exceed', 'score_weight',
        )
        return Response(list(rows))


class AdminIpReputationView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        rows = IpReputation.objects.values(
            'ip_address', 'score', 'external_score',
            'distinct_users_24h', 'failed_logins_1h', 'chargebacks_30d',
            'is_datacenter', 'is_tor', 'is_proxy', 'is_manual_block',
            'country', 'last_seen_at',
        )[:200]
        return Response(list(rows))

    def post(self, request):
        obj = services.upsert_ip_reputation(
            ip=request.data['ip'],
            external_score=int(request.data.get('external_score', 0)),
            country=request.data.get('country', ''),
            is_datacenter=bool(request.data.get('is_datacenter', False)),
            is_tor=bool(request.data.get('is_tor', False)),
            is_proxy=bool(request.data.get('is_proxy', False)),
            manual_block=bool(request.data.get('manual_block', False)),
        )
        return Response({'ip': obj.ip_address})
