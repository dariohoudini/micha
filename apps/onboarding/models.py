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


class GuestCartItem(models.Model):
    """Guest-First doc CH6 — the server-side guest cart.

    A snapshot of the anonymous cart keyed to the guest device, so the
    cart survives reinstalls and reaches other devices — and is merged
    into the account cart at signup (the carry-over). Deliberately a
    loose snapshot (integer product ids, not FKs): the guest's local
    cart can hold stale ids, and validation happens at read + merge
    time against the live catalog, exactly like /cart/merge/ does.
    """
    guest = models.ForeignKey(
        GuestProfile, on_delete=models.CASCADE, related_name='cart_items')
    product_id = models.PositiveBigIntegerField()
    variant_combo_id = models.PositiveBigIntegerField(null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)
    price_at_add = models.DecimalField(max_digits=10, decimal_places=2,
                                       null=True, blank=True)
    title = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'onboarding_guest_cart_item'
        constraints = [
            models.UniqueConstraint(
                fields=['guest', 'product_id', 'variant_combo_id'],
                name='guest_cart_item_unique'),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name='guest_cart_item_qty_positive'),
        ]

    def __str__(self):
        return f'GuestCartItem({self.guest_id} p{self.product_id} x{self.quantity})'
