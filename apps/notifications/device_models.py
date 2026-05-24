"""
apps/notifications/device_models.py
────────────────────────────────────

Push-notification device tokens.

Why a separate model (not just ``User.fcm_token``)
───────────────────────────────────────────────────
Pre-R5 the codebase had ``User.fcm_token`` — a single TextField. That
shape silently broke multi-device usage in production:

  • Buyer logs in on phone → fcm_token = phone_token
  • Buyer logs in on tablet → fcm_token = tablet_token (phone overwritten)
  • Phone now silently receives no pushes. Buyer never learns their
    order shipped. Support ticket: "the app doesn't notify me."

A user has many devices (phone + tablet + work laptop web). Each
device has its own FCM/APNs token. The mapping must be one-to-many.

This model is the one-to-many side.

Lifecycle
─────────
  registered → frontend obtains token from Capacitor + POSTs it
  active     → dispatcher sends pushes here
  inactive   → user logged out, or FCM returned InvalidRegistration
               on send. Soft-deleted (kept for audit / re-activation).

Failure handling
─────────────────
FCM returns specific error codes per token on send:
  ``messaging/registration-token-not-registered`` → device uninstalled
  ``messaging/invalid-registration-token``        → garbage token
Both → mark token inactive. Otherwise we keep retrying a dead token
on every notification, which inflates FCM bills + adds latency.

The dispatcher (apps/notifications/push_service.py) calls
``deactivate(reason=...)`` on these errors.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class DeviceToken(models.Model):
    """A single FCM / APNs / web-push device registration.

    The (user, token) pair is unique — re-registering the same token
    from the same user is an idempotent upsert (updates ``platform``
    + ``last_seen_at``). The same token under a different user is
    blocked at the DB level by ``token`` unique constraint — if a
    user logs out and someone else logs in on the same device, the
    re-register call hard-replaces the FK.
    """

    PLATFORM_CHOICES = [
        ('ios',     'iOS (APNs via FCM)'),
        ('android', 'Android (FCM)'),
        ('web',     'Web push'),
    ]

    DEACTIVATION_REASONS = [
        ('logout',          'User logged out'),
        ('fcm_invalid',     'FCM rejected as invalid'),
        ('fcm_unregistered','FCM reported app uninstalled'),
        ('replaced',        'Replaced by newer registration'),
        ('admin',           'Admin / ops action'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='device_tokens',
    )
    # Tokens are 100–200 chars typically; use TextField to stay safe
    # against future provider changes (Apple has rotated formats once
    # already).
    token = models.TextField(unique=True)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES)

    is_active = models.BooleanField(default=True)
    deactivation_reason = models.CharField(
        max_length=20, choices=DEACTIVATION_REASONS,
        blank=True, default='',
    )

    # Update on every send-attempt or re-register so we can prune
    # tokens that haven't been seen for N months. Cheap update —
    # no index needed, the prune job is rare.
    last_seen_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Optional: device model / OS version for ops visibility. Not
    # required — frontend may not send it. Used for debugging "why
    # is this user not getting pushes" tickets.
    device_info = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'notifications_device_token'
        indexes = [
            # Hot path: dispatcher looks up active tokens for a user.
            models.Index(fields=['user', 'is_active']),
        ]

    def __str__(self):
        suffix = self.token[-8:] if self.token else '(empty)'
        status = '✓' if self.is_active else '✗'
        return f'DeviceToken({status} {self.user_id} {self.platform} …{suffix})'

    def deactivate(self, reason: str = 'admin') -> None:
        """Soft-delete: mark inactive, record reason, save.

        Kept (not deleted) so the audit trail survives — useful when
        a user complains "I'm not getting pushes" and we can show
        their tokens were deactivated last week with reason='logout'.
        """
        if not self.is_active:
            return
        self.is_active = False
        self.deactivation_reason = reason or 'admin'
        self.save(update_fields=['is_active', 'deactivation_reason', 'updated_at'])

    def touch(self) -> None:
        """Bump ``last_seen_at`` without touching other fields."""
        self.last_seen_at = timezone.now()
        self.save(update_fields=['last_seen_at', 'updated_at'])
