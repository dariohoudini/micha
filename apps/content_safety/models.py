"""
apps/content_safety/models.py

Generic content safety. Reusable across chat, reviews, product
descriptions, profile bios — anywhere a user types something the platform
shows to other users.

Four tables:

  ScanRule          Editable rules (regex pattern + severity + category).
                    Operators can add / disable rules in admin without a
                    deploy. The existing apps/chat/content_filter.py
                    patterns get bootstrapped here as seed data.

  ScanResult        Append-only audit per scan. Stores matched_rules,
                    severity, action, hash of the scanned text (we don't
                    keep the raw text — PII concerns. Hash lets us dedupe
                    repeated submissions of the same content.)

  UserViolationCounter  Rolling per-user counter of recent violations.
                    Drives escalation: 3 blocks in 24h → auto-open a T&S
                    case. Counter decays automatically (24h window).

  IPViolationCounter    Same shape but per source IP. Catches bot rings
                    that rotate through accounts.
"""
import hashlib
from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class RuleCategory(models.TextChoices):
    PII       = 'pii',       'PII (phone/email/IBAN)'
    SCAM      = 'scam',      'Scam / off-platform payment'
    PHISHING  = 'phishing',  'Phishing / external links'
    ABUSE     = 'abuse',     'Abuse / harassment'
    SPAM      = 'spam',      'Spam'
    SUSPICIOUS= 'suspicious','Suspicious language (review)'


class Severity(models.TextChoices):
    INFO  = 'info',  'Info (log only)'
    WARN  = 'warn',  'Warn (flag for review)'
    HIDE  = 'hide',  'Hide content from other party'
    BLOCK = 'block', 'Block — refuse to publish'


class Action(models.TextChoices):
    ALLOW = 'allow', 'Allowed'
    FLAG  = 'flag',  'Flagged for review'
    HIDE  = 'hide',  'Hidden from recipient'
    BLOCK = 'block', 'Blocked'


class ScanRule(models.Model):
    """One regex rule. Admins can add / disable in admin without a deploy."""
    name = models.CharField(max_length=80, unique=True)
    description = models.CharField(max_length=200, blank=True)
    pattern = models.CharField(max_length=500,
                               help_text='Python regex; case-insensitive when run')
    category = models.CharField(max_length=12, choices=RuleCategory.choices, db_index=True)
    severity = models.CharField(max_length=6, choices=Severity.choices, db_index=True)
    # Optional contextual narrowing — only apply this rule to certain ref types.
    # Empty = applies everywhere. JSON list of strings (e.g. ['chat_message']).
    applies_to = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    # User-facing message when this rule fires (shown when severity blocks)
    user_message = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['is_active', 'category']),
        ]
        ordering = ['category', 'name']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Bust the cached rule list — service reads it via cache_kit
        try:
            from apps.core.cache_kit import bump_tag
            bump_tag('content_safety:rules')
        except Exception:
            pass

    def __str__(self):
        return f'{self.name} ({self.severity})'


class ScanResult(models.Model):
    """Append-only audit. One row per scan() invocation."""
    ref_type = models.CharField(max_length=40, db_index=True)
    ref_id   = models.CharField(max_length=80, db_index=True)
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+',
    )
    severity = models.CharField(max_length=6, choices=Severity.choices, db_index=True)
    action   = models.CharField(max_length=6, choices=Action.choices)
    # List of rule names that matched. Stored as JSON for portability.
    matched_rules = models.JSONField(default=list)
    # SHA-256 of the scanned text. We DON'T persist the raw text — for both
    # PII reasons and storage bounds. Hash lets us dedupe identical submits.
    text_hash = models.CharField(max_length=64, db_index=True)
    text_length = models.PositiveIntegerField(default=0)
    # Free-form metadata: scanner version, request_id, language, etc.
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['ref_type', 'ref_id']),
            models.Index(fields=['actor', '-created_at']),
            models.Index(fields=['severity', '-created_at']),
        ]
        ordering = ['-created_at']

    @staticmethod
    def hash_text(s: str) -> str:
        return hashlib.sha256((s or '').encode('utf-8')).hexdigest()


class UserViolationCounter(models.Model):
    """Per-user rolling counter for escalation. count_24h is reset on the
    first scan past a 24h-old window."""
    user = models.OneToOneField(User, on_delete=models.CASCADE,
                                  related_name='content_violations')
    count_24h = models.PositiveIntegerField(default=0)
    window_started_at = models.DateTimeField()
    last_violation_at = models.DateTimeField(null=True, blank=True)
    # Latest severity hit — drives whether we auto-open a case
    last_severity = models.CharField(max_length=6, blank=True)
    # Case auto-opened? FK to apps.cases.Case
    last_case_id = models.IntegerField(null=True, blank=True)
