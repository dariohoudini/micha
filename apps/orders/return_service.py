"""
apps/orders/return_service.py

Service layer for return state transitions. Every state change goes through
``transition()`` — never set ReturnRequest.status directly outside this file.

Why a service layer:
  - Validates allowed transitions (state machine integrity)
  - Stamps the audit trail (ReturnEvent) atomically with the status change
  - Publishes an outbox event per transition (so seller webhooks fire,
    notifications go out, etc.)
  - Triggers side-effects safely (deadline updates, refunds via saga)
"""
from __future__ import annotations
import logging
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .return_models import (
    ReturnRequest, ReturnEvent, ReturnStatus,
    PICKUP_DEADLINE_DAYS, ESCALATION_WINDOW_HOURS,
)

log = logging.getLogger(__name__)


class TransitionError(Exception):
    pass


# Allowed transitions per actor role. ``admin`` can do anything via the
# override endpoint, so it's not listed here — admin transitions still
# record an audit row but skip this check.
VALID_TRANSITIONS = {
    'buyer': {
        ReturnStatus.PENDING:   {ReturnStatus.WITHDRAWN},
        ReturnStatus.REJECTED:  {ReturnStatus.ESCALATED},
    },
    'seller': {
        ReturnStatus.PENDING:        {ReturnStatus.APPROVED, ReturnStatus.REJECTED},
        ReturnStatus.APPROVED:       {ReturnStatus.COMPLETED, ReturnStatus.REJECTED},
        ReturnStatus.AUTO_APPROVED:  {ReturnStatus.COMPLETED},
    },
    'system': {
        # SLA enforcement
        ReturnStatus.PENDING:   {ReturnStatus.AUTO_APPROVED},
        ReturnStatus.APPROVED:  {ReturnStatus.CANCELLED},
        ReturnStatus.AUTO_APPROVED: {ReturnStatus.CANCELLED},
    },
}


def transition(
    return_request: ReturnRequest,
    to_status: str,
    *,
    actor=None,
    actor_role: str,
    note: str = '',
    metadata: dict | None = None,
    admin_override: bool = False,
):
    """Move a return to a new status. Returns the saved ReturnRequest.

    Raises TransitionError if the move isn't allowed for the actor role.
    Admin overrides bypass the state-machine check but still record the
    audit event with admin_override=True in metadata.
    """
    from_status = return_request.status

    if not admin_override:
        allowed = VALID_TRANSITIONS.get(actor_role, {}).get(from_status, set())
        if to_status not in allowed:
            raise TransitionError(
                f'{actor_role} cannot move return from {from_status} → {to_status}'
            )

    with transaction.atomic():
        # Lock the row so two concurrent actors (seller approve / buyer
        # withdraw at the same instant) can't both win.
        rr = (
            ReturnRequest.objects.select_for_update().get(pk=return_request.pk)
        )
        if rr.status != from_status:
            # Someone beat us — re-check against the fresh status.
            raise TransitionError(
                f'state changed under us: expected {from_status}, found {rr.status}'
            )

        rr.status = to_status

        # Side-effects per destination state
        if to_status in (ReturnStatus.APPROVED, ReturnStatus.AUTO_APPROVED):
            rr.pickup_deadline_at = timezone.now() + timedelta(days=PICKUP_DEADLINE_DAYS)
        elif to_status == ReturnStatus.REJECTED:
            rr.escalation_deadline_at = (
                timezone.now() + timedelta(hours=ESCALATION_WINDOW_HOURS)
            )
        elif to_status in (
            ReturnStatus.COMPLETED, ReturnStatus.WITHDRAWN,
            ReturnStatus.CANCELLED, ReturnStatus.ESCALATED,
        ):
            # Terminal-or-paused states clear all open deadlines.
            rr.seller_response_deadline_at = None
            rr.pickup_deadline_at = None

        rr.save(update_fields=[
            'status', 'seller_response_deadline_at',
            'pickup_deadline_at', 'escalation_deadline_at', 'updated_at',
        ])

        meta = dict(metadata or {})
        if admin_override:
            meta['admin_override'] = True
        ReturnEvent.objects.create(
            return_request=rr, actor=actor, actor_role=actor_role,
            from_status=from_status, to_status=to_status,
            note=note[:500], metadata=meta,
        )

    # Outbox event — outside the DB transaction so a publish failure doesn't
    # roll back the state change.
    _publish_transition(rr, from_status, to_status, actor_role, meta)

    # Kick off the completion saga for terminal "we owe the buyer money" states.
    if to_status == ReturnStatus.COMPLETED:
        _kick_completion_saga(rr)

    return rr


