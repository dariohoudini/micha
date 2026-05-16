"""
apps/cases/service.py

Single transition gate — every state change goes through ``transition()``.
Never set Case.status directly outside this file. Every transition writes
a CaseEvent audit row atomically with the status update.

VALID_TRANSITIONS:
  new → triaged | closed
  triaged → investigating | resolved | closed | escalated
  investigating → awaiting_info | resolved | escalated | closed
  awaiting_info → investigating | resolved | closed
  escalated → investigating | resolved | closed
  resolved → reopened (→ investigating)
  closed → (terminal)
"""
from __future__ import annotations
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import (
    Case, CaseEvent, CaseLink, CaseSubject,
    CaseStatus, CasePriority, CaseKind, CaseResolution,
)

log = logging.getLogger(__name__)


class TransitionError(Exception):
    pass


VALID_TRANSITIONS = {
    CaseStatus.NEW:           {CaseStatus.TRIAGED, CaseStatus.CLOSED},
    CaseStatus.TRIAGED:       {CaseStatus.INVESTIGATING, CaseStatus.RESOLVED,
                               CaseStatus.CLOSED, CaseStatus.ESCALATED},
    CaseStatus.INVESTIGATING: {CaseStatus.AWAITING_INFO, CaseStatus.RESOLVED,
                               CaseStatus.ESCALATED, CaseStatus.CLOSED},
    CaseStatus.AWAITING_INFO: {CaseStatus.INVESTIGATING, CaseStatus.RESOLVED,
                               CaseStatus.CLOSED},
    CaseStatus.ESCALATED:     {CaseStatus.INVESTIGATING, CaseStatus.RESOLVED,
                               CaseStatus.CLOSED},
    CaseStatus.RESOLVED:      {CaseStatus.INVESTIGATING},  # via reopen
    CaseStatus.CLOSED:        set(),
}

# SLA windows per priority. URGENT pages someone in 1h; LOW gets a week.
SLA_HOURS = {
    CasePriority.URGENT: 1,
    CasePriority.HIGH:   8,
    CasePriority.NORMAL: 48,
    CasePriority.LOW:    7 * 24,
}


# ─── Open ─────────────────────────────────────────────────────────────────

def open_case(*, kind: str, title: str, priority: str = CasePriority.NORMAL,
              opened_by_user=None, opened_by_admin=None,
              subject_type: str = '', subject_id: str = '',
              summary: str = '') -> Case:
    """Create a new case. Stamps SLA based on priority and writes the
    initial 'opened' event."""
    if kind not in {k.value for k in CaseKind}:
        raise ValueError(f'unknown kind: {kind}')
    if priority not in {p.value for p in CasePriority}:
        raise ValueError(f'unknown priority: {priority}')

    sla_at = timezone.now() + timedelta(hours=SLA_HOURS.get(priority, 48))

    with transaction.atomic():
        case = Case.objects.create(
            title=(title or '')[:200],
            kind=kind, priority=priority,
            subject_type=subject_type[:40], subject_id=str(subject_id)[:80],
            opened_by_user=opened_by_user if (opened_by_user and getattr(opened_by_user, 'is_authenticated', False)) else None,
            opened_by_admin=opened_by_admin if (opened_by_admin and getattr(opened_by_admin, 'is_authenticated', False)) else None,
            summary=summary[:2000], sla_at=sla_at,
        )
        actor = opened_by_admin or opened_by_user
        CaseEvent.objects.create(
            case=case, actor=actor,
            actor_role='admin' if opened_by_admin else ('user' if opened_by_user else 'system'),
            event_type='opened',
            body=summary[:500],
            metadata={'priority': priority, 'kind': kind, 'sla_at': sla_at.isoformat()},
        )
    return case


# ─── Transitions ──────────────────────────────────────────────────────────

def transition(case: Case, to_status: str, *, actor=None,
               actor_role: str = 'admin', note: str = '',
               metadata: dict | None = None,
               admin_override: bool = False) -> Case:
    """Move a case to a new status. Raises TransitionError if not allowed.
    Admin override bypasses the state-machine check but still audits."""
    from_status = case.status

    if not admin_override:
        allowed = VALID_TRANSITIONS.get(from_status, set())
        if to_status not in allowed:
            raise TransitionError(
                f'cannot move case from {from_status} → {to_status}'
            )

    with transaction.atomic():
        c = Case.objects.select_for_update().get(pk=case.pk)
        if c.status != from_status:
            raise TransitionError(
                f'concurrent update — expected {from_status}, found {c.status}'
            )

        c.status = to_status
        update_fields = ['status', 'updated_at']
        # Terminal states stamp resolved_at AND clear the SLA (it's no longer
        # the case's SLA, it's the audit history)
        if to_status in (CaseStatus.RESOLVED, CaseStatus.CLOSED):
            c.resolved_at = timezone.now()
            update_fields.append('resolved_at')
        c.save(update_fields=update_fields)

        meta = dict(metadata or {})
        meta.update({'from': from_status, 'to': to_status})
        if admin_override:
            meta['admin_override'] = True

        CaseEvent.objects.create(
            case=c, actor=actor, actor_role=actor_role,
            event_type='state_change', body=note[:2000], metadata=meta,
        )
    return c


