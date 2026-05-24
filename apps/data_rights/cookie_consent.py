"""
apps/data_rights/cookie_consent.py
───────────────────────────────────

Cookie consent persistence (R6 / GDPR + Lei 22/11).

Why this exists
───────────────
Both GDPR (Art. 7) and Angola's Lei 22/11 require explicit consent
before setting non-essential cookies, plus an audit trail proving
WHEN and WHAT the user agreed to. Without:

  • A regulator inspection sees no consent records → fine.
  • A user complaint ("I never agreed to tracking") has no evidence.
  • Withdrawal of consent has no mechanism beyond clearing cookies.

Categories
──────────
  essential       always allowed (session, CSRF, cart) — not gated
  analytics       PostHog/Mixpanel-style event tracking
  marketing       attribution + retargeting
  preferences     remembered settings (language, theme)

Default: essential ON, others OFF until user opts in. The frontend
shows the banner; this module persists the decision so it survives
device changes (anon: tied to consent_key; authed: tied to user).

API
───
  POST /api/v1/account/data-request/consent/      body: {analytics, marketing, preferences}
  GET  /api/v1/account/data-request/consent/      returns current state
  POST /api/v1/account/data-request/consent/withdraw/  → sets all non-essential to False
"""
from __future__ import annotations

import logging
import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


log = logging.getLogger('micha.consent')


class CookieConsent(models.Model):
    """Append-only consent records. Latest row per (user OR consent_key)
    is the active consent. Historical rows are retained for audit.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='cookie_consents',
    )
    # For anonymous visitors who consent BEFORE login. Frontend
    # generates a random 32-char key once and stores in localStorage.
    # On login, we link this key's history to the user.
    consent_key = models.CharField(max_length=64, db_index=True, blank=True, default='')

    analytics = models.BooleanField(default=False)
    marketing = models.BooleanField(default=False)
    preferences = models.BooleanField(default=False)

    # Audit fields.
    ip_hash = models.CharField(max_length=64, blank=True, default='')
    user_agent = models.CharField(max_length=200, blank=True, default='')
    policy_version = models.CharField(max_length=20, blank=True, default='v1')
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'data_rights_cookie_consent'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['consent_key', '-created_at']),
        ]

    def __str__(self):
        who = self.user_id or self.consent_key or 'anon'
        return f'CookieConsent({who}, a={self.analytics}, m={self.marketing})'


# ─── Service helpers ──────────────────────────────────────────────────


def _hash_ip(ip: str) -> str:
    import hashlib
    if not ip:
        return ''
    secret = (settings.SECRET_KEY or '')[:16].encode()
    return hashlib.sha256(secret + ip.encode()).hexdigest()[:64]


def latest_consent(*, user=None, consent_key: str = ''):
    """Return the latest CookieConsent row for the requester, or None."""
    qs = CookieConsent.objects.all()
    if user is not None and getattr(user, 'pk', None):
        qs = qs.filter(user=user)
    elif consent_key:
        qs = qs.filter(consent_key=consent_key)
    else:
        return None
    return qs.order_by('-created_at').first()


def record_consent(*, user=None, consent_key: str = '',
                   analytics: bool, marketing: bool, preferences: bool,
                   request=None, policy_version: str = 'v1') -> CookieConsent:
    """Insert a new consent row. Never updates existing rows — full
    history retained for regulator audit."""
    ip = ''
    ua = ''
    if request is not None:
        try:
            from middleware.client_ip import get_client_ip
            ip = get_client_ip(request, trusted_only=True) or ''
        except Exception:
            ip = ''
        ua = (request.META.get('HTTP_USER_AGENT') or '')[:200]

    if not consent_key and user is None:
        # Frontend should always supply one; generate as fallback.
        consent_key = secrets.token_urlsafe(24)

    row = CookieConsent.objects.create(
        user=user if (user and getattr(user, 'pk', None)) else None,
        consent_key=consent_key or '',
        analytics=bool(analytics),
        marketing=bool(marketing),
        preferences=bool(preferences),
        ip_hash=_hash_ip(ip),
        user_agent=ua,
        policy_version=policy_version,
    )
    log.info('cookie_consent_recorded',
             extra={'consent_id': row.pk, 'user_id': row.user_id,
                    'analytics': row.analytics, 'marketing': row.marketing,
                    'preferences': row.preferences,
                    'policy_version': policy_version})
    return row


def withdraw(*, user=None, consent_key: str = '',
             request=None) -> CookieConsent:
    """Withdraw consent — record a row with all non-essential False."""
    row = record_consent(
        user=user, consent_key=consent_key,
        analytics=False, marketing=False, preferences=False,
        request=request,
    )
    row.withdrawn_at = timezone.now()
    row.save(update_fields=['withdrawn_at'])
    return row
