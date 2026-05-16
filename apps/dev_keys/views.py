"""
apps/dev_keys/views.py

Self-serve key management for developers/sellers.

  GET    /dev/keys/                   list my keys (no secrets shown)
  POST   /dev/keys/                   create new key — RESPONSE INCLUDES SECRET ONCE
  GET    /dev/keys/<id>/              detail (no secret)
  POST   /dev/keys/<id>/revoke/       revoke a key
  GET    /dev/keys/<id>/usage/        recent usage rows for this key
"""
from datetime import timedelta
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import APIKey, APIKeyUsage, _generate_secret, SCOPE_CHOICES


def _serialize_key(k: APIKey, *, plaintext: str | None = None) -> dict:
    out = {
        'id': k.id, 'name': k.name, 'prefix': k.key_prefix,
        'scopes': k.scopes, 'is_active': k.is_active,
        'last_used_at': k.last_used_at,
        'expires_at': k.expires_at,
        'created_at': k.created_at,
        'revoked_at': k.revoked_at,
    }
    if plaintext is not None:
        # ONE-TIME REVEAL on creation
        out['secret'] = plaintext
    return out


class APIKeyListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        rows = APIKey.objects.filter(user=request.user).order_by('-created_at')
        return Response({
            'scopes': [s for s, _ in SCOPE_CHOICES],
            'results': [_serialize_key(k) for k in rows],
        })

    def post(self, request):
        name = (request.data.get('name') or '').strip()[:80]
        if not name:
            return Response({'error': 'validation_error',
                             'detail': 'name required'}, status=400)
        scopes = request.data.get('scopes') or []
        valid_scopes = {s for s, _ in SCOPE_CHOICES}
        bad = [s for s in scopes if s not in valid_scopes]
        if bad:
            return Response({'error': 'invalid_scopes', 'detail': bad}, status=400)

        # Optional expiry in days
        expires_in_days = request.data.get('expires_in_days')
        expires_at = None
        if expires_in_days is not None:
            try:
                d = int(expires_in_days)
                if d < 1 or d > 365 * 5:
                    return Response({'error': 'validation_error',
                                     'detail': 'expires_in_days 1..1825'}, status=400)
                expires_at = timezone.now() + timedelta(days=d)
            except ValueError:
                return Response({'error': 'validation_error',
                                 'detail': 'expires_in_days int'}, status=400)

        # Cap keys per user to limit blast-radius of compromise
        active_count = APIKey.objects.filter(user=request.user, is_active=True).count()
        if active_count >= 20:
            return Response({'error': 'too_many_keys',
                             'detail': 'Max 20 active keys per user. Revoke one first.'},
                            status=400)

        plaintext, prefix, kh = _generate_secret()
        key = APIKey.objects.create(
            user=request.user, name=name, key_hash=kh, key_prefix=prefix,
            scopes=list(scopes), expires_at=expires_at,
        )
        return Response(_serialize_key(key, plaintext=plaintext), status=201)


class APIKeyDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        key = get_object_or_404(APIKey, pk=pk, user=request.user)
        return Response(_serialize_key(key))


class APIKeyRevokeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        key = get_object_or_404(APIKey, pk=pk, user=request.user)
        if not key.is_active:
            return Response({'error': 'already_revoked'}, status=409)
        reason = (request.data.get('reason') or '').strip()[:200]
        key.is_active = False
        key.revoked_at = timezone.now()
        key.revoked_reason = reason
        key.save(update_fields=['is_active', 'revoked_at', 'revoked_reason'])
        return Response(_serialize_key(key))


class APIKeyUsageView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        key = get_object_or_404(APIKey, pk=pk, user=request.user)
        rows = APIKeyUsage.objects.filter(key=key).order_by('-created_at')[:200]
        return Response({'results': [{
            'method': r.method, 'path': r.path, 'status': r.status,
            'latency_ms': r.latency_ms, 'ip': r.ip,
            'created_at': r.created_at, 'error': r.error,
        } for r in rows]})
