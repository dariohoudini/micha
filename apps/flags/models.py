"""
apps/flags/models.py

Feature flags. Three kinds:

  BOOLEAN — simple on/off, optionally rolled out to a % of users.
  PERCENTAGE — same as boolean but the "on" set is gradually expanded.
  VARIANT — A/B/n test. Each user is bucketed into exactly one variant
            (or to 'control'); buckets are stable across calls.

Evaluation is deterministic per user via SHA-256(salt + flag_name + user_id)
so the same user always gets the same answer, even across processes and
deployments. No central random state, no race conditions.

Overrides:
  • per-user: forces a specific user into a specific value/variant
    (useful for QA + dogfooding before global rollout)
  • per-segment: e.g. "all staff get the new UI" — evaluated before
    percentage rollout
"""
from django.db import models
from django.conf import settings

User = settings.AUTH_USER_MODEL


class FlagKind(models.TextChoices):
    BOOLEAN    = 'boolean',    'Boolean (on/off)'
    PERCENTAGE = 'percentage', 'Percentage rollout'
    VARIANT    = 'variant',    'A/B/n variants'


class Flag(models.Model):
    """One row per flag. Operators manage these through the admin or the
    flags API — code only READS them via apps.flags.evaluator.evaluate()."""
    name = models.CharField(
        max_length=80, unique=True, db_index=True,
        help_text='Stable identifier referenced in code, e.g. "checkout_v2".',
    )
    description = models.TextField(blank=True)
    kind = models.CharField(max_length=12, choices=FlagKind.choices)

    is_active = models.BooleanField(
        default=True,
        help_text='When False, the flag returns its default for everyone.',
    )

    # Rollout configuration. Shape depends on kind:
    #   boolean / percentage:
    #     {"percentage": 25, "segments": ["is_staff"]}
    #   variant:
    #     {"variants": {"control": 50, "new_ui": 25, "redesign": 25},
    #      "segments": ["is_staff"]}
    #
    # ``segments`` is an opt-in list — listed segments are forced ON or into
    # the first non-control variant *before* the percentage rollout takes
    # effect. Supports: "is_staff", "is_superuser", "is_seller".
    rules = models.JSONField(default=dict)

    # Returned when:
    #   - flag is inactive
    #   - user is not in any segment AND percentage rollout decides "off"
    #   - evaluator hits an unexpected error (fail-safe)
    default_value = models.JSONField(default=False)

    # When did we last touch this flag? Bumped by save() — used to invalidate
    # cached evaluations.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.kind})'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Bust cached evaluations for this flag — every cached_call() with
        # tag 'flag:{name}' becomes a miss on next read.
        try:
            from apps.core.cache_kit import bump_tag
            bump_tag(f'flag:{self.name}')
        except Exception:
            pass


class FlagOverride(models.Model):
    """Force a specific user into a specific value for a specific flag.

    Useful for: QA before percentage rollout, customer support reproducing
    a buyer's reported bug, sticky-bucketing power users into experiments
    after they opted in via UI.

    Override is consulted BEFORE the percentage roll — it always wins.
    """
    flag = models.ForeignKey(Flag, on_delete=models.CASCADE, related_name='overrides')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='flag_overrides')
    # JSON so booleans, strings (variants) and numbers all fit.
    value = models.JSONField()
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['flag', 'user'], name='uniq_flag_user_override'),
        ]
        indexes = [
            models.Index(fields=['user', 'flag']),
        ]


class ExperimentExposure(models.Model):
    """Append-only log of which variant a user was shown. The source data
    for A/B test analysis: aggregate by flag_name × variant → measure
    downstream conversion rate.

    Written via evaluator.evaluate() with log_exposure=True so we don't
    record exposures that the calling code never actually surfaced to the
    user (an evaluated-but-never-rendered flag is not an exposure)."""
    flag_name = models.CharField(max_length=80, db_index=True)
    user_id = models.PositiveIntegerField(db_index=True, null=True, blank=True)
    # Hashed session id when user is anonymous — same person sees the same
    # variant across page loads even without an account.
    anon_token = models.CharField(max_length=64, blank=True, db_index=True)
    variant = models.CharField(max_length=80)
    context = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=['flag_name', 'variant', '-created_at']),
        ]
