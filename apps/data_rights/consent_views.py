"""
Cookie consent endpoints (R6).

GET  /api/v1/account/data-request/consent/
POST /api/v1/account/data-request/consent/
POST /api/v1/account/data-request/consent/withdraw/
"""
from __future__ import annotations

from rest_framework import permissions, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from .cookie_consent import (
    latest_consent, record_consent, withdraw as withdraw_consent,
)


class _ConsentPayload(serializers.Serializer):
    analytics = serializers.BooleanField(required=False, default=False)
    marketing = serializers.BooleanField(required=False, default=False)
    preferences = serializers.BooleanField(required=False, default=False)
    consent_key = serializers.CharField(required=False, allow_blank=True,
                                        default='', max_length=64)
    policy_version = serializers.CharField(required=False, allow_blank=True,
                                           default='v1', max_length=20)


def _serialize(row):
    if row is None:
        return {
            'analytics': False, 'marketing': False, 'preferences': False,
            'has_consent': False, 'withdrawn_at': None,
        }
    return {
        'id': row.pk,
        'analytics': row.analytics,
        'marketing': row.marketing,
        'preferences': row.preferences,
        'policy_version': row.policy_version,
        'has_consent': row.withdrawn_at is None and (
            row.analytics or row.marketing or row.preferences
        ),
        'created_at': row.created_at.isoformat(),
        'withdrawn_at': row.withdrawn_at.isoformat() if row.withdrawn_at else None,
    }


class CookieConsentView(APIView):
    """GET returns the latest consent state.
    POST records a new one.

    Anonymous callers identify via ``consent_key`` in body/query.
    Authenticated callers use request.user; consent_key optional and
    merged on login (operator job — out of this commit's scope).
    """
    permission_classes = [permissions.AllowAny]
    # authentication_classes left as default — JWT auth still runs
    # so an authenticated user is recognised; AllowAny ensures
    # anonymous callers aren't refused.

    def get(self, request):
        user = request.user if getattr(request, 'user', None) \
            and getattr(request.user, 'is_authenticated', False) else None
        consent_key = request.query_params.get('consent_key', '')
        row = latest_consent(user=user, consent_key=consent_key)
        return Response(_serialize(row))

    def post(self, request):
        ser = _ConsentPayload(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data

        user = request.user if getattr(request, 'user', None) \
            and getattr(request.user, 'is_authenticated', False) else None
        row = record_consent(
            user=user,
            consent_key=v.get('consent_key', ''),
            analytics=v['analytics'],
            marketing=v['marketing'],
            preferences=v['preferences'],
            request=request,
            policy_version=v.get('policy_version', 'v1') or 'v1',
        )
        return Response(_serialize(row), status=201)


class CookieConsentWithdrawView(APIView):
    """POST .../withdraw/ — single-call clear of all non-essential consent."""
    permission_classes = [permissions.AllowAny]
    # JWT auth still tried; AllowAny lets anon pass.

    def post(self, request):
        user = request.user if getattr(request, 'user', None) \
            and getattr(request.user, 'is_authenticated', False) else None
        consent_key = request.data.get('consent_key') or ''
        if user is None and not consent_key:
            return Response(
                {'error': 'validation_error',
                 'detail': 'consent_key required for anonymous withdrawal.'},
                status=400,
            )
        row = withdraw_consent(user=user, consent_key=consent_key,
                               request=request)
        return Response(_serialize(row))
