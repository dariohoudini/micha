"""
apps/moderation/service.py
───────────────────────────

Central content-moderation chokepoint.

Why this exists
────────────────
``apps/moderation/models.py:ContentFlag.check_content()`` has existed
in the codebase for months but was NEVER CALLED from any view. Every
Product, Review, ListingSnapshot, and ChatMessage was published with
zero moderation gate — keyword profanity, scam keywords, banned items,
all live in production the moment a seller hits "publish".

This module fixes that with a single ``moderate()`` entry point + a
signal-based wire-up. Signal-based (vs view-based) because:

  • Catches EVERY creation path: API views, management commands,
    admin UI, fixtures, data migrations, Celery tasks. A view-based
    hook is bypassable; a model-signal hook is not.
  • Centralised: one place to change the moderation policy, one place
    to instrument metrics, one place to plug in Roadmap-4 ML classifiers.

Decision model
───────────────
``moderate()`` returns a ``ModerationDecision`` enum:

  ALLOW    — content passes; publish normally
  REVIEW   — content matches a soft-flag rule; publish but in a
             non-public state (Product.is_active=False, Review hidden)
             AND create a ContentFlag row for the moderator queue
  BLOCK    — content matches a hard-rule (banned item, illegal); refuse
             to save. Currently no rules are BLOCK-class; the keyword
             list is all REVIEW.

What this module is NOT
────────────────────────
  • Not an ML classifier. The current rule set is a keyword blacklist
    inherited from apps/moderation/models.py:BANNED_KEYWORDS. Roadmap-4
    will plug in real image classification (NSFW, weapons), text
    classification (multilingual profanity), and brand-counterfeit
    detection. The signature of ``moderate()`` is designed to absorb
    those without callers needing to change.
  • Not a moderator's UI. ContentFlag rows are written here; reviewing
    them is admin-side and lives in apps/moderation/views.py (not yet
    fully built — Roadmap 4 work).
  • Not chat moderation. ChatMessage moderation is best-effort logging
    only — a chat is a private conversation; auto-blocking individual
    messages would be heavy-handed and breaks the UX. ContentFlag is
    written for ops review when patterns trigger; the message itself
    is still delivered.

Public API
──────────
  moderate(text: str, target_type: str, target_id: int,
           target_user=None) -> ModerationDecision

  apply_decision(instance, decision: ModerationDecision) -> None
      Centralised post-decision action: flips visibility flags on the
      instance based on its target_type. Used by the signal handlers
      so callers don't need to know the per-model visibility field.
"""
from __future__ import annotations

import enum
import logging
from typing import Optional

log = logging.getLogger(__name__)


class ModerationDecision(enum.Enum):
    ALLOW = 'allow'
    REVIEW = 'review'   # publish in non-public state + queue for review
    BLOCK = 'block'     # refuse save (currently unused; reserved)


# Keywords that trigger REVIEW (queue for ops). Tuned for Lusophone +
# English marketplace context (Angola serves both). The original list
# in models.py was English-only — added Portuguese equivalents.
#
# This is intentionally small and high-precision. Roadmap 4 plugs in
# a real classifier. Until then we'd rather have FALSE NEGATIVES
# (real abuse slips through to manual review) than FALSE POSITIVES
# (legitimate listings auto-flagged en masse).
_REVIEW_KEYWORDS = (
    # Fraud / scam patterns (en + pt)
    'scam', 'fraud', 'fake', 'counterfeit', 'stolen',
    'fraude', 'falsificado', 'roubado',
    # Restricted goods (en + pt)
    'drugs', 'weapons', 'firearm', 'cocaine', 'heroin',
    'drogas', 'armas', 'munição',
    # Adult content (en + pt) — marketplace is general consumer
    'pornography', 'adult content',
    'pornografia', 'conteúdo adulto',
)


def _setting(name, default):
    try:
        from django.conf import settings
        return getattr(settings, name, default)
    except Exception:
        return default


def _moderation_enabled() -> bool:
    """Master switch. Lets ops disable moderation if the rules are
    misfiring during a launch. Default ON in prod, ON in dev."""
    return bool(_setting('MODERATION_ENABLED', True))


