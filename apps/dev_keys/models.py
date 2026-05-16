"""
apps/dev_keys/models.py

Third-party API keys. Two tables:

  APIKey       — one row per credential. The plaintext secret is shown to the
                 caller ONCE at creation; we store a SHA-256 hash. Hashing
                 means a database leak doesn't expose live secrets.

  APIKeyUsage  — sampled per-request audit log (one row per call to the API
                 by that key). Bounded growth via TTL — only last 30 days
                 retained for any key.

Key format: ``mk_live_<prefix6>_<secret>``
  Prefix is human-meaningful and stored alongside the hash so admins can
  see which key was used in usage rows without ever knowing the secret.

Scopes (string list on the key):
  Each protected endpoint declares a required scope (e.g. 'orders:read').
  Decorator @requires_scope('orders:read') refuses keys that lack it.
  Scope list is enforceable at request time; expanding scopes requires
  the seller to re-issue a key (limits damage from a leaked narrow key).
"""
import secrets
import hashlib
from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


SCOPE_CHOICES = (
    # Read scopes
    ('orders:read',    'Read orders'),
    ('products:read',  'Read products'),
    ('inventory:read', 'Read inventory'),
    ('payouts:read',   'Read payouts'),
    ('analytics:read', 'Read analytics'),
    # Write scopes
    ('orders:write',     'Update orders (ship, refund)'),
    ('products:write',   'Create / update / delete products'),
    ('inventory:write',  'Adjust stock levels'),
    ('webhooks:write',   'Register / update webhook URLs'),
)


def _generate_secret() -> tuple[str, str, str]:
    """Return (plaintext_key, prefix, hash). The plaintext is shown once;
    the hash is what we store."""
    secret = secrets.token_urlsafe(32)
    prefix = secret[:6]
    full = f'mk_live_{prefix}_{secret}'
    return full, prefix, hashlib.sha256(full.encode('utf-8')).hexdigest()


def _hash_key(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode('utf-8')).hexdigest()


class APIKey(models.Model):
    """One credential. Owned by a User (the seller/developer); a single user
    may have many keys (e.g. one per environment: dev, staging, prod)."""
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='api_keys',
    )
    name = models.CharField(max_length=80, help_text='Human label, e.g. "ERP integration prod".')
    # SHA-256 of the full plaintext. We index this so authentication is O(1).
    key_hash = models.CharField(max_length=64, unique=True, db_index=True)
    # First 6 chars of the secret portion — shown in admin UI / usage rows so
    # operators can identify a key without seeing the secret.
    key_prefix = models.CharField(max_length=12, db_index=True)
    scopes = models.JSONField(default=list)

    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True,
                                      help_text='NULL = never expires')
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'is_active']),
            models.Index(fields=['key_prefix', '-created_at']),
        ]

    def has_scope(self, scope: str) -> bool:
        return scope in (self.scopes or [])

    def __str__(self):
        return f'{self.name} ({self.key_prefix}…)'


class APIKeyUsage(models.Model):
    """Per-request audit row. High write volume → indexed for the read paths
    we actually need (per-key recent activity)."""
    key = models.ForeignKey(APIKey, on_delete=models.CASCADE, related_name='usage')
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=300)
    status = models.PositiveSmallIntegerField()
    latency_ms = models.PositiveIntegerField(default=0)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    error = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['key', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]
