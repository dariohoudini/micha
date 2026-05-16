"""
apps/two_factor/views.py — user-facing 2FA self-service.
"""
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone

from . import service
from .models import UserTOTP, TrustedDevice, BackupCode


def _client_ip(request) -> str:
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return (xff.split(',')[0].strip() if xff else (request.META.get('REMOTE_ADDR') or ''))[:45]


def _ua(request) -> str:
    return (request.META.get('HTTP_USER_AGENT') or '')[:200]


class StartSetupView(APIView):
    """POST /2fa/setup/ — begin enrolment. Returns secret + otpauth URI
    for QR-code rendering on the client."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            out = service.start_setup(request.user)
        except service.TwoFactorError as e:
            return Response({'error': 'tfa_error', 'detail': str(e)}, status=400)
        return Response(out)


class ConfirmSetupView(APIView):
    """POST /2fa/confirm/  body: {code} — verify first code, return backup
    codes ONCE."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        code = (request.data.get('code') or '').strip()
        if not code:
            return Response({'error': 'validation_error',
                             'detail': 'code required'}, status=400)
        try:
            out = service.confirm_setup(
                request.user, code,
                ip=_client_ip(request), ua=_ua(request),
            )
        except service.TwoFactorError as e:
            return Response({'error': 'tfa_error', 'detail': str(e)}, status=400)
        return Response(out)


class ChallengeView(APIView):
    """POST /2fa/challenge/  body: {code, purpose?, trust_device?} —
    verify code. Returns trusted-device token if trust_device=true."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        code = (request.data.get('code') or '').strip()
        purpose = (request.data.get('purpose') or 'login').strip()[:40]
        try:
            ok, outcome = service.challenge(
                request.user, code, purpose=purpose,
                ip=_client_ip(request), ua=_ua(request),
            )
        except service.LockedOut as e:
            return Response({'error': 'locked_out', 'detail': str(e)},
                            status=429)
        if not ok:
            return Response({'error': 'bad_code', 'outcome': outcome},
                            status=400)
        body = {'verified': True, 'outcome': outcome}
        if request.data.get('trust_device'):
            token = service.trust_device(
                request.user, name=(request.data.get('device_name') or '')[:80],
                ip=_client_ip(request), ua=_ua(request),
            )
            body['trust_token'] = token  # client sets this as a cookie
        return Response(body)


class StatusView(APIView):
    """GET /2fa/status/ — report enrolment state for the current user."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        row = UserTOTP.objects.filter(user=request.user).first()
        backup_remaining = BackupCode.objects.filter(
            user=request.user, used_at__isnull=True,
        ).count()
        device_count = TrustedDevice.objects.filter(
            user=request.user, expires_at__gt=timezone.now(),
        ).count()
        return Response({
            'enabled': bool(row and row.enabled_at),
            'pending_setup': bool(row and not row.enabled_at),
            'enabled_at': row.enabled_at if row else None,
            'last_used_at': row.last_used_at if row else None,
            'backup_codes_remaining': backup_remaining,
            'trusted_devices': device_count,
            'locked_until': row.locked_until if row else None,
        })


class DisableView(APIView):
    """POST /2fa/disable/  body: {code} — must verify a fresh code first.
    Removes TOTP + backup codes + trusted devices."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        code = (request.data.get('code') or '').strip()
        if not code:
            return Response({'error': 'validation_error',
                             'detail': 'fresh 2FA code required to disable'},
                            status=400)
        try:
            ok, outcome = service.challenge(
                request.user, code, purpose='disable_2fa',
                ip=_client_ip(request), ua=_ua(request),
            )
        except service.LockedOut as e:
            return Response({'error': 'locked_out', 'detail': str(e)},
                            status=429)
        if not ok:
            return Response({'error': 'bad_code'}, status=400)
        service.disable(request.user, actor=request.user)
        return Response({'disabled': True})


class RegenerateBackupCodesView(APIView):
    """POST /2fa/backup-codes/regenerate/ — fresh set; old codes invalidated."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            codes = service.regenerate_backup_codes(request.user)
        except service.TwoFactorError as e:
            return Response({'error': 'tfa_error', 'detail': str(e)},
                            status=400)
        return Response({'backup_codes': codes})


class TrustedDevicesView(APIView):
    """GET — list my trusted devices.
    DELETE — revoke by id or all (?all=1)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from django.utils import timezone
        now = timezone.now()
        rows = TrustedDevice.objects.filter(
            user=request.user, expires_at__gt=now,
        ).order_by('-last_used_at')[:50]
        return Response({'results': [{
            'id': d.id, 'name': d.name, 'ip': d.ip,
            'last_used_at': d.last_used_at, 'expires_at': d.expires_at,
        } for d in rows]})

    def delete(self, request):
        if request.query_params.get('all'):
            n, _ = TrustedDevice.objects.filter(user=request.user).delete()
            return Response({'revoked': n})
        did = request.query_params.get('id')
        if not did:
            return Response({'error': 'id required'}, status=400)
        try:
            n = service.revoke_device(request.user, did)
        except Exception:
            return Response({'error': 'revoke_failed'}, status=400)
        return Response({'revoked': n})
