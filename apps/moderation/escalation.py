"""
apps/moderation/escalation.py
─────────────────────────────

Repeat-offender escalation: after a moderator REJECTS a ContentFlag
against a user, count how many rejections that user has accumulated
in the rolling infraction window. Above SUSPEND_THRESHOLD → suspend;
above BAN_THRESHOLD → ban.

Why this exists
────────────────
Without escalation, the same scammer can re-list the same fake product
ten times a day. The moderation queue catches each one individually,
but the *user* sees zero consequences — they just resubmit. R4 closes
that loop: every confirmed-bad flag accumulates against the owner;
thresholds auto-suspend.

Public API
──────────
  evaluate_user(user, request=None) -> EscalationResult
      Called from the moderator-reject path. Counts recent rejections
      against ``user``, applies suspend / ban if a threshold is hit,
      and writes an AdminActionLog row. Idempotent: if the user is
      already suspended/banned, returns without re-suspending.

Settings (all optional, sensible defaults)
───────────────────────────────────────────
  MODERATION_SUSPEND_THRESHOLD       default 3
  MODERATION_BAN_THRESHOLD           default 5
  MODERATION_INFRACTION_WINDOW_DAYS  default 30
  MODERATION_ESCALATION_ENABLED      default True
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone

log = logging.getLogger(__name__)


# ─── Thresholds ───────────────────────────────────────────────────────

def _suspend_threshold() -> int:
    return int(getattr(settings, 'MODERATION_SUSPEND_THRESHOLD', 3))


def _ban_threshold() -> int:
    return int(getattr(settings, 'MODERATION_BAN_THRESHOLD', 5))


def _window_days() -> int:
    return int(getattr(settings, 'MODERATION_INFRACTION_WINDOW_DAYS', 30))


def _enabled() -> bool:
    return bool(getattr(settings, 'MODERATION_ESCALATION_ENABLED', True))


# ─── Result ───────────────────────────────────────────────────────────

@dataclass
class EscalationResult:
    """Outcome of an escalation evaluation."""
    user_id: int
    infractions: int        # confirmed rejections in window
    action: str             # 'none' | 'suspend' | 'ban' | 'already_suspended' | 'already_banned' | 'disabled'
    previous_status: str    # status before evaluation
    new_status: str         # status after (may be same as previous)


# ─── Public: evaluate_user ────────────────────────────────────────────

def evaluate_user(user, request=None) -> EscalationResult:
    """Apply escalation thresholds against ``user``.

    Pulled out of the view layer so the same logic runs from:
      • moderator reject endpoint (synchronous)
      • automated dispute-resolution path (Celery task)
      • bulk-moderation tool (management command)

    Atomic: locks the user row before updating status to avoid two
    concurrent rejections both suspending (which would write two
    AdminActionLog rows for the same transition).

    Returns an EscalationResult — callers can use it to shape the
    response payload ("flag rejected + user suspended").
    """
    from django.contrib.auth import get_user_model
    from apps.moderation.models import ContentFlag

    if not _enabled():
        return EscalationResult(
            user_id=getattr(user, 'pk', 0),
            infractions=0,
            action='disabled',
            previous_status=getattr(user, 'status', ''),
            new_status=getattr(user, 'status', ''),
        )

    User = get_user_model()
    suspend_n = _suspend_threshold()
    ban_n = _ban_threshold()
    window_start = timezone.now() - timedelta(days=_window_days())

    with transaction.atomic():
        # Lock the user row so concurrent rejections can't double-suspend.
        locked = User.objects.select_for_update().get(pk=user.pk)
        previous_status = locked.status

        # Already terminal — no-op.
        if previous_status == 'banned':
            return EscalationResult(
                user_id=locked.pk, infractions=0,
                action='already_banned',
                previous_status=previous_status,
                new_status=previous_status,
            )

        # Count rejections in the window. ``rejected`` is the moderator-
        # confirmed-bad status; ``escalated`` doesn't count yet (it's
        # under review). Past suspensions don't reset the counter —
        # that's intentional, a previously-suspended user reoffending
        # should escalate faster.
        infractions = ContentFlag.objects.filter(
            target_user=locked,
            status='rejected',
            resolved_at__gte=window_start,
        ).count()

        action = 'none'
        new_status = previous_status

        if infractions >= ban_n:
            if previous_status != 'banned':
                locked.status = 'banned'
                locked.is_active = False  # belt + suspenders — login refused
                locked.save(update_fields=['status', 'is_active'])
                action = 'ban'
                new_status = 'banned'
        elif infractions >= suspend_n:
            if previous_status not in ('suspended', 'banned'):
                locked.status = 'suspended'
                locked.save(update_fields=['status'])
                action = 'suspend'
                new_status = 'suspended'
            else:
                action = 'already_suspended'

    # AdminActionLog write happens outside the lock — it's an
    # append-only audit table and doesn't need the user lock.
    if action in ('suspend', 'ban'):
        _audit_escalation(
            request=request,
            target_user=locked,
            action=action,
            infractions=infractions,
        )
        log.warning(
            'moderation_escalation',
            extra={
                'user_id': locked.pk,
                'action': action,
                'infractions': infractions,
                'window_days': _window_days(),
            },
        )

    return EscalationResult(
        user_id=locked.pk,
        infractions=infractions,
        action=action,
        previous_status=previous_status,
        new_status=new_status,
    )


def _audit_escalation(*, request, target_user, action: str, infractions: int) -> None:
    """Write an AdminActionLog row for the escalation event.

    Failure here must not abort the escalation — the user is already
    suspended; logging being unavailable is a monitoring issue, not a
    correctness one.
    """
    try:
        from apps.admin_actions.models import AdminActionLog
        action_type = 'suspend_user' if action == 'suspend' else 'ban_user'
        if request is None or not getattr(request, 'user', None) \
                or not getattr(request.user, 'is_authenticated', False):
            # No request context (system-triggered) — AdminActionLog.log
            # requires request.user to set ``admin`` FK. Skip the audit
            # row; the WARNING log line above is the audit trail in
            # that case. The reject-from-view path always has request.
            return
        AdminActionLog.log(
            request=request,
            action=action_type,
            target=target_user,
            note=(
                f'Auto-escalated by moderation engine: '
                f'{infractions} rejected flag(s) in {_window_days()}d window'
            ),
            metadata={
                'source': 'moderation_escalation',
                'infractions': infractions,
                'window_days': _window_days(),
                'suspend_threshold': _suspend_threshold(),
                'ban_threshold': _ban_threshold(),
            },
        )
    except Exception:
        log.warning(
            'moderation: failed to write AdminActionLog for escalation',
            exc_info=True,
        )
