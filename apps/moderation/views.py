"""
apps/moderation/views.py
─────────────────────────

Admin/moderator-facing endpoints for the moderation queue (R4).

Endpoints
─────────
  GET  /moderation/flags/                  legacy list — kept for back-compat
  PATCH /moderation/flags/<id>/resolve/    legacy bulk-resolve

  GET  /moderation/queue/                  paginated queue, filtered
  POST /moderation/queue/<id>/approve/     mod says "content is fine"
  POST /moderation/queue/<id>/reject/      mod says "content is bad" → escalation
  POST /moderation/queue/<id>/escalate/    mod kicks to senior

  GET  /moderation/ip-bans/                IP ban list
  POST /moderation/ip-bans/                ban an IP
  POST /moderation/buyer-protection/       file a buyer-protection claim

Audit
─────
Every queue decision writes an AdminActionLog row with the mod's user,
the target, and a snapshot of the flag state at decision time. Required
for GDPR + dispute defense.

Escalation
──────────
A 'reject' decision counts as a confirmed infraction against the
content owner. ``apps.moderation.escalation.evaluate_user`` is called
after each reject; thresholds may auto-suspend or auto-ban the owner.
The response includes the escalation result so the moderator sees
the consequence of their action immediately.
"""
from __future__ import annotations

import logging
from typing import Iterable

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsAdminOrSuperuser, IsNotSuspended
from .escalation import evaluate_user
from .models import BuyerProtectionClaim, ContentFlag, IPBan
from .serializers import (
    ModerationDecisionSerializer,
    ModerationQueueItemSerializer,
)


log = logging.getLogger(__name__)


# ─── Legacy endpoints (kept for back-compat) ─────────────────────────

class ContentFlagListView(APIView):
    """Legacy: minimal list of unresolved flags.

    Kept because pre-R4 admin dashboards point at this URL. New
    moderator UI should use /queue/ instead.
    """
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        flags = ContentFlag.objects.filter(is_resolved=False)
        return Response([
            {
                "id": f.id,
                "target_type": f.target_type,
                "target_id": f.target_id,
                "reason": f.reason,
                "auto": f.auto_flagged,
                "at": f.created_at,
            }
            for f in flags
        ])


class ResolveContentFlagView(APIView):
    """Legacy: flip a flag to is_resolved=True. Does NOT count as an
    infraction (no status='rejected' transition, no escalation).
    Provided for back-compat with the old admin endpoint."""
    permission_classes = [IsAdminOrSuperuser]

    def patch(self, request, pk):
        flag = get_object_or_404(ContentFlag, pk=pk)
        flag.is_resolved = True
        flag.save(update_fields=['is_resolved'])
        return Response({"detail": "Flag resolved."})


# ─── R4: Unified moderator queue ─────────────────────────────────────

class QueuePagination(PageNumberPagination):
    """Modest pagination — moderators rarely scroll past page 5."""
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 200


class ModerationQueueView(APIView):
    """GET /api/v1/moderation/queue/

    Lists ContentFlag rows in pending/escalated status by default —
    the "needs attention" worklist. Filters:

      ?status=pending|approved|rejected|escalated
      ?target_type=product|review|message|listing
      ?severity=low|medium|high
      ?target_user_id=<int>
      ?include_resolved=1   shortcut for status not in (approved, rejected)

    Pagination: ``?page=N&page_size=M`` (default 25, max 200).

    Response includes a ``target_snippet`` per row — a short excerpt of
    the flagged content so the mod doesn't need to click through for
    obvious cases. Snippet lookup is best-effort (one query per
    target type, batched).
    """
    permission_classes = [IsAdminOrSuperuser]
    pagination_class = QueuePagination

    def get(self, request):
        qs = ContentFlag.objects.all().select_related(
            'target_user', 'flagger', 'resolved_by',
        )

        # Default view: pending + escalated (= things needing action).
        # Pass ?status=… or ?include_resolved=1 to widen.
        status_q = request.query_params.get('status')
        if status_q:
            qs = qs.filter(status=status_q)
        elif request.query_params.get('include_resolved'):
            pass  # show everything
        else:
            qs = qs.filter(status__in=('pending', 'escalated'))

        target_type = request.query_params.get('target_type')
        if target_type:
            qs = qs.filter(target_type=target_type)

        severity = request.query_params.get('severity')
        if severity:
            qs = qs.filter(severity=severity)

        target_user_id = request.query_params.get('target_user_id')
        if target_user_id:
            qs = qs.filter(target_user_id=target_user_id)

        qs = qs.order_by('-created_at')

        paginator = QueuePagination()
        page = paginator.paginate_queryset(qs, request, view=self)

        snippets = _batch_target_snippets(page or [])
        ser = ModerationQueueItemSerializer(
            page, many=True, context={'snippets': snippets},
        )
        return paginator.get_paginated_response(ser.data)


