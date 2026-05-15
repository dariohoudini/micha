"""
apps/idempotency/models.py

Stores the *response* of a successful write request so a retry that sends the
same Idempotency-Key replays the original response byte-for-byte instead of
executing the side-effect a second time.

Scope: per-user. Two different users cannot collide on a key.
TTL:   24 hours by default — long enough for buyer/network retry, short enough
       to keep the table small.

Pattern:
    POST /checkout/  +  Idempotency-Key: <uuid>
       1st call → service runs, response stored, key flips to COMPLETED
       2nd call → cached response replayed (200/201 whatever it was)
       In-flight retry → 409 idempotency_in_progress (so the client backs off
                         instead of fighting itself)
"""
from django.conf import settings
from django.db import models, transaction
from django.utils import timezone
from datetime import timedelta


class IdempotencyStatus(models.TextChoices):
    IN_PROGRESS = 'in_progress', 'In progress'
    COMPLETED   = 'completed',   'Completed'


class IdempotencyKey(models.Model):
    """One row per (user, key). Caches the response for safe replay."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='idempotency_keys',
    )
    key = models.CharField(max_length=128)
    # Hash of the request body — protects against a client reusing the same key
    # with a different payload (which would be a programming bug; we 422 it).
    request_hash = models.CharField(max_length=64)

    status = models.CharField(
        max_length=16, choices=IdempotencyStatus.choices,
        default=IdempotencyStatus.IN_PROGRESS,
    )
    # Cached response (filled when status flips to COMPLETED)
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_body = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()

    class Meta:
        # A user cannot reuse the same key (that's the whole point).
        constraints = [
            models.UniqueConstraint(fields=['user', 'key'], name='uniq_user_idempotency_key'),
        ]
        indexes = [
            models.Index(fields=['expires_at']),
            models.Index(fields=['user', 'status']),
        ]

    @classmethod
    def default_ttl(cls):
        return timedelta(hours=24)

    @classmethod
    def claim(cls, *, user, key, request_hash):
        """Atomically claim the key.

        Returns a tuple ``(row, replay)`` where:
          - ``replay`` is None when the caller is the first to claim (must
            proceed to run the real handler and call ``complete()``)
          - ``replay`` is the cached response dict ``{status_code, body}``
            when the key has already COMPLETED
          - raises ``IdempotencyInProgress`` if the key is currently held by
            another in-flight request (client should retry later)
          - raises ``IdempotencyMismatch`` if the same key was previously used
            with a different request body (programming error on the client)
        """
        now = timezone.now()
        with transaction.atomic():
            existing = (
                cls.objects.select_for_update()
                .filter(user=user, key=key)
                .first()
            )
            if existing is None:
                row = cls.objects.create(
                    user=user, key=key, request_hash=request_hash,
                    expires_at=now + cls.default_ttl(),
                )
                return row, None

            # Same key reused with a different payload — almost certainly a
            # client bug. Refuse loudly rather than silently replay a stale
            # response for the wrong intent.
            if existing.request_hash != request_hash:
                raise IdempotencyMismatch(
                    'Idempotency-Key reused with a different request body'
                )

            if existing.status == IdempotencyStatus.COMPLETED:
                return existing, {
                    'status_code': existing.status_code or 200,
                    'body': existing.response_body,
                }

            # IN_PROGRESS — first request is still running. The client should
            # back off and retry; we don't want concurrent executions.
            raise IdempotencyInProgress(
                'A request with this Idempotency-Key is already in progress'
            )

    def complete(self, *, status_code, body):
        self.status = IdempotencyStatus.COMPLETED
        self.status_code = status_code
        self.response_body = body
        self.completed_at = timezone.now()
        self.save(update_fields=[
            'status', 'status_code', 'response_body', 'completed_at',
        ])

    def abandon(self):
        """Remove the in-progress claim so the client can retry cleanly.

        Called when the handler raises *before* writing a response — we don't
        want the key locked forever just because of a transient error.
        """
        if self.status == IdempotencyStatus.IN_PROGRESS:
            self.delete()


class IdempotencyInProgress(Exception):
    """Raised when the same key is currently being processed by another request."""


class IdempotencyMismatch(Exception):
    """Raised when the same key is reused with a different request body."""
