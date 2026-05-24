"""
apps/payments/chargeback_views.py
──────────────────────────────────

Admin + PSP-webhook endpoints for the chargeback workflow.

Routes (wired from apps/payments/urls.py):

  POST /api/v1/payments/chargebacks/inbound/         (no-auth, HMAC-signed)
  GET  /api/v1/payments/chargebacks/                  admin list
  GET  /api/v1/payments/chargebacks/<pk>/             admin detail
  POST /api/v1/payments/chargebacks/<pk>/respond/     submit evidence
  POST /api/v1/payments/chargebacks/<pk>/accept/      accept loss
  POST /api/v1/payments/chargebacks/<pk>/resolve/     mark won/lost
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsAdminOrSuperuser
from .chargebacks import (
    Chargeback,
    accept_loss,
    ingest_chargeback,
    resolve as resolve_cb,
    submit_evidence,
)


log = logging.getLogger('micha.chargebacks')


# ─── Serializers ─────────────────────────────────────────────────────


class ChargebackSerializer(serializers.ModelSerializer):
    payment_id = serializers.CharField(source='payment.pk', read_only=True)
    order_id = serializers.SerializerMethodField()
    handled_by_email = serializers.SerializerMethodField()
    overdue = serializers.SerializerMethodField()

    class Meta:
        model = Chargeback
        fields = [
            'id', 'external_case_id', 'payment_id', 'order_id',
            'reason_code', 'reason_text',
            'amount', 'currency', 'status',
            'deadline_at', 'received_at', 'responded_at', 'resolved_at',
            'handled_by_email', 'admin_notes', 'overdue',
        ]
        read_only_fields = fields

    def get_order_id(self, obj):
        order = getattr(obj.payment, 'order', None)
        return str(order.pk) if order else None

    def get_handled_by_email(self, obj):
        u = obj.handled_by
        return getattr(u, 'email', None) if u else None

    def get_overdue(self, obj):
        return obj.is_overdue()


class ChargebackDetailSerializer(ChargebackSerializer):
    """Detail view includes the full evidence packet."""

    class Meta(ChargebackSerializer.Meta):
        fields = ChargebackSerializer.Meta.fields + ['evidence_packet']


# ─── Inbound webhook ─────────────────────────────────────────────────


class ChargebackInboundView(APIView):
    """``POST /api/v1/payments/chargebacks/inbound/``

    Accepts both:
      • PSP webhook format (HMAC-signed via WEBHOOK_HMAC_SECRETS['chargebacks'])
      • Admin-paste format (authenticated admin POSTs manually after
        receiving an email from AppyPay).

    Idempotent on external_case_id. Repeated deliveries of the same
    case return 200 with the existing chargeback row.

    Payload shape (lenient):
      {
        "external_case_id": "PSP-12345",     required
        "payment_id":       "pay_abc",        required (matches Payment.gateway_ref OR pk)
        "amount":           "1000.00",        required
        "currency":         "AOA",            default 'AOA'
        "reason_code":      "fraud",          optional
        "reason_text":      "...",            optional
        "deadline_at":      "2026-06-01T..."  optional, ISO-8601
      }
    """
    permission_classes = []
    # authentication_classes NOT cleared — we want JWT/Session auth to
    # populate request.user so the admin-paste path can short-circuit
    # to allow. HMAC path doesn't need authentication_classes since
    # the HMAC IS the auth.

    def post(self, request):
        # Auth: either HMAC signature OR admin session/JWT (admin paste).
        if not self._authenticated(request):
            return Response(
                {'error': 'unauthorized',
                 'detail': 'HMAC signature or admin auth required.'},
                status=401,
            )

        data = request.data or {}
        case_id = (data.get('external_case_id') or '').strip()
        payment_ref = (data.get('payment_id') or '').strip()
        if not case_id or not payment_ref:
            return Response(
                {'error': 'validation_error',
                 'detail': 'external_case_id and payment_id required.'},
                status=400,
            )

        try:
            amount = Decimal(str(data.get('amount') or '0'))
        except Exception:
            return Response(
                {'error': 'validation_error',
                 'detail': 'amount must be decimal.'},
                status=400,
            )
        if amount <= 0:
            return Response(
                {'error': 'validation_error',
                 'detail': 'amount must be positive.'},
                status=400,
            )

        # Resolve Payment by gateway_ref OR pk.
        payment = self._resolve_payment(payment_ref)
        if payment is None:
            return Response(
                {'error': 'not_found',
                 'detail': f'payment not found: {payment_ref}'},
                status=404,
            )

        deadline_at = self._parse_deadline(data.get('deadline_at'))

        cb = ingest_chargeback(
            external_case_id=case_id,
            payment=payment,
            amount=amount,
            currency=data.get('currency') or 'AOA',
            reason_code=data.get('reason_code') or 'other',
            reason_text=data.get('reason_text') or '',
            deadline_at=deadline_at,
            source='webhook' if 'HTTP_X_PSP_SIGNATURE' in request.META else 'admin',
        )
        return Response(ChargebackSerializer(cb).data, status=200)

    # ── helpers ────────────────────────────────────────────────────

    def _authenticated(self, request) -> bool:
        sig = request.META.get('HTTP_X_PSP_SIGNATURE', '')
        if sig and self._verify_hmac(request.body, sig):
            return True
        # Fall back to admin auth (for manual-paste flow).
        user = getattr(request, 'user', None)
        if user and getattr(user, 'is_authenticated', False) \
                and (user.is_staff or user.is_superuser):
            return True
        return False

    def _verify_hmac(self, body: bytes, sig: str) -> bool:
        secrets = getattr(settings, 'WEBHOOK_HMAC_SECRETS', {}) or {}
        secret = (secrets.get('chargebacks') or '').encode('utf-8')
        if not secret:
            return False
        expected = hmac.new(secret, body or b'', hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, (sig or '').strip())

    def _resolve_payment(self, ref: str):
        from apps.orders.models import Payment
        if not ref:
            return None
        # Try gateway_ref first (the PSP's identifier), then pk.
        p = Payment.objects.filter(gateway_reference=ref).first()
        if p is not None:
            return p
        try:
            return Payment.objects.filter(pk=ref).first()
        except (ValueError, TypeError):
            return None

    def _parse_deadline(self, raw):
        if not raw:
            return None
        try:
            # Accept ISO-8601 with or without timezone.
            dt = datetime.fromisoformat(str(raw).replace('Z', '+00:00'))
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            return dt
        except Exception:
            return None


# ─── Admin endpoints ─────────────────────────────────────────────────


class ChargebackListPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 200


class ChargebackListView(APIView):
    """``GET /api/v1/payments/chargebacks/?status=received|...``"""
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperuser]
    pagination_class = ChargebackListPagination

    def get(self, request):
        qs = Chargeback.objects.all().select_related('payment', 'handled_by')

        status_q = request.query_params.get('status')
        if status_q:
            qs = qs.filter(status=status_q)

        if request.query_params.get('overdue') == '1':
            qs = qs.filter(status='received', deadline_at__lt=timezone.now())

        qs = qs.order_by('-received_at')

        paginator = ChargebackListPagination()
        page = paginator.paginate_queryset(qs, request, view=self)
        ser = ChargebackSerializer(page, many=True)
        return paginator.get_paginated_response(ser.data)


class ChargebackDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperuser]

    def get(self, request, pk):
        cb = get_object_or_404(Chargeback, pk=pk)
        return Response(ChargebackDetailSerializer(cb).data)


class ChargebackRespondView(APIView):
    """``POST .../respond/`` — submit evidence packet."""
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperuser]

    def post(self, request, pk):
        cb = get_object_or_404(Chargeback, pk=pk)
        evidence = request.data.get('evidence') or {}
        if not isinstance(evidence, dict):
            return Response(
                {'error': 'validation_error',
                 'detail': 'evidence must be an object.'},
                status=400,
            )
        try:
            updated = submit_evidence(cb, evidence=evidence, actor=request.user)
        except ValueError as e:
            return Response(
                {'error': 'invalid_state', 'detail': str(e)}, status=409,
            )
        try:
            from apps.admin_actions.models import AdminActionLog
            AdminActionLog.log(
                request=request, action='issue_refund', target=updated,
                note='Chargeback evidence submitted',
                metadata={'chargeback_id': cb.pk,
                          'external_case_id': cb.external_case_id},
            )
        except Exception:
            log.warning('chargeback: respond audit-log failed', exc_info=True)
        return Response(ChargebackDetailSerializer(updated).data)


class ChargebackAcceptView(APIView):
    """``POST .../accept/`` — accept the loss without contesting."""
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperuser]

    def post(self, request, pk):
        cb = get_object_or_404(Chargeback, pk=pk)
        note = (request.data.get('note') or '')[:2000]
        try:
            updated = accept_loss(cb, actor=request.user, note=note)
        except ValueError as e:
            return Response(
                {'error': 'invalid_state', 'detail': str(e)}, status=409,
            )
        return Response(ChargebackDetailSerializer(updated).data)


class ChargebackResolveView(APIView):
    """``POST .../resolve/`` — body {won: true|false}."""
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperuser]

    def post(self, request, pk):
        cb = get_object_or_404(Chargeback, pk=pk)
        won = bool(request.data.get('won'))
        note = (request.data.get('note') or '')[:2000]
        try:
            updated = resolve_cb(cb, won=won, actor=request.user, note=note)
        except ValueError as e:
            return Response(
                {'error': 'invalid_state', 'detail': str(e)}, status=409,
            )
        return Response(ChargebackDetailSerializer(updated).data)