def _batch_target_snippets(flags: Iterable) -> dict:
    """Look up a short content excerpt per (target_type, target_id).

    Batched per target type — one query per type, not per row. Returns
    a dict keyed by (target_type, target_id). Missing targets map to
    "(deleted)" so the moderator sees the flag never disappears just
    because the underlying row was already removed.
    """
    by_type: dict = {}
    for f in flags:
        by_type.setdefault(f.target_type, set()).add(f.target_id)

    out: dict = {}

    # Product
    if 'product' in by_type:
        try:
            from apps.products.models import Product
            rows = Product.objects.filter(
                pk__in=by_type['product'],
            ).values_list('pk', 'title')
            for pk, title in rows:
                out[('product', pk)] = (title or '')[:120]
            for pk in by_type['product']:
                out.setdefault(('product', pk), '(deleted)')
        except Exception:
            log.debug('queue snippet: product lookup failed', exc_info=True)

    # Listing
    if 'listing' in by_type:
        try:
            from apps.listings.models import Listing
            rows = Listing.objects.filter(
                pk__in=by_type['listing'],
            ).values_list('pk', 'title')
            for pk, title in rows:
                out[('listing', pk)] = (title or '')[:120]
            for pk in by_type['listing']:
                out.setdefault(('listing', pk), '(deleted)')
        except Exception:
            log.debug('queue snippet: listing lookup failed', exc_info=True)

    # Review — variable field names across review models, defensive
    if 'review' in by_type:
        try:
            from apps.reviews.models import Review
            rows = Review.objects.filter(pk__in=by_type['review'])
            for r in rows:
                content = (
                    getattr(r, 'comment', None)
                    or getattr(r, 'content', None)
                    or getattr(r, 'text', None)
                    or ''
                )
                out[('review', r.pk)] = content[:120]
            for pk in by_type['review']:
                out.setdefault(('review', pk), '(deleted)')
        except Exception:
            log.debug('queue snippet: review lookup failed', exc_info=True)

    # Message — chat private; show the body but not the participants
    if 'message' in by_type:
        try:
            from apps.chat.models import Message
            rows = Message.objects.filter(
                pk__in=by_type['message'],
            ).values_list('pk', 'content')
            for pk, content in rows:
                out[('message', pk)] = (content or '')[:120]
            for pk in by_type['message']:
                out.setdefault(('message', pk), '(deleted)')
        except Exception:
            log.debug('queue snippet: message lookup failed', exc_info=True)

    return out


# ─── R4: Decision endpoints ──────────────────────────────────────────

class _DecisionBase(APIView):
    """Shared infrastructure for approve/reject/escalate.

    Concrete subclasses set ``action`` (the resulting status string) and
    ``audit_action`` (the AdminActionLog action key). The ``post`` method
    handles validation, state transition, audit, and (for reject)
    escalation evaluation.
    """
    permission_classes = [IsAdminOrSuperuser, IsNotSuspended]
    action: str = ''            # 'approved' | 'rejected' | 'escalated'
    audit_action: str = ''      # AdminActionLog action key
    runs_escalation: bool = False

    def post(self, request, pk):
        ser = ModerationDecisionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        note = ser.validated_data.get('note', '')

        flag = get_object_or_404(ContentFlag, pk=pk)

        # Idempotent / explicit error: only allow transitions from
        # pending or escalated. A flag already in approved/rejected
        # is terminal — re-deciding would silently overwrite history.
        if flag.status not in ('pending', 'escalated'):
            # NOTE: extra metadata can't ride along in 4xx bodies — the
            # error-envelope middleware (middleware/error_envelope.py)
            # normalises 4xx responses to {error, detail, request_id}
            # and drops other keys. The status string is therefore
            # embedded in ``detail`` itself.
            return Response(
                {
                    'error': 'flag_terminal_state',
                    'detail': (
                        f'Flag is already in terminal state: {flag.status}'
                    ),
                },
                status=409,
            )

        previous_status = flag.status
        flag.status = self.action
        flag.is_resolved = True  # back-compat with legacy queries
        flag.resolved_by = request.user
        flag.resolved_at = timezone.now()
        flag.resolution_note = note[:2000]
        flag.save(update_fields=[
            'status', 'is_resolved', 'resolved_by',
            'resolved_at', 'resolution_note',
        ])

        # Audit trail — every decision is logged for compliance.
        _audit_decision(
            request=request,
            flag=flag,
            audit_action=self.audit_action,
            previous_status=previous_status,
            note=note,
        )

        payload = {
            'flag_id': flag.pk,
            'status': flag.status,
            'previous_status': previous_status,
            'resolved_by': request.user.email,
            'resolved_at': flag.resolved_at.isoformat(),
        }

        # Reject path: count this as an infraction against target_user
        # and evaluate escalation thresholds. Mod sees the consequence
        # in the response.
        if self.runs_escalation and flag.target_user_id:
            result = evaluate_user(flag.target_user, request=request)
            payload['escalation'] = {
                'infractions': result.infractions,
                'action': result.action,
                'previous_status': result.previous_status,
                'new_status': result.new_status,
            }

        return Response(payload, status=200)