def _publish_transition(rr, from_status, to_status, actor_role, metadata):
    """Emit one outbox event per transition. Topic naming convention:
    ``return.<to_status>`` — matches the webhook subscription whitelist."""
    try:
        from apps.outbox.service import publish
        topic = f'return.{to_status}'
        # Map a couple of states to the cleaner topic names sellers care about.
        if to_status == ReturnStatus.AUTO_APPROVED:
            topic = 'return.approved'  # webhook subscribers see this as approval
        publish(
            topic=topic,
            payload={
                'return_id': rr.id,
                'order_id': str(rr.order_id),
                'buyer_id': rr.buyer_id,
                'from_status': from_status,
                'to_status': to_status,
                'actor_role': actor_role,
                'metadata': metadata,
            },
            dedupe_key=f'return.{rr.id}.{from_status}-{to_status}.{int(timezone.now().timestamp())}',
            ref_type='return', ref_id=str(rr.id),
        )
    except Exception as e:
        log.warning('publish return transition failed: %s', e)


def _kick_completion_saga(rr):
    """Spawn a saga to do the refund + restock + notify atomically (with
    compensations if any step fails)."""
    try:
        from apps.sagas.runner import start, run
        s = start(
            'return_completion', ref_type='return', ref_id=str(rr.id),
            payload={'return_id': rr.id, 'order_id': str(rr.order_id)},
        )
        run(s.id)
    except Exception as e:
        log.exception('return completion saga failed to start: %s', e)


# ─── Buyer convenience entrypoints ─────────────────────────────────────────

def buyer_withdraw(rr, *, actor, note=''):
    return transition(rr, ReturnStatus.WITHDRAWN,
                      actor=actor, actor_role='buyer', note=note)


def buyer_escalate(rr, *, actor, note=''):
    # Enforce the escalation window: if the buyer waited too long after a
    # rejection, the dispute is no longer available.
    if rr.escalation_deadline_at and timezone.now() > rr.escalation_deadline_at:
        raise TransitionError('escalation window has lapsed')
    return transition(rr, ReturnStatus.ESCALATED,
                      actor=actor, actor_role='buyer', note=note)


# ─── Seller convenience entrypoints ────────────────────────────────────────

def seller_approve(rr, *, actor, note=''):
    return transition(rr, ReturnStatus.APPROVED,
                      actor=actor, actor_role='seller', note=note)


def seller_reject(rr, *, actor, note=''):
    return transition(rr, ReturnStatus.REJECTED,
                      actor=actor, actor_role='seller', note=note)


def seller_complete(rr, *, actor, note=''):
    return transition(rr, ReturnStatus.COMPLETED,
                      actor=actor, actor_role='seller', note=note)


# ─── System (sweeper) entrypoints ──────────────────────────────────────────

def system_auto_approve(rr, *, note='seller SLA missed'):
    return transition(rr, ReturnStatus.AUTO_APPROVED,
                      actor=None, actor_role='system', note=note)


def system_cancel_for_pickup_timeout(rr, *, note='buyer pickup window lapsed'):
    return transition(rr, ReturnStatus.CANCELLED,
                      actor=None, actor_role='system', note=note)
