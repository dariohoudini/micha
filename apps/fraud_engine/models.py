"""
Fraud Rules Engine — data model
================================

Three layers of evidence:

  - DeviceFingerprint     SHA-256 of (UA + accept-language + screen
                          + timezone + canvas hash). One row per
                          *seen* fingerprint. The same fingerprint
                          can be linked to many users; that's what
                          we look for during evaluation.
  - IpReputation          Per-IP rolling counters + score. Built by a
                          worker from logs / external feeds.
  - VelocityRule          Tunable per-action thresholds the
                          evaluator walks at decision time.

When an action fires (welcome grant, referral click, checkout
submit, dispute open), `evaluate_fraud(action, context)` returns a
`FraudDecision` row capturing the score breakdown so support can
audit "why did this user get blocked?" after the fact.
"""
from __future__ import annotations

import hashlib
import uuid

from django.conf import settings
from django.db import models

User = settings.AUTH_USER_MODEL


ACTION_CHOICES = (
    ('welcome_grant',     'Welcome incentive grant'),
    ('referral_click',    'Referral link click'),
    ('referral_register', 'Referral-driven registration'),
    ('checkout_submit',   'Checkout submission'),
    ('order_place',       'Order place'),
    ('payment_attempt',   'Payment attempt'),
    ('coupon_redeem',     'Coupon redemption'),
    ('dispute_open',      'Dispute open'),
    ('account_login',     'Login'),
    ('signup',            'Signup'),
)

DECISION_CHOICES = (
    ('allow',     'Allow'),
    ('review',    'Send for manual review'),
    ('challenge', 'Challenge (OTP / step-up)'),
    ('block',     'Block — refuse the action'),
)


class DeviceFingerprint(models.Model):
    """Append-only record of devices we've ever seen. Rows are reused
    across sessions of the same device; first_seen / last_seen
    track the timeline."""

    fingerprint_hash = models.CharField(max_length=64, primary_key=True)
    raw_ua = models.CharField(max_length=255, blank=True, default='')
    timezone = models.CharField(max_length=64, blank=True, default='')
    language = models.CharField(max_length=24, blank=True, default='')
    screen = models.CharField(max_length=32, blank=True, default='')
    platform = models.CharField(max_length=32, blank=True, default='')
    canvas_hash = models.CharField(max_length=64, blank=True, default='')
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    seen_count = models.PositiveIntegerField(default=1)

    @staticmethod
    def hash_components(ua: str, lang: str, screen: str, tz: str,
                         canvas: str = '') -> str:
        raw = f'{ua}|{lang}|{screen}|{tz}|{canvas}'
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()


class DeviceUserLink(models.Model):
    """The many-to-many between devices and users. We flag a high
    fan-out (one device, many users) as a likely sharing / fraud
    farm in the velocity rules."""

    id = models.BigAutoField(primary_key=True)
    device = models.ForeignKey(
        DeviceFingerprint, on_delete=models.CASCADE, related_name='user_links',
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='device_links',
    )
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    seen_count = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = [('device', 'user')]
        indexes = [models.Index(fields=['user'])]


class IpReputation(models.Model):
    """Per-IP rolling counters + manual flag. `score` is the
    evaluator-facing value: 0=clean, 100=blocked. Computed from
    counters + external_score (proxy/datacenter/Tor flags supplied
    by an external feed when configured)."""

    ip_address = models.GenericIPAddressField(primary_key=True)
    score = models.PositiveSmallIntegerField(default=0)
    external_score = models.PositiveSmallIntegerField(default=0)
    distinct_users_24h = models.PositiveSmallIntegerField(default=0)
    failed_logins_1h = models.PositiveSmallIntegerField(default=0)
    chargebacks_30d = models.PositiveSmallIntegerField(default=0)
    is_datacenter = models.BooleanField(default=False)
    is_tor = models.BooleanField(default=False)
    is_proxy = models.BooleanField(default=False)
    is_manual_block = models.BooleanField(default=False)
    country = models.CharField(max_length=2, blank=True, default='')
    last_seen_at = models.DateTimeField(auto_now=True)
    first_seen_at = models.DateTimeField(auto_now_add=True)


class VelocityRule(models.Model):
    """Tunable per-action limits. Multiple rules per action are
    allowed — the evaluator runs all of them and picks the harshest
    decision. Editable via Django admin so ops can adjust without
    deploys."""

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=80)
    action = models.CharField(max_length=24, choices=ACTION_CHOICES, db_index=True)
    is_active = models.BooleanField(default=True)
    # Scope: what aggregates against the limit.
    scope = models.CharField(
        max_length=16,
        choices=(('user', 'Per user'),
                 ('device', 'Per device fingerprint'),
                 ('ip', 'Per IP address'),
                 ('email', 'Per email')),
    )
    window_seconds = models.PositiveIntegerField(default=3600)
    max_count = models.PositiveIntegerField(default=10)
    # Output: what to do if exceeded.
    on_exceed = models.CharField(max_length=12, choices=DECISION_CHOICES, default='review')
    score_weight = models.PositiveSmallIntegerField(
        default=25,
        help_text='Points to add to the fraud score if this rule trips.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class FraudDecision(models.Model):
    """Persisted output of evaluate_fraud(). One row per evaluation
    call so support can answer "what did the engine see?"."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action = models.CharField(max_length=24, choices=ACTION_CHOICES, db_index=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fraud_decisions',
    )
    device_hash = models.CharField(max_length=64, blank=True, default='', db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    score = models.PositiveSmallIntegerField(default=0)
    decision = models.CharField(max_length=12, choices=DECISION_CHOICES, default='allow')
    reasons = models.JSONField(default=list, blank=True)
    context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['action', 'decision'])]


class ActionLog(models.Model):
    """Append-only log of every fraud-sensitive action we evaluate.
    Drives velocity rule counters."""

    id = models.BigAutoField(primary_key=True)
    action = models.CharField(max_length=24, choices=ACTION_CHOICES, db_index=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='fraud_action_logs',
    )
    device_hash = models.CharField(max_length=64, blank=True, default='', db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    email = models.EmailField(blank=True, default='')
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['action', 'user', 'occurred_at']),
            models.Index(fields=['action', 'device_hash', 'occurred_at']),
            models.Index(fields=['action', 'ip_address', 'occurred_at']),
        ]
