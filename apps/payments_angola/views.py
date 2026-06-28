"""Angola payments — REST endpoints under /api/v1/payments-ao/.

Webhook endpoint is AllowAny (HMAC-verified). Buyer endpoints require auth.
Admin/finance endpoints require is_staff.
"""
import hashlib
import hmac

from django.conf import settings
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import (
    BankTransferProof, CodCashRemittance, MulticaixaReference, PaymentFlow,
    PaymentsAngolaKpiSnapshot,
)


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.is_staff)


# ── CH3 COD eligibility check ─────────────────────────────────────────

class CodEligibilityView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        ok, reason = services.is_cod_eligible(
            request.user,
            total_cents=int(request.data.get('total_cents', 0)),
            province=request.data.get('province', ''),
            category_ids=request.data.get('category_ids', []),
            is_remote=bool(request.data.get('is_remote')),
            seller_cod_enabled=bool(
                request.data.get('seller_cod_enabled', True)))
        return Response({'eligible': ok, 'reason': reason})


# ── CH5 create reference / CH6 push / CH7 bank — flow creation ─────────

class CreateFlowView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        method = request.data.get('method')
        order_id = request.data.get('order_id')
        amount = int(request.data.get('amount_cents', 0))
        key = request.data.get('idempotency_key') or \
            request.headers.get('Idempotency-Key', '')
        if not key:
            return Response({'error': 'Idempotency-Key required'},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            if method == 'mcx_reference':
                flow = services.create_mcx_reference(
                    request.user, order_id=order_id, amount_cents=amount,
                    idempotency_key=key)
                ref = MulticaixaReference.objects.filter(
                    flow=flow, is_active=True).first()
                return Response({
                    'flow_id': str(flow.id), 'status': flow.status,
                    'reference': ref.reference if ref else None,
                    'entity': ref.entity if ref else None,
                    'expires_at': flow.expires_at,
                    'amount_display': services.format_aoa(flow.amount_cents)},
                    status=status.HTTP_201_CREATED)
            elif method == 'mcx_push':
                flow = services.initiate_mcx_push(
                    request.user, order_id=order_id, amount_cents=amount,
                    phone_number=request.data.get('phone_number', ''),
                    idempotency_key=key)
            elif method == 'bank_transfer':
                flow = services.create_bank_transfer_flow(
                    request.user, order_id=order_id, amount_cents=amount,
                    idempotency_key=key,
                    bank=request.data.get('bank', 'BAI'))
            elif method == 'cod':
                flow = services.create_cod_flow(
                    request.user, order_id=order_id, total_cents=amount,
                    idempotency_key=key,
                    add_cod_fee=bool(request.data.get('add_cod_fee')))
            else:
                return Response({'error': 'unsupported method'},
                                status=status.HTTP_400_BAD_REQUEST)
        except ValueError as exc:
            return Response({'error': str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({'flow_id': str(flow.id), 'status': flow.status,
                         'amount_display': services.format_aoa(
                             flow.amount_cents)},
                        status=status.HTTP_201_CREATED)


class FlowStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, flow_id):
        flow = PaymentFlow.objects.filter(id=flow_id,
                                          buyer=request.user).first()
        if not flow:
            return Response({'error': 'not found'},
                            status=status.HTTP_404_NOT_FOUND)
        return Response({'flow_id': str(flow.id), 'status': flow.status,
                         'method': flow.method,
                         'amount_display': services.format_aoa(
                             flow.amount_cents),
                         'paid_at': flow.paid_at})


# ── CH7 bank proof upload ─────────────────────────────────────────────

class BankProofUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, flow_id):
        flow = PaymentFlow.objects.filter(
            id=flow_id, buyer=request.user, method='bank_transfer').first()
        if not flow:
            return Response({'error': 'not found'},
                            status=status.HTTP_404_NOT_FOUND)
        proof = services.upload_bank_proof(
            flow,
            declared_amount_cents=int(request.data.get('declared_amount_cents',
                                                       0)),
            file_key=request.data.get('file_key', ''),
            bank=request.data.get('bank', 'BAI'),
            reference_code=request.data.get('reference_code', ''))
        return Response({'proof_id': proof.id, 'status': proof.status},
                        status=status.HTTP_201_CREATED)


# ── CH10 P2P transfer ─────────────────────────────────────────────────

class P2PTransferView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from django.contrib.auth import get_user_model
        recipient = get_user_model().objects.filter(
            id=request.data.get('recipient_id')).first()
        if not recipient:
            return Response({'error': 'recipient not found'},
                            status=status.HTTP_404_NOT_FOUND)
        result = services.p2p_transfer(
            request.user, recipient,
            amount_cents=int(request.data.get('amount_cents', 0)),
            note=request.data.get('note', ''))
        code = status.HTTP_201_CREATED if result.get('ok') \
            else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)


class WalletBalanceView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cents = services.wallet_balance_cents(request.user)
        return Response({'balance_cents': cents,
                         'balance_display': services.format_aoa(cents)})


# ── CH5/CH6 APPYPAY webhook ───────────────────────────────────────────

