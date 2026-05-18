"""
apps/security/login_attempt_models.py

Append-only audit table for every login attempt. The cache (Redis) holds
the hot-path counters; this table is the durable, queryable record for:

  • forensics ("when did the attack start?", "which IPs?")
  • compliance ("show me every access to user X's account")
  • incident response ("notify users whose accounts were hit")
  • anomaly detection (impossible-travel, new-device alerts)

The cache layer can be flushed without losing security history because
this table is the source of truth.

Privacy / retention:
  • Email is stored verbatim (not hashed) — must be queryable for the
    "show me access to my account" data-export endpoint.
  • IPs and user-agents are stored verbatim — required for
    forensic correlation across accounts.
  • Beat task ``security.purge_old_login_attempts`` deletes rows older
    than ``LOGIN_ATTEMPT_RETENTION_DAYS`` (default 90).
"""
from django.db import models


class LoginAttemptFailureReason(models.TextChoices):
    BAD_CREDENTIALS = 'bad_credentials', 'Bad credentials'
    EMAIL_NOT_VERIFIED = 'email_not_verified', 'Email not verified'
    ACCOUNT_SUSPENDED = 'account_suspended', 'Account suspended'
    ACCOUNT_LOCKED = 'account_locked', 'Account locked (too many failures)'
    IP_LOCKED = 'ip_locked', 'IP locked (credential stuffing)'
    BAD_2FA = 'bad_2fa', '2FA code rejected'
    MISSING_2FA = 'missing_2fa', '2FA code not provided'
    UNKNOWN = 'unknown', 'Unknown'


class LoginAttempt(models.Model):
    # Email is stored as the attempted value, NOT a FK. Failed attempts
    # against non-existent emails are recorded too — that's the whole
    # point of credential-stuffing forensics.
    email = models.CharField(max_length=255, db_index=True)

    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)

    succeeded = models.BooleanField()
    failure_reason = models.CharField(
        max_length=24,
        choices=LoginAttemptFailureReason.choices,
        blank=True,
    )

    # When the attempt triggered a lockout (per-email OR per-ip), record
    # which threshold was hit. Lets forensics distinguish "regular
    # failure" from "the failure that locked the door".
    triggered_lockout = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            # The two query patterns operations actually run:
            #   "all attempts against email X in last 24h" (lockout state)
            #   "all attempts from IP Y in last 24h" (stuffing detection)
            models.Index(fields=['email', '-created_at']),
            models.Index(fields=['ip', '-created_at']),
            # Forensic: locate every lockout trigger in a window
            models.Index(fields=['triggered_lockout', '-created_at'],
                         condition=models.Q(triggered_lockout=True),
                         name='security_la_locks_idx'),
        ]
        ordering = ['-created_at']

    def __str__(self):
        outcome = 'ok' if self.succeeded else self.failure_reason
        return f'{self.email} from {self.ip} → {outcome}'