def _audit_decision(*, request, flag, audit_action: str,
                    previous_status: str, note: str) -> None:
    """Write the AdminActionLog row for a queue decision. Defensive —
    audit failure does not abort the decision (the flag transition has
    already committed)."""
    try:
        from apps.admin_actions.models import AdminActionLog
        AdminActionLog.log(
            request=request,
            action=audit_action,
            target=flag,
            note=note[:2000],
            metadata={
                'flag_id': flag.pk,
                'target_type': flag.target_type,
                'target_id': flag.target_id,
                'target_user_id': flag.target_user_id,
                'previous_status': previous_status,
                'new_status': flag.status,
                'severity': flag.severity,
                'auto_flagged': flag.auto_flagged,
            },
        )
    except Exception:
        log.warning(
            'moderation: failed to write AdminActionLog for decision',
            exc_info=True,
        )


class ModerationApproveView(_DecisionBase):
    """POST /api/v1/moderation/queue/<pk>/approve/

    "Content is fine, dismiss the flag." Does NOT count as an
    infraction against the owner.
    """
    action = 'approved'
    audit_action = 'moderate_approve'
    runs_escalation = False


class ModerationRejectView(_DecisionBase):
    """POST /api/v1/moderation/queue/<pk>/reject/

    "Content is bad, remove it." Counts as a confirmed infraction
    against the content owner; triggers escalation evaluation.
    """
    action = 'rejected'
    audit_action = 'moderate_reject'
    runs_escalation = True


class ModerationEscalateView(_DecisionBase):
    """POST /api/v1/moderation/queue/<pk>/escalate/

    "Out of my paygrade — needs senior review." Does NOT count as an
    infraction yet (decision deferred). The flag stays visible to
    other mods (escalated rows still in default queue).
    """
    action = 'escalated'
    audit_action = 'moderate_escalate'
    runs_escalation = False


# ─── Existing endpoints (unchanged behavior) ─────────────────────────

class IPBanView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        bans = IPBan.objects.all().order_by("-created_at")[:100]
        return Response([
            {"ip": b.ip_address, "reason": b.reason, "at": b.created_at}
            for b in bans
        ])

    def post(self, request):
        ip = request.data.get("ip_address")
        if not ip:
            return Response({'error': 'IP required.'}, status=400)
        IPBan.objects.get_or_create(
            ip_address=ip,
            defaults={
                "reason": request.data.get("reason", ""),
                "banned_by": request.user,
            },
        )
        return Response({"detail": f"IP {ip} banned."})


class BuyerProtectionView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request):
        from apps.orders.models import Order
        order = get_object_or_404(
            Order, pk=request.data.get("order_id"), buyer=request.user,
        )
        if hasattr(order, "buyer_protection"):
            return Response({'error': 'Claim already submitted.'}, status=400)
        age_days = (timezone.now() - order.created_at).days
        auto = age_days > 30 and order.status not in ("delivered", "cancelled")
        BuyerProtectionClaim.objects.create(
            order=order, buyer=request.user,
            reason=request.data.get("reason", ""),
            auto_approved=auto,
            status="approved" if auto else "pending",
            resolved_at=timezone.now() if auto else None,
        )
        return Response(
            {"detail": "Claim submitted.", "auto_approved": auto},
            status=201,
        )