def moderate(text: str, target_type: str, target_id,
             target_user=None) -> ModerationDecision:
    """Run the moderation rules against ``text`` and return a decision.

    Args:
      text: free-form content to check. None / empty → ALLOW.
      target_type: one of 'product', 'review', 'listing', 'message'.
        Matches ContentFlag.TARGET_CHOICES.
      target_id: PK of the target row. Stored on ContentFlag for the
        moderator queue link.
      target_user: optional User who created the content. Used by
        future per-user-reputation rules; not used by the keyword
        rule today.

    Returns:
      ModerationDecision. Side effect: on REVIEW, writes a
      ContentFlag row.

    Safe failure: if anything raises (DB hiccup, import error),
    returns ALLOW and logs at WARNING. Better to let one item through
    than to break the entire create flow.
    """
    if not _moderation_enabled():
        return ModerationDecision.ALLOW

    if not text:
        return ModerationDecision.ALLOW

    try:
        text_l = str(text).lower()
        triggered = [kw for kw in _REVIEW_KEYWORDS if kw in text_l]

        if not triggered:
            return ModerationDecision.ALLOW

        # REVIEW: write a ContentFlag row. The moderator queue picks
        # this up via apps/moderation/views.py.
        #
        # target_user vs flagger: target_user is the *owner* of the
        # flagged content (used by the escalation engine to count
        # rejections per user). flagger is who reported it — here it's
        # an auto-flag so flagger=None. Pre-R4 callers passed
        # target_user via the flagger= field; we now route it correctly.
        try:
            from .models import ContentFlag
            tu = target_user if (
                target_user
                and getattr(target_user, 'is_authenticated', False)
            ) else None
            ContentFlag.objects.create(
                target_type=target_type,
                target_id=int(target_id) if target_id else 0,
                target_user=tu,
                reason=f'Auto-flagged keywords: {", ".join(triggered[:5])}',
                auto_flagged=True,
                flagger=None,  # auto-flag — no human reporter
                severity='medium',
                status='pending',
            )
        except Exception:
            log.exception('moderation: failed to write ContentFlag row')

        log.info(
            'moderation_flagged',
            extra={
                'target_type': target_type,
                'target_id': str(target_id),
                'triggered_count': len(triggered),
                'user_id': getattr(target_user, 'id', None),
            },
        )
        return ModerationDecision.REVIEW

    except Exception:
        log.exception('moderation: moderate() raised; failing OPEN')
        return ModerationDecision.ALLOW


def apply_decision(instance, decision: ModerationDecision) -> None:
    """Apply a decision to a model instance's visibility flags.

    Centralised so per-model knowledge (which field hides the content)
    lives in one place. Adding a new moderated content type means
    one branch here, not touching every view.

    Currently:
      Product:   is_active=False on REVIEW
      Review:    is_visible=False if the field exists (defensive)
      Listing:   is_active=False on REVIEW
      Message:   no visibility change (chat is private; log only)
    """
    if decision != ModerationDecision.REVIEW:
        return

    cls_name = instance.__class__.__name__

    if cls_name == 'Product':
        if getattr(instance, 'is_active', False):
            instance.is_active = False
            instance.save(update_fields=['is_active'])

    elif cls_name in ('Review', 'ProductReview'):
        # Reviews use ``is_visible`` (preferred) or fall back to
        # ``is_active``. We don't know the exact schema across the
        # two review models, so probe defensively.
        for fname in ('is_visible', 'is_active', 'is_published'):
            if hasattr(instance, fname):
                setattr(instance, fname, False)
                instance.save(update_fields=[fname])
                break

    elif cls_name == 'Listing':
        if hasattr(instance, 'is_active'):
            instance.is_active = False
            instance.save(update_fields=['is_active'])

    elif cls_name == 'Message':
        # Chat: best-effort logging only. The ContentFlag row exists;
        # ops sees the pattern; the message itself still delivers.
        # Auto-blocking individual chat messages would be heavy-handed
        # and breaks UX for legitimate users using flagged words in
        # context.
        pass


def moderate_and_apply(text: str, instance, target_user=None) -> ModerationDecision:
    """Convenience: run moderate() on text, apply decision to instance.

    Used by the signal handlers in apps/moderation/signals.py.
    """
    target_type_map = {
        'Product': 'product',
        'Review': 'review',
        'ProductReview': 'review',
        'Listing': 'listing',
        'Message': 'message',
    }
    target_type = target_type_map.get(
        instance.__class__.__name__, 'product',
    )
    decision = moderate(
        text=text,
        target_type=target_type,
        target_id=instance.pk,
        target_user=target_user,
    )
    apply_decision(instance, decision)
    return decision
