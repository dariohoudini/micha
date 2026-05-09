"""
Fraud risk models.

Core ideas
----------
* A `RiskAssessment` is the *audit trail* of one scoring pass: which rules
  fired, what each contributed, the final score, the action taken.
  Persisted regardless of outcome, so we can appeal/explain decisions.
* `DeviceFingerprint` keeps a hash of client-side signals tied to the user.
  Multiple users sharing one fingerprint = collusion / account farming
  signal.
* The score lives on the *target* (Order has fraud_score / fraud_action
  already). RiskAssessment is the explanation; the score is denormalised
  to the target for hot-path reads.

Action ladder
-------------
   < 30   →  allow      (proceed)
   30–59  →  flag       (proceed but log + ops queue review)
   60–89  →  hold       (do not proceed; manual review required)
   ≥ 90   →  block      (do not proceed; surfaced to user as risk error)
"""
from django.conf import settings
from django.db import models


User = settings.AUTH_USER_MODEL


class RiskAction(models.TextChoices):
    ALLOW = 'allow', 'Allow'
    FLAG = 'flag', 'Flag (proceed, log)'
    HOLD = 'hold', 'Hold for manual review'
    BLOCK = 'block', 'Block (refuse)'


def action_for_score(score: int) -> str:
    if score < 30:
        return RiskAction.ALLOW
    if score < 60:
        return RiskAction.FLAG
    if score < 90:
        return RiskAction.HOLD
    return RiskAction.BLOCK


class RiskAssessment(models.Model):
    """One scoring pass. Persists every rule result + the final action.

    `ref_type` / `ref_id` link to the entity being scored — usually
    'order:<uuid>' or 'signup:<user_id>' or 'review:<id>'.
    """
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True,
        related_name='risk_assessments',
    )
    ref_type = models.CharField(max_length=40, db_index=True)
    ref_id = models.CharField(max_length=80, blank=True, db_index=True)
    score = models.PositiveSmallIntegerField()
    action = models.CharField(max_length=10, choices=RiskAction.choices, db_index=True)
    # List of {'rule': str, 'delta': int, 'reason': str}
    reasons = models.JSONField(default=list)
    # Snapshot of context for forensic review
    context = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['ref_type', 'ref_id', '-created_at']),
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['action', '-created_at']),
        ]

    def __str__(self):
        return f'{self.ref_type}:{self.ref_id} score={self.score} ({self.action})'


class DeviceFingerprint(models.Model):
    """Maps client-side fingerprint hashes → users that have used them.

    The fingerprint hash is opaque to the backend (computed in the browser
    from canvas + UA + tz + screen — never sensitive). What matters is
    correlation: 6 different accounts using the same fingerprint = farm.
    """
    fingerprint = models.CharField(max_length=128, db_index=True)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='device_fingerprints',
    )
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    last_seen_ip = models.GenericIPAddressField(null=True, blank=True)
    use_count = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ('fingerprint', 'user')
        indexes = [
            models.Index(fields=['fingerprint', '-last_seen_at']),
        ]
        ordering = ['-last_seen_at']

    def __str__(self):
        return f'{self.fingerprint[:8]}… · {self.user_id}'
