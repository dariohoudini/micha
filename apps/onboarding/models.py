"""
First-Run Experience doc CH10 — the guest profile.

The setup answers (region, language/currency, interests, permissions,
attribution) live on a PII-free GUEST record keyed by the client's
device id — no account needed. It drives localisation + first-feed
personalisation while the user is still a guest, and is copied to the
user at signup (the carry-over, CH11) so the account is born already
knowing them. Holds NO PII (no name/phone/email) — a preferences +
context profile, not an identity dossier.
"""
import uuid

from django.conf import settings
from django.db import models


class GuestProfile(models.Model):
    STATUS = (
        ('not_started', 'Not started'),
        ('in_progress', 'In progress'),
        ('completed', 'Completed'),
        ('skipped', 'Skipped'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # The stable anchor: a client-generated device id (localStorage /
    # secure storage). Unique so a returning guest resolves to the same
    # profile and skips setup.
    device_id = models.CharField(max_length=128, unique=True, db_index=True)

    # locale = {region, country, language, currency, province?}
    locale = models.JSONField(default=dict, blank=True)
    # interests = [category_id, ...] — the cold-start seed.
    interests = models.JSONField(default=list, blank=True)
    # permissions = {notif, location} — granted|denied|undetermined
    permissions = models.JSONField(default=dict, blank=True)
    # attribution = {source, campaign, referrer} — how they arrived.
    attribution = models.JSONField(default=dict, blank=True)

    onboarding_status = models.CharField(
        max_length=16, choices=STATUS, default='not_started', db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Set on carry-over at signup — the guest becomes this user.
    linked_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='guest_profiles')
    carried_over_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'onboarding_guest_profile'
        indexes = [
            models.Index(fields=['linked_user']),
            models.Index(fields=['onboarding_status', '-created_at']),
        ]

    def __str__(self):
        return f'GuestProfile({self.device_id[:12]}… {self.onboarding_status})'