class AppypayWebhookView(APIView):
    """HMAC-verified webhook (doc CH17). Raw body signature, constant-time
    compare, idempotent processing, amount integrity.
    """
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        # 1. HMAC verify (raw body, constant-time) — API doc Part 2 CH33.
        secret = getattr(settings, 'APPYPAY_WEBHOOK_SECRET', '') or 'dev-secret'
        raw = request.body
        provided = request.headers.get('X-APPYPAY-Signature', '')
        expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(provided, expected):
            services.log_event(None, 'webhook.rejected_signature', {})
            return Response({'error': 'webhook_signature_invalid',
                             'detail': 'Assinatura de webhook inválida.'},
                            status=status.HTTP_401_UNAUTHORIZED)
        data = request.data
        merchant_order_id = data.get('merchant_order_id')
        amount_cents = int(round(float(data.get('amount', 0)) * 100))
        psp_status = (data.get('status') or '').upper()

        # 2. Replay protection (CH33): a captured + replayed signed webhook
        # must be a fast no-op. Claim the event under a unique key; a
        # duplicate means we've already durably processed it.
        receipt = self._claim_event(data, merchant_order_id, psp_status)
        if receipt is None:
            services.log_event(None, 'webhook.replay_ignored',
                               {'merchant_order_id': str(merchant_order_id or '')})
            return Response({'received': True, 'replay': True})

        # 3. Idempotent processing (the service layer is also idempotent at
        # the payment level — defence in depth). On failure, RELEASE the
        # claim so a genuine PSP retry can re-process (doc Part 1 CH5.1).
        try:
            if psp_status == 'PAID':
                result = services.confirm_reference_payment(
                    merchant_order_id=merchant_order_id,
                    amount_cents=amount_cents,
                    psp_reference=data.get('psp_reference', ''))
            else:
                result = services.handle_push_result(
                    merchant_order_id=merchant_order_id,
                    success=False, reason=psp_status)
        except Exception:
            receipt.delete()  # not durably processed → allow retry
            raise
        # 200 means "durably recorded" (doc CH33 response discipline).
        return Response({'received': True, 'result': result})

    @staticmethod
    def _event_key(data, merchant_order_id, psp_status):
        import hashlib as _hl
        event_id = (data.get('event_id') or data.get('id')
                    or data.get('psp_reference') or '')
        if event_id:
            return f'appypay:{event_id}'
        basis = f'{merchant_order_id}|{data.get("psp_reference","")}|{psp_status}'
        return 'appypay:' + _hl.sha256(basis.encode()).hexdigest()

    @classmethod
    def _claim_event(cls, data, merchant_order_id, psp_status):
        """Insert the dedupe receipt; return it, or None if already seen.

        Savepoint pattern so a duplicate IntegrityError rolls back only this
        insert, never a surrounding transaction.
        """
        from django.db import IntegrityError, transaction

        from .models import ProcessedWebhookEvent

        event_key = cls._event_key(data, merchant_order_id, psp_status)
        try:
            with transaction.atomic():
                return ProcessedWebhookEvent.objects.create(
                    provider='appypay', event_key=event_key,
                    merchant_order_id=str(merchant_order_id or ''),
                    psp_status=psp_status)
        except IntegrityError:
            return None


# ── Admin / finance ───────────────────────────────────────────────────

class BankProofReviewView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'proofs': [
            {'id': p.id, 'flow': str(p.flow_id), 'bank': p.bank,
             'declared_cents': p.declared_amount_cents, 'status': p.status,
             'created_at': p.created_at}
            for p in BankTransferProof.objects.filter(
                status__in=('pending', 'clarification'))[:100]]})

    def post(self, request, proof_id):
        proof = BankTransferProof.objects.filter(id=proof_id).first()
        if not proof:
            return Response({'error': 'not found'},
                            status=status.HTTP_404_NOT_FOUND)
        result = services.verify_bank_proof(
            proof, decision=request.data.get('decision', 'verify'),
            reviewer=request.user, note=request.data.get('note', ''),
            statement_matched=bool(request.data.get('statement_matched')))
        code = status.HTTP_200_OK if result.get('ok') \
            else status.HTTP_400_BAD_REQUEST
        return Response(result, status=code)


class CourierRemittanceView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'remittances': [
            {'id': r.id, 'courier': r.courier_id, 'status': r.status,
             'expected_cents': r.expected_cents,
             'deposited_cents': r.deposited_cents,
             'discrepancy_cents': r.discrepancy_cents}
            for r in CodCashRemittance.objects.exclude(
                status='reconciled')[:100]]})


class KpiView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'snapshots': [
            {'date': s.snapshot_date,
             'payment_success_pct': str(s.payment_success_pct),
             'cod_acceptance_pct': str(s.cod_acceptance_pct),
             'cod_refusal_pct': str(s.cod_refusal_pct),
             'cash_in_transit_display': services.format_aoa(
                 s.cash_in_transit_cents),
             'reference_conversion_pct': str(s.reference_conversion_pct),
             'settlement_match_pct': str(s.settlement_match_pct),
             'open_recon_exceptions': s.open_recon_exceptions,
             'wallet_integrity_ok': s.wallet_integrity_ok,
             'method_mix': s.method_mix}
            for s in PaymentsAngolaKpiSnapshot.objects.order_by(
                '-snapshot_date')[:30]]})

    def post(self, request):
        snap = services.snapshot_payments_kpis()
        return Response({'date': snap.snapshot_date},
                        status=status.HTTP_201_CREATED)
