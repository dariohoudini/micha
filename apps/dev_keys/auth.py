"""
apps/dev_keys/auth.py

DRF authentication class. Reads the X-API-Key header (or Authorization:
ApiKey <key>), looks up by SHA-256 hash, sets request.user to the key's
owner AND stashes the APIKey row on request._api_key for scope checks.

Auth never raises — invalid keys produce AuthenticationFailed, the standard
DRF response (401). Expired / revoked keys are treated as invalid.
"""
from __future__ import annotations
import hashlib
import logging

from rest_framework import authentication, exceptions
from django.utils import timezone

from .models import APIKey

log = logging.getLogger(__name__)


class APIKeyAuthentication(authentication.BaseAuthentication):
    """Authenticate by ``X-API-Key`` header OR ``Authorization: ApiKey <key>``."""
    keyword = 'ApiKey'

    def authenticate(self, request):
        raw = self._extract_key(request)
        if not raw:
            return None  # let other auth classes try

        key_hash = hashlib.sha256(raw.encode('utf-8')).hexdigest()
        key = (
            APIKey.objects
            .select_related('user')
            .filter(key_hash=key_hash, is_active=True)
            .first()
        )
        if key is None:
            raise exceptions.AuthenticationFailed('Invalid API key.')
        if key.expires_at and key.expires_at <= timezone.now():
            raise exceptions.AuthenticationFailed('API key expired.')

        # Stash the key row on the request so downstream permission classes
        # can check scopes. last_used_at is bumped here so a high-volume
        # caller doesn't update the row on every request (we update it lazily
        # if it's older than ~1 minute).
        request._api_key = key
        self._maybe_bump_last_used(key)

        return (key.user, key)

    def authenticate_header(self, request):
        return f'{self.keyword} realm="api"'

    def _extract_key(self, request):
        raw = (request.META.get('HTTP_X_API_KEY') or '').strip()
        if raw:
            return raw
        # Authorization: ApiKey <key>
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith(f'{self.keyword} '):
            return auth_header[len(self.keyword) + 1:].strip()
        return ''

    def _maybe_bump_last_used(self, key):
        try:
            now = timezone.now()
            if key.last_used_at is None or (now - key.last_used_at).total_seconds() > 60:
                APIKey.objects.filter(pk=key.pk).update(last_used_at=now)
        except Exception:
            pass
