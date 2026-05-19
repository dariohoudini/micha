"""
apps/notifications/unsubscribe.py

One-click unsubscribe — RFC 8058 + CAN-SPAM Section 5(a)(4)(A) +
GDPR Art. 7(3) compliance.

The footer of every non-transactional email contains a link to:

    /api/v1/notifications/unsubscribe/?token=<HMAC-signed token>

Hitting it (GET or POST) adds the address to the suppression list
WITHOUT requiring authentication — the token IS the auth. Required
by RFC 8058: a user reading email on their phone can't realistically
log in to unsubscribe.

Token shape:
    base64(email_hash[:16] + signature[:16])
  where
    email_hash    = first 16 chars of sha256(email)
    signature     = HMAC-SHA256(settings.SECRET_KEY, email).hexdigest()[:16]

We hash the email instead of putting it in the URL so:
  • The URL itself doesn't expose the email to web-server logs, CDN
    caches, or browser history.
  • The recipient's "Recently visited" URL list doesn't carry their
    address to their next device.

The handler reverses the hash by walking SuppressedEmail candidates
(but the smart path is to also include the raw email in the URL for
ease of operation, balanced against the privacy concern). For now we
include the raw email lookup-key but sign it so attackers can't
unsubscribe other users.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from urllib.parse import urlencode

from django.conf import settings


_TOKEN_VERSION = 'v1'


def _sign(email: str) -> str:
    """HMAC-SHA256 of the email under SECRET_KEY. First 16 chars hex."""
    secret = settings.SECRET_KEY.encode('utf-8')
    msg = f'{_TOKEN_VERSION}:{email.lower().strip()}'.encode('utf-8')
    return hmac.new(secret, msg, hashlib.sha256).hexdigest()[:24]


def build_unsubscribe_url(email: str) -> str:
    """Build a one-click unsubscribe URL for an email.

    Returns an absolute URL using settings.FRONTEND_URL so it works
    from a customer's email client (no relative-path nonsense).
    """
    if not email:
        return ''
    base = getattr(settings, 'FRONTEND_URL', '') or 'https://micha.app'
    qs = urlencode({
        'email': email.lower().strip(),
        'sig': _sign(email),
        'v': _TOKEN_VERSION,
    })
    return f'{base}/u/?{qs}'


def verify_unsubscribe(email: str, sig: str, version: str = _TOKEN_VERSION) -> bool:
    """Constant-time signature check. Returns True if the (email, sig)
    pair is a valid unsubscribe token issued by this server."""
    if not email or not sig:
        return False
    if version != _TOKEN_VERSION:
        return False
    expected = _sign(email)
    return hmac.compare_digest(expected, sig)
