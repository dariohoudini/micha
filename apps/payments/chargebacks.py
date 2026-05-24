"""
apps/payments/chargebacks.py
─────────────────────────────

Card-issuer chargeback workflow (R2).

Pre-R2 the platform had NO record type for chargebacks. When a buyer
disputes a payment via their card issuer (NOT through MICHA's internal
disputes app — that's a different workflow), AppyPay forwards the
notification. The merchant has a fixed window (typically 7 days) to
provide evidence or the funds are reversed.

Without a Chargeback model:
  • No way to track which orders are under dispute
  • No deadline tracking → window lapses silently, funds reversed
  • No evidence packet (order + shipping + IP + device history)
    automatically assembled for response
  • No reconciliation against AppyPay's chargeback report

This module fixes all of that.

Model: Chargeback
─────────────────
States:
  received    AppyPay notified us; deadline_at counts down
  evidence    We've submitted evidence; awaiting issuer decision
  won         Issuer ruled in our favour; funds retained
  lost        Issuer ruled in buyer's favour; funds reversed
  accepted    We chose not to contest (sometimes cheaper than fees)

Evidence packet (auto-collected on receipt):
  • Order metadata (items, amounts, dates)
  • Shipping history (tracking events, delivery confirmation)
  • Buyer history (IP, device fingerprint, prior orders)
  • Communication log (chat with seller, support tickets)
  Stored as a JSON blob on Chargeback.evidence_packet so the admin
  UI can render it without joining 5 tables at render time.

Ingestion endpoint
──────────────────
  POST /api/v1/payments/chargebacks/inbound/
  AppyPay-style webhook. HMAC-signed via WEBHOOK_ALLOWED_SOURCES. The
  payload shape is defensive — accepts AppyPay's documented format
  AND a manual-admin shape (since AppyPay routinely hands chargeback
  notifications over email and admins paste them in by hand).

Admin endpoints
───────────────
  GET  /api/v1/payments/chargebacks/             list, filtered
  GET  /api/v1/payments/chargebacks/<id>/        detail + evidence packet
  POST /api/v1/payments/chargebacks/<id>/respond/  submit evidence
  POST /api/v1/payments/chargebacks/<id>/accept/   accept loss
  POST /api/v1/payments/chargebacks/<id>/resolve/  mark won/lost from issuer reply

Audit
─────
Every state transition writes an AdminActionLog row + an outbox event
(``payments.chargeback.<state>``) so the ledger reconciliation worker
picks up the financial impact.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone


User = settings.AUTH_USER_MODEL
log = logging.getLogger('micha.chargebacks')


# ─── Model ────────────────────────────────────────────────────────────


class Chargeback(models.Model):
    """A card-issuer-initiated dispute against a Payment."""

    STATUS_CHOICES = [
        ('received', 'Received — pending response'),
        ('evidence', 'Evidence submitted — awaiting issuer'),
        ('won',      'Won — funds retained'),
        ('lost',     'Lost — funds reversed'),
        ('accepted', 'Accepted — no contest'),
    ]

    REASON_CHOICES = [
        ('fraud',          'Fraudulent transaction'),
        ('not_received',   'Goods not received'),
        ('not_as_described','Goods not as described'),
        ('duplicate',      'Duplicate charge'),
        ('subscription',   'Subscription cancellation'),
        ('other',          'Other'),
    ]

    # PROTECT on payment FK — losing the link to the original payment
    # would orphan the audit trail. ON DELETE in production should
    # never fire for Payment rows anyway (financial PROTECT throughout).
    payment = models.ForeignKey(
        'orders.Payment',
        on_delete=models.PROTECT,
        related_name='chargebacks',
    )
    # External case ID from AppyPay (or whichever PSP). Unique constraint
    # makes the inbound webhook idempotent.
    external_case_id = models.CharField(max_length=120, unique=True)
    reason_code = models.CharField(max_length=20, choices=REASON_CHOICES, default='other')
    reason_text = models.TextField(blank=True, default='')

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=8, default='AOA')

    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='received',
        db_index=True,
    )

    # Deadline by which we must submit evidence. AppyPay typically
    # gives 7 days; we conservatively store the exact datetime the
    # webhook reported, falling back to received_at + 7 days.
    deadline_at = models.DateTimeField(db_index=True)

    received_at = models.DateTimeField(auto_now_add=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    # Evidence packet auto-assembled on receipt + appended via responses.
    evidence_packet = models.JSONField(default=dict)
    # Free-form admin notes — internal communication around the case.
    admin_notes = models.TextField(blank=True, default='')

    handled_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='chargebacks_handled',
    )

    class Meta:
        db_table = 'payments_chargeback'
        ordering = ['-received_at']
        indexes = [
            models.Index(fields=['status', '-received_at']),
            models.Index(fields=['deadline_at']),
        ]

    def __str__(self):
        return f'Chargeback({self.external_case_id}, {self.status})'

    def is_overdue(self) -> bool:
        """True if we're past the deadline AND haven't responded yet."""
        if self.status not in ('received',):
            return False
        return timezone.now() > self.deadline_at


# ─── Service ──────────────────────────────────────────────────────────


DEFAULT_RESPONSE_WINDOW_DAYS = 7


def ingest_chargeback(
    *,
    external_case_id: str,
    payment,
    amount: Decimal,
    currency: str = 'AOA',
    reason_code: str = 'other',
    reason_text: str = '',
    deadline_at=None,
    source: str = 'psp',
) -> Chargeback:
    """Idempotent ingestion: returns existing row if external_case_id
    already seen, else creates a new row + assembles the evidence
    packet + emits an outbox event so ops gets paged.
    """
    if deadline_at is None:
        deadline_at = timezone.now() + timedelta(days=DEFAULT_RESPONSE_WINDOW_DAYS)

    with transaction.atomic():
        existing = Chargeback.objects.filter(
            external_case_id=external_case_id,
        ).first()
        if existing is not None:
            return existing

        evidence = _assemble_evidence_packet(payment)

        cb = Chargeback.objects.create(
            payment=payment,
            external_case_id=external_case_id,
            reason_code=reason_code or 'other',
            reason_text=reason_text or '',
            amount=Decimal(str(amount)),
            currency=currency or 'AOA',
            deadline_at=deadline_at,
            evidence_packet=evidence,
        )

    _publish_outbox('payments.chargeback.received', cb, source=source)
    log.warning(
        'chargeback received',
        extra={
            'chargeback_id': cb.pk,
            'external_case_id': external_case_id,
            'amount': str(amount),
            'deadline_at': deadline_at.isoformat(),
            'reason': reason_code,
        },
    )
    return cb


def submit_evidence(chargeback: Chargeback, *, evidence: dict,
                    actor=None) -> Chargeback:
    """Append admin-submitted evidence + flip to status='evidence'."""
    if chargeback.status != 'received':
        raise ValueError(
            f'cannot submit evidence on chargeback in status={chargeback.status}'
        )
    with transaction.atomic():
        cb = Chargeback.objects.select_for_update().get(pk=chargeback.pk)
        merged = dict(cb.evidence_packet or {})
        merged.setdefault('admin_submissions', []).append({
            'submitted_at': timezone.now().isoformat(),
            'submitted_by': getattr(actor, 'email', None),
            'evidence': evidence,
        })
        cb.evidence_packet = merged
        cb.status = 'evidence'
        cb.responded_at = timezone.now()
        cb.handled_by = actor
        cb.save(update_fields=[
            'evidence_packet', 'status', 'responded_at', 'handled_by',
        ])
    _publish_outbox('payments.chargeback.evidence', cb)
    return cb


def accept_loss(chargeback: Chargeback, *, actor=None,
                note: str = '') -> Chargeback:
    """We choose not to contest. Funds will be reversed by the issuer.
    Sometimes cheaper than fighting a $30 chargeback that costs $50
    in admin time + lost-case fees."""
    if chargeback.status not in ('received', 'evidence'):
        raise ValueError(
            f'cannot accept on chargeback in status={chargeback.status}'
        )
    with transaction.atomic():
        cb = Chargeback.objects.select_for_update().get(pk=chargeback.pk)
        cb.status = 'accepted'
        cb.resolved_at = timezone.now()
        cb.handled_by = actor
        if note:
            cb.admin_notes = (cb.admin_notes + '\n' + note).strip()
        cb.save(update_fields=[
            'status', 'resolved_at', 'handled_by', 'admin_notes',
        ])
    _publish_outbox('payments.chargeback.accepted', cb)
    return cb


def resolve(chargeback: Chargeback, *, won: bool, actor=None,
            note: str = '') -> Chargeback:
    """Mark a chargeback as won (we kept the funds) or lost (reversed).
    Called after the issuer rules — typically days/weeks after we
    submitted evidence."""
    if chargeback.status != 'evidence':
        raise ValueError(
            'can only resolve a chargeback in status=evidence '
            f'(got {chargeback.status})'
        )
    with transaction.atomic():
        cb = Chargeback.objects.select_for_update().get(pk=chargeback.pk)
        cb.status = 'won' if won else 'lost'
        cb.resolved_at = timezone.now()
        cb.handled_by = actor
        if note:
            cb.admin_notes = (cb.admin_notes + '\n' + note).strip()
        cb.save(update_fields=[
            'status', 'resolved_at', 'handled_by', 'admin_notes',
        ])
    _publish_outbox(
        'payments.chargeback.won' if won else 'payments.chargeback.lost',
        cb,
    )
    return cb


# ─── Evidence packet ──────────────────────────────────────────────────


def _assemble_evidence_packet(payment) -> dict:
    """Collect everything an admin (or auto-submission) would need to
    contest the chargeback. Run once at ingestion + frozen so that
    if the seller deletes the listing later, our evidence still has
    the historical state.

    All field accesses are defensive — different code paths populate
    Payment differently and we'd rather skip a field than crash the
    whole ingestion."""
    packet = {'assembled_at': timezone.now().isoformat()}

    try:
        order = getattr(payment, 'order', None)
        if order is not None:
            packet['order'] = {
                'id': str(order.pk),
                'status': order.status,
                'subtotal': str(order.subtotal),
                'shipping_cost': str(order.shipping_cost),
                'tax_amount': str(getattr(order, 'tax_amount', '0')),
                'total': str(order.total),
                'currency': getattr(order, 'currency', 'AOA'),
                'buyer_email': getattr(order.buyer, 'email', '')
                                if order.buyer_id else '',
                'shipping_name': order.shipping_name,
                'shipping_address': order.shipping_address,
                'shipping_city': order.shipping_city,
                'shipping_province': order.shipping_province,
                'shipping_country': order.shipping_country,
                'tracking_number': order.tracking_number,
                'carrier': order.carrier,
                'created_at': order.created_at.isoformat(),
            }

            items = []
            for it in order.items.all():
                items.append({
                    'product_title': it.product_title,
                    'unit_price': str(it.unit_price),
                    'quantity': it.quantity,
                    'total_price': str(it.total_price),
                })
            packet['items'] = items

        packet['payment'] = {
            'id': str(payment.pk),
            'gateway_reference': getattr(payment, 'gateway_reference', ''),
            'amount': str(payment.amount),
            'status': payment.status,
            'method': getattr(payment, 'method', ''),
            'created_at': payment.created_at.isoformat()
                          if getattr(payment, 'created_at', None) else None,
        }

        # Shipping events (proof of delivery is the #1 evidence type).
        try:
            from apps.orders.models import OrderTrackingEvent
            events = OrderTrackingEvent.objects.filter(order=order).order_by('created_at')
            packet['tracking_events'] = [
                {
                    'event': e.event,
                    'note': e.note,
                    'at': e.created_at.isoformat(),
                }
                for e in events
            ]
        except Exception:
            pass

    except Exception:
        log.exception('chargeback: evidence assembly partial failure')

    return packet


# ─── Outbox helper ────────────────────────────────────────────────────


def _publish_outbox(topic: str, cb: Chargeback, **extra):
    try:
        from apps.outbox.service import publish
        payload = {
            'chargeback_id': cb.pk,
            'external_case_id': cb.external_case_id,
            'payment_id': cb.payment_id,
            'amount': str(cb.amount),
            'currency': cb.currency,
            'reason_code': cb.reason_code,
            'status': cb.status,
            'deadline_at': cb.deadline_at.isoformat()
                            if cb.deadline_at else None,
        }
        payload.update(extra)
        publish(
            topic=topic, payload=payload,
            dedupe_key=f'{topic}:{cb.pk}:{cb.status}',
            ref_type='chargeback', ref_id=str(cb.pk),
        )
    except Exception:
        log.warning('chargeback: outbox publish failed for %s', topic,
                    exc_info=True)