def assign(case: Case, *, to_admin, by_actor=None, note: str = '') -> Case:
    """Assign or re-assign to an admin. Setting to_admin=None unassigns."""
    with transaction.atomic():
        c = Case.objects.select_for_update().get(pk=case.pk)
        old_id = c.assigned_to_id
        c.assigned_to = to_admin
        c.save(update_fields=['assigned_to', 'updated_at'])
        CaseEvent.objects.create(
            case=c, actor=by_actor, actor_role='admin',
            event_type='assigned', body=note[:2000],
            metadata={
                'from_admin_id': old_id,
                'to_admin_id': to_admin.id if to_admin else None,
            },
        )
    return c


def change_priority(case: Case, *, to_priority: str, actor=None, note: str = '') -> Case:
    if to_priority not in {p.value for p in CasePriority}:
        raise ValueError(f'unknown priority: {to_priority}')
    with transaction.atomic():
        c = Case.objects.select_for_update().get(pk=case.pk)
        old = c.priority
        c.priority = to_priority
        # Recompute SLA based on the new priority — unless it's terminal
        if c.status not in (CaseStatus.RESOLVED, CaseStatus.CLOSED):
            c.sla_at = timezone.now() + timedelta(hours=SLA_HOURS.get(to_priority, 48))
        c.save(update_fields=['priority', 'sla_at', 'updated_at'])
        CaseEvent.objects.create(
            case=c, actor=actor, actor_role='admin',
            event_type='priority_change', body=note[:2000],
            metadata={'from': old, 'to': to_priority, 'sla_at': c.sla_at.isoformat() if c.sla_at else None},
        )
    return c


# ─── Resolution ───────────────────────────────────────────────────────────

def resolve(case: Case, *, resolution: str, actor=None, note: str = '') -> Case:
    if resolution not in {r.value for r in CaseResolution}:
        raise ValueError(f'unknown resolution: {resolution}')
    case.resolution = resolution
    case.resolution_note = note[:2000]
    case.save(update_fields=['resolution', 'resolution_note', 'updated_at'])
    return transition(case, CaseStatus.RESOLVED, actor=actor,
                      actor_role='admin', note=note,
                      metadata={'resolution': resolution})


def reopen(case: Case, *, actor=None, note: str = '') -> Case:
    if case.status != CaseStatus.RESOLVED:
        raise TransitionError('only resolved cases can be reopened')
    # Clear the resolution so we don't carry stale data into the next round
    case.resolution = ''
    case.resolution_note = ''
    case.resolved_at = None
    case.save(update_fields=['resolution', 'resolution_note',
                              'resolved_at', 'updated_at'])
    return transition(case, CaseStatus.INVESTIGATING, actor=actor,
                      actor_role='admin', note=note)


# ─── Links + subjects + notes ─────────────────────────────────────────────

def add_link(case: Case, *, link_type: str, ref_type: str, ref_id,
             note: str = '', actor=None) -> CaseLink:
    """Idempotent — duplicate links no-op (returns the existing row)."""
    link, created = CaseLink.objects.get_or_create(
        case=case, link_type=link_type, ref_type=ref_type, ref_id=str(ref_id)[:80],
        defaults={'note': note[:300], 'added_by': actor},
    )
    if created:
        CaseEvent.objects.create(
            case=case, actor=actor, actor_role='admin',
            event_type='link_added',
            body=note[:2000],
            metadata={'link_id': link.id, 'link_type': link_type,
                      'ref_type': ref_type, 'ref_id': str(ref_id)},
        )
    return link


def remove_link(case: Case, link_id: int, *, actor=None, note: str = '') -> bool:
    deleted, _ = CaseLink.objects.filter(case=case, pk=link_id).delete()
    if deleted:
        CaseEvent.objects.create(
            case=case, actor=actor, actor_role='admin',
            event_type='link_removed', body=note[:2000],
            metadata={'link_id': link_id},
        )
    return bool(deleted)


def add_subject(case: Case, *, user, role: str, actor=None) -> CaseSubject:
    sub, created = CaseSubject.objects.get_or_create(
        case=case, user=user, role=role,
    )
    if created:
        CaseEvent.objects.create(
            case=case, actor=actor, actor_role='admin',
            event_type='subject_added',
            metadata={'user_id': user.id, 'role': role},
        )
    return sub


def add_note(case: Case, *, body: str, actor=None,
             actor_role: str = 'admin') -> CaseEvent:
    return CaseEvent.objects.create(
        case=case, actor=actor, actor_role=actor_role,
        event_type='note', body=body[:5000],
    )
