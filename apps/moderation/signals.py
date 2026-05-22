"""
apps/moderation/signals.py
───────────────────────────

post_save signal handlers that route new user-generated content
through the moderation service.

Why signals (vs explicit view calls)
─────────────────────────────────────
A view-based moderation hook is bypassable:
  • Management commands that create products miss it.
  • Bulk import flows miss it.
  • Future API endpoints written without the hook miss it.
  • Admin UI creates miss it.

Signal-based hook catches ALL creation paths — including the ones
nobody has thought of yet. The signal fires AFTER the save, which
means:
  • The row exists with its target PK before moderation runs (needed
    for ContentFlag.target_id).
  • Moderation can set ``is_active=False`` and save again as a
    second-pass update.

Why post_save (not pre_save)
─────────────────────────────
We need the instance PK for the ContentFlag row. pre_save runs before
the INSERT so PK isn't allocated yet on most backends. Cost: the
flagged content briefly exists with default visibility before the
signal handler hides it. Acceptable trade-off because:
  • Default visibility is is_active=False on most models anyway (e.g.
    Product needs publish_at to be set).
  • The signal handler runs synchronously in the same request — there's
    no observable window where flagged content is publicly visible.

Performance
────────────
The keyword check is a Python ``in`` over a small list — microseconds
per row. The DB write of ContentFlag only happens on REVIEW (i.e.,
content matches a keyword), which should be the minority of saves.
Net per-save cost: one Python loop + one conditional DB write.

Skip-paths
───────────
The handler honours an instance attribute ``_skip_moderation``
(set on bulk-import / fixture flows where moderation has already been
applied or isn't desired). Defence: trust this attribute only when
the calling code explicitly sets it.
"""
from __future__ import annotations

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

log = logging.getLogger(__name__)


def _gather_text(instance) -> str:
    """Build the combined text blob to moderate from an instance.

    Each model has different text fields; pick the relevant ones per
    type. We concatenate so the moderator sees "title + description"
    as one logical content unit.
    """
    cls_name = instance.__class__.__name__
    parts = []

    if cls_name == 'Product':
        parts.append(getattr(instance, 'title', '') or '')
        parts.append(getattr(instance, 'description', '') or '')
    elif cls_name in ('Review', 'ProductReview'):
        parts.append(getattr(instance, 'title', '') or '')
        parts.append(getattr(instance, 'comment', '') or '')
    elif cls_name == 'Listing':
        parts.append(getattr(instance, 'title', '') or '')
        parts.append(getattr(instance, 'description', '') or '')
    elif cls_name == 'Message':
        parts.append(getattr(instance, 'content', '') or '')

    return ' '.join(p for p in parts if p).strip()


def _resolve_user(instance):
    """Find the user who created the instance, if available. Used by
    moderation rules that incorporate per-user reputation."""
    for fname in ('seller', 'user', 'buyer', 'sender', 'author', 'created_by'):
        u = getattr(instance, fname, None)
        if u is not None:
            return u
    return None


def _moderate_handler(sender, instance, created, **kwargs):
    """Route a newly-created instance through the moderation service.

    Only fires on creation (created=True). Updates skip moderation —
    the original creator's content has already been reviewed; an edit
    by the same user shouldn't re-trigger flags. (Roadmap 4 may add
    re-moderation on edit for high-risk content classes.)
    """
    if not created:
        return
    if getattr(instance, '_skip_moderation', False):
        return

    try:
        from .service import moderate_and_apply
        text = _gather_text(instance)
        if not text:
            return
        decision = moderate_and_apply(
            text=text,
            instance=instance,
            target_user=_resolve_user(instance),
        )
        # Stash the decision on the instance for downstream code that
        # wants to short-circuit (e.g. don't send "your product is
        # live" notifications if the product is in REVIEW state).
        instance._moderation_decision = decision
    except Exception:
        # Moderation is best-effort; never break the create flow.
        log.exception(
            'moderation.signals: handler raised on %s',
            instance.__class__.__name__,
        )


# We connect signals in apps.py:ready() so they only fire after Django
# has finished loading all apps. The receiver decorator at module level
# would attach the handler too early during app registry build.

def register():
    """Connect post_save signals for the moderated models.

    Called from apps/moderation/apps.py:ModerationConfig.ready().
    """
    from django.apps import apps as django_apps

    for app_label, model_name in (
        ('products', 'Product'),
        ('reviews', 'Review'),
        ('reviews', 'ProductReview'),
        ('listings', 'Listing'),
        ('chat', 'Message'),
    ):
        try:
            model = django_apps.get_model(app_label, model_name)
        except LookupError:
            continue
        if model is None:
            continue
        # ``dispatch_uid`` prevents double-registration if ready() runs
        # twice (uncommon but possible under runserver autoreload).
        post_save.connect(
            _moderate_handler,
            sender=model,
            dispatch_uid=f'moderation_post_save_{app_label}_{model_name}',
        )
        log.debug('moderation: connected post_save for %s.%s',
                  app_label, model_name)
