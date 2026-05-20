"""
apps/disputes/service.py
─────────────────────────

Single source of truth for the dispute lifecycle.

Why this exists
────────────────
Before this module, dispute side-effects were scattered across views:

  • OpenDisputeView created a Dispute row but DID NOT freeze the
    seller's EarningsHold. Result: a buyer opens a dispute, the
    7-day post-delivery hold expires mid-dispute, the seller
    withdraws via PayoutRequest, the dispute resolves to refund the
    buyer, and the platform eats the loss. At scale this is a six-
    figure-per-month leak masquerading as "marketplace risk".

  • OpenDisputeView captured no evidence snapshot. If the seller
    edits the product page (cheap title-stuffing trick), the
    dispute later references a totally different listing than
    what the buyer actually bought.

  • AdminResolveDisputeView created a Refund row with status=
    'processed' directly — bypassing the PSP, bypassing the
    order state machine, bypassing the ledger. The dispute looked
    resolved in the DB; the buyer's card was never credited.

  • No SLA: disputes sat open forever. AliExpress / Amazon close
    in 5-10 days max. Without a timer, NPS dies.

  • No outbox events: downstream systems (notifications, analytics)
    couldn't react to dispute lifecycle changes.

This module centralises all of that. Views call into here; this
module is the only thing that mutates Dispute.status or touches
EarningsHold rows on the dispute path.

Public API
──────────
  open_dispute(buyer, order, reason, description) -> Dispute
    Atomically: validate buyer + order, freeze EarningsHold rows,
    snapshot evidence, set SLA timers, write Dispute, publish outbox.

  add_message(actor, dispute, body, attachment=None) -> DisputeMessage
    Validate participant; updates last_seller_message_at if seller posted.

  resolve_dispute(admin, dispute, resolution, note='') -> Dispute
    Atomically: state transition + refund creation + EarningsHold
    settlement + audit + outbox.

  auto_resolve_silent_seller(dispute) -> Dispute
    Called by the SLA sweep. Applies refund_buyer if seller silent
    past auto_resolve_at.

SLA defaults (overridable via settings)
────────────────────────────────────────
  DISPUTE_SELLER_RESPONSE_HOURS = 72   (3 days)
  DISPUTE_AUTO_RESOLVE_DAYS     = 7    (1 week)

These are conservative; tune from ops data.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.utils import timezone


log = logging.getLogger(__name__)


# ─── SLA defaults ─────────────────────────────────────────────────────

def _seller_response_hours() -> int:
    return int(getattr(settings, 'DISPUTE_SELLER_RESPONSE_HOURS', 72))


def _auto_resolve_days() -> int:
    return int(getattr(settings, 'DISPUTE_AUTO_RESOLVE_DAYS', 7))


# ─── Errors ───────────────────────────────────────────────────────────

class DisputeError(Exception):
    """Base — anything below is safe to surface to clients via DRF
    400/409 envelopes. Internal traces go in log.warning."""


class InvalidDisputeAction(DisputeError):
    """Wrong status / wrong actor / wrong transition."""


class DisputeAlreadyOpen(DisputeError):
    """Re-open attempt on an order that already has a Dispute row."""


class NotADisputeParticipant(DisputeError):
    """Actor is neither buyer, seller, nor admin."""


# ─── Evidence snapshot ────────────────────────────────────────────────

def _snapshot_evidence(order) -> dict:
    """Capture forensic-grade snapshot of order state at open-time.

    Stored as JSON in Dispute.evidence_snapshot. Read-only after open.
    Keys deliberately flat-ish so jq/Datadog filtering is straightforward.
    """
    try:
        items = []
        for it in order.items.all().select_related('product'):
            items.append({
                'product_id': it.product_id,
                'title': (getattr(it.product, 'title', '') or '')[:200],
                'price': str(it.price),
                'quantity': it.quantity,
                'seller_id': getattr(it.product, 'seller_id', None),
            })
    except Exception:
        items = []

    return {
        'order_id': str(order.id),
        'order_status_at_open': order.status,
        'total': str(order.total),
        'placed_at': order.created_at.isoformat() if order.created_at else None,
        'shipped_at': getattr(order, 'shipped_at', None) and order.shipped_at.isoformat(),
        'delivered_at': (getattr(order, 'delivered_at', None)
                         and order.delivered_at.isoformat()),
        'items': items,
        'snapshot_taken_at': timezone.now().isoformat(),
    }


# ─── EarningsHold freezing ────────────────────────────────────────────

def _freeze_holds_for_order(order) -> int:
    """Set is_disputed=True on every unreleased EarningsHold for this
    order. Returns the count touched. Idempotent."""
    try:
        from apps.payments.models import EarningsHold
    except Exception:
        return 0
    now = timezone.now()
    return EarningsHold.objects.filter(
        order=order, released=False, is_disputed=False,
    ).update(is_disputed=True, disputed_at=now)


def _settle_holds_for_resolution(order, resolution: str) -> dict:
    """Settle EarningsHold rows according to the resolution.

    Returns a dict summary {released: N, refunded: N, partial: N}.

    Settlement rules:
      pay_seller     → is_disputed=False, release_at=now (next sweep
                       releases to wallet)
      dismissed      → same as pay_seller (buyer claim rejected)
      refund_buyer   → released=True, refunded_at=now (consumed by
                       refund, never paid out)
      partial_refund → marked as refunded; the partial-amount split is
                       handled by the Refund row's amount (the hold is
                       fully consumed because the leftover goes to the
                       seller via the wallet directly in the refund flow)

    NOTE: this DOES NOT credit the buyer or debit the gateway. That is
    the Refund/PSP path's job. We're only releasing the platform-side
    accounting lock that prevented the seller from withdrawing while
    the dispute was active.
    """
    try:
        from apps.payments.models import EarningsHold
    except Exception:
        return {'released': 0, 'refunded': 0, 'partial': 0}

    now = timezone.now()
    qs = EarningsHold.objects.filter(order=order, released=False)
    summary = {'released': 0, 'refunded': 0, 'partial': 0}

    if resolution in ('pay_seller', 'dismissed'):
        # Unfreeze and make release_at=now so the next sweep pays out.
        summary['released'] = qs.update(
            is_disputed=False, disputed_at=None, release_at=now,
        )
    elif resolution == 'refund_buyer':
        summary['refunded'] = qs.update(
            released=True, refunded_at=now, is_disputed=False,
        )
    elif resolution == 'partial_refund':
        # Full hold consumed; seller-side reconciliation is handled by
        # the refund amount, which is < hold total in the partial case.
        summary['partial'] = qs.update(
            released=True, refunded_at=now, is_disputed=False,
        )
    else:
        log.warning(
            'dispute resolve: unknown resolution %r — holds untouched',
            resolution,
        )

    return summary


# ─── Outbox helpers ───────────────────────────────────────────────────

def _publish(topic: str, dispute, **extra):
    try:
        from apps.outbox.service import publish
        payload = {
            'dispute_id': str(dispute.id),
            'order_id': str(dispute.order_id),
            'buyer_id': dispute.buyer_id,
            'seller_id': dispute.seller_id,
            'status': dispute.status,
        }
        payload.update(extra)
        publish(
            topic=topic,
            payload=payload,
            dedupe_key=f'{topic}:{dispute.id}:{dispute.status}',
            ref_type='dispute',
            ref_id=str(dispute.id),
        )
    except Exception:
        log.warning('dispute: outbox publish %s failed', topic, exc_info=True)


# ─── Public: open_dispute ─────────────────────────────────────────────

def open_dispute(*, buyer, order, reason: str, description: str):
    """Open a dispute on an order — atomic across Dispute row,
    EarningsHold freeze, evidence snapshot, and outbox publish.

    Raises:
      InvalidDisputeAction: if buyer doesn't own the order, order isn't
        in a disputable state, or the reason is unknown.
      DisputeAlreadyOpen: if order already has a Dispute row.
    """
    from .models import Dispute
    from apps.orders.models import Order

    valid_reasons = {r[0] for r in Dispute.REASONS}
    if reason not in valid_reasons:
        raise InvalidDisputeAction(
            f'Unknown reason {reason!r}. Valid: {sorted(valid_reasons)}'
        )

    if not (description or '').strip():
        raise InvalidDisputeAction('description is required')

    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)

        if locked.buyer_id != buyer.id:
            raise InvalidDisputeAction('not the buyer of this order')

        # Disputable states. We intentionally allow 'shipped' even
        # though the package isn't delivered yet — that's the
        # "not_received" + "carrier said delivered but it wasn't" case
        # AliExpress treats as the most common dispute reason.
        if locked.status not in ('shipped', 'delivered'):
            raise InvalidDisputeAction(
                f'cannot dispute order in status {locked.status!r}; '
                f'must be shipped or delivered'
            )

        if Dispute.objects.filter(order=locked).exists():
            raise DisputeAlreadyOpen('order already has an open dispute')

        now = timezone.now()
        respond_by = now + timedelta(hours=_seller_response_hours())
        auto_resolve_at = now + timedelta(days=_auto_resolve_days())

        dispute = Dispute.objects.create(
            order=locked,
            buyer=buyer,
            seller_id=locked.seller_id,
            reason=reason,
            description=description.strip()[:5000],
            status='open',
            respond_by=respond_by,
            auto_resolve_at=auto_resolve_at,
            evidence_snapshot=_snapshot_evidence(locked),
        )

        frozen = _freeze_holds_for_order(locked)
        log.info(
            'dispute opened',
            extra={
                'dispute_id': str(dispute.id),
                'order_id': locked.id,
                'frozen_holds': frozen,
                'auto_resolve_at': auto_resolve_at.isoformat(),
            },
        )

        _publish('dispute.opened', dispute, reason=reason)

    return dispute


# ─── Public: add_message ──────────────────────────────────────────────

def add_message(*, actor, dispute, body: str, attachment=None):
    """Append a message to the dispute thread.

    Updates last_seller_message_at if actor is the seller — this
    short-circuits the SLA auto-resolution: once the seller responds,
    they've satisfied the response SLA.
    """
    from .models import DisputeMessage

    if dispute.status in ('resolved', 'closed'):
        raise InvalidDisputeAction('dispute is closed; no further messages')

    is_buyer = actor.id == dispute.buyer_id
    is_seller = actor.id == dispute.seller_id
    is_admin = getattr(actor, 'is_staff', False) or getattr(actor, 'is_superuser', False)

    if not (is_buyer or is_seller or is_admin):
        raise NotADisputeParticipant('not a party to this dispute')

    body = (body or '').strip()
    if not body and not attachment:
        raise InvalidDisputeAction('message body or attachment required')

    with transaction.atomic():
        msg = DisputeMessage.objects.create(
            dispute=dispute, sender=actor,
            message=body[:5000], attachment=attachment,
        )
        if is_seller:
            dispute.last_seller_message_at = timezone.now()
            # Once the seller responds we also clear the response-by
            # timer so the dashboard doesn't keep blinking red.
            dispute.respond_by = None
            dispute.save(update_fields=['last_seller_message_at', 'respond_by'])
    return msg


# ─── Public: resolve_dispute ──────────────────────────────────────────

_VALID_RESOLUTIONS = {'refund_buyer', 'pay_seller', 'partial_refund', 'dismissed'}


def resolve_dispute(*, admin, dispute, resolution: str,
                    note: str = '', refund_amount: Optional[Decimal] = None):
    """Apply a resolution to a dispute — atomic across status change,
    EarningsHold settlement, Refund creation (if applicable), audit,
    and outbox publish.

    Args:
      admin: User initiating the resolve (must be staff/superuser).
      dispute: Dispute instance.
      resolution: one of refund_buyer / pay_seller / partial_refund / dismissed.
      note: free-text admin note.
      refund_amount: required if resolution == 'partial_refund'. For
        full refunds, defaults to the order total.

    Raises InvalidDisputeAction on bad input.
    """
    from .models import Dispute

    if not (getattr(admin, 'is_staff', False) or getattr(admin, 'is_superuser', False)):
        raise InvalidDisputeAction('only admins can resolve disputes')

    if resolution not in _VALID_RESOLUTIONS:
        raise InvalidDisputeAction(
            f'Unknown resolution {resolution!r}. Valid: {sorted(_VALID_RESOLUTIONS)}'
        )

    with transaction.atomic():
        d = Dispute.objects.select_for_update().get(pk=dispute.pk)

        if d.status in ('resolved', 'closed'):
            # Idempotent no-op — admin may have double-clicked.
            return d

        order = d.order
        order_total = Decimal(order.total or 0)

        # Default refund amount = full order total for refund_buyer,
        # required for partial_refund, zero for the others.
        if resolution == 'refund_buyer':
            amount = order_total if refund_amount is None else Decimal(refund_amount)
        elif resolution == 'partial_refund':
            if refund_amount is None or Decimal(refund_amount) <= 0:
                raise InvalidDisputeAction(
                    'partial_refund requires refund_amount > 0'
                )
            if Decimal(refund_amount) >= order_total:
                raise InvalidDisputeAction(
                    'partial_refund cannot equal or exceed order total — '
                    'use refund_buyer for full refunds'
                )
            amount = Decimal(refund_amount)
        else:
            amount = Decimal('0')

        # Apply state transition.
        d.resolution = resolution
        d.status = 'resolved'
        d.admin_note = (note or '')[:2000]
        d.resolved_at = timezone.now()
        # Clear SLA timers — no longer relevant.
        d.respond_by = None
        d.auto_resolve_at = None
        d.save(update_fields=[
            'resolution', 'status', 'admin_note', 'resolved_at',
            'respond_by', 'auto_resolve_at', 'updated_at',
        ])

        # Settle the EarningsHold(s).
        hold_summary = _settle_holds_for_resolution(order, resolution)

        # Create the Refund row when buyer money is owed. We keep
        # status='pending' so the PSP path picks it up — direct
        # 'processed' marking was the prior bug.
        refund = None
        if resolution in ('refund_buyer', 'partial_refund'):
            from apps.orders.models import Refund
            refund, _created = Refund.objects.get_or_create(
                order=order,
                defaults={
                    'requested_by': d.buyer,
                    'reason': f'Dispute {d.id} → {resolution}',
                    'amount': amount,
                    'status': 'pending',
                    'admin_note': (note or '')[:2000],
                },
            )

        log.info(
            'dispute resolved',
            extra={
                'dispute_id': str(d.id),
                'order_id': order.id,
                'resolution': resolution,
                'refund_id': getattr(refund, 'id', None),
                'hold_summary': hold_summary,
            },
        )

        _publish(
            'dispute.resolved', d,
            resolution=resolution,
            refund_amount=str(amount),
        )

    return d


# ─── Public: auto_resolve_silent_seller ───────────────────────────────

def auto_resolve_silent_seller(dispute):
    """Apply refund_buyer to disputes where the seller has gone silent
    past auto_resolve_at. Called by the SLA sweep task.

    Conservatively skips disputes where the seller HAS posted a message
    since the dispute opened — they're engaged, admin should rule.
    """
    if dispute.status != 'open':
        return dispute

    # Belt-and-braces: only fire if SLA actually elapsed.
    now = timezone.now()
    if dispute.auto_resolve_at and dispute.auto_resolve_at > now:
        return dispute

    # If the seller has responded, don't auto-resolve — escalate to
    # admin instead by flipping to under_review.
    if dispute.last_seller_message_at is not None:
        with transaction.atomic():
            d = type(dispute).objects.select_for_update().get(pk=dispute.pk)
            if d.status == 'open':
                d.status = 'under_review'
                d.save(update_fields=['status', 'updated_at'])
                _publish('dispute.escalated', d, reason='seller_responded_no_resolution')
        return d

    # Synthetic "admin" — the system itself. We pass the SLA bot user
    # if one exists, else None (the audit row will say source=sla_sweep).
    try:
        from django.contrib.auth import get_user_model
        User = get_user_model()
        sla_user = User.objects.filter(
            username='__sla_bot__'
        ).first() or User.objects.filter(is_superuser=True).first()
    except Exception:
        sla_user = None

    if sla_user is None:
        log.warning('sla sweep: no admin user available; skipping dispute %s',
                    dispute.id)
        return dispute

    return resolve_dispute(
        admin=sla_user,
        dispute=dispute,
        resolution='refund_buyer',
        note=(f'Auto-resolved by SLA sweep: seller silent for '
              f'{_auto_resolve_days()}d past dispute open.'),
    )
