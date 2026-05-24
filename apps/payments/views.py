"""
Payments Views — 2FA enforcement on financial operations
FIX: Requires2FAForFinancial applied to payout, bank account add/delete
"""
import logging

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import generics, permissions, serializers
from rest_framework.throttling import UserRateThrottle
from rest_framework.permissions import AllowAny
from rest_framework.pagination import PageNumberPagination

# Module logger used by the AppyPay webhook handler + payment-flow
# diagnostic logs. Previously missing — every call to ``logger.info()``
# / ``logger.error()`` in this file would NameError when the webhook
# fired. Surfaced by flake8 F821.
logger = logging.getLogger('micha.payments')

from apps.users.permissions import (
    IsNotSuspended, IsSellerOrSuperuser, IsAdminOrSuperuser,
    Requires2FAForFinancial,
)
from middleware.security import log_security_event
from apps.inbound_webhooks.decorators import verified_webhook
from apps.idempotency.decorators import idempotent
from .models import SellerWallet, WalletTransaction, SellerBankAccount, PayoutRequest


class PaymentThrottle(UserRateThrottle):
    scope = "payment"


class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerWallet
        fields = ["balance", "pending_balance", "total_earned", "total_withdrawn", "updated_at"]


class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = ["id", "type", "amount", "description", "reference", "balance_after", "created_at"]


class BankAccountSerializer(serializers.ModelSerializer):
    account_number_display = serializers.SerializerMethodField()

    class Meta:
        model = SellerBankAccount
        fields = ["id", "bank_name", "account_name", "account_number", "account_number_display",
                  "iban", "is_default", "is_verified", "created_at"]
        # ``is_verified`` MUST be read-only on the serializer — otherwise a
        # seller POSTing {is_verified: true, ...} self-verifies their bank
        # account, bypassing whatever manual verification the platform
        # requires before paying real money to that IBAN.
        # ``created_at`` is also read-only (timestamp managed by DB).
        read_only_fields = ["id", "is_verified", "created_at"]
        extra_kwargs = {
            "account_number": {"write_only": True},
            "iban": {"write_only": True},
        }

    def get_account_number_display(self, obj):
        return obj.masked_number()


class PayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayoutRequest
        fields = ["id", "bank_account", "amount", "status", "admin_note", "processed_at", "created_at"]
        read_only_fields = ["id", "status", "admin_note", "processed_at", "created_at"]


class WalletView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def get(self, request):
        wallet, _ = SellerWallet.objects.get_or_create(seller=request.user)
        return Response(WalletSerializer(wallet).data)



class WalletTransactionPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class WalletTransactionListView(generics.ListAPIView):
    serializer_class = TransactionSerializer
    pagination_class = WalletTransactionPagination
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def get_queryset(self):
        wallet, _ = SellerWallet.objects.get_or_create(seller=self.request.user)
        return WalletTransaction.objects.filter(wallet=wallet)


class BankAccountListCreateView(APIView):
    """
    GET  — list bank accounts
    POST — add bank account (FIX: requires 2FA)
    """
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def get(self, request):
        accounts = SellerBankAccount.objects.filter(seller=request.user)
        return Response(BankAccountSerializer(accounts, many=True).data)

    def post(self, request):
        # FIX: Adding a bank account requires 2FA verification
        if request.user.two_fa_enabled:
            totp_code = request.META.get("HTTP_X_TOTP_CODE", "").strip()
            if not totp_code:
                return Response({'error': '2fa_required',
                                 "detail": "Send your 2FA code in X-TOTP-Code header to add a bank account."}, status=403)
            try:
                import pyotp
                totp = pyotp.TOTP(request.user.two_fa_secret)
                if not totp.verify(totp_code, valid_window=1):
                    log_security_event("bank_account_2fa_failed", request=request, severity="WARNING")
                    return Response({'error': 'invalid_2fa', "detail": "Invalid 2FA code."}, status=403)
            except Exception:
                return Response({'error': '2fa_error', "detail": "2FA verification failed."}, status=403)

        serializer = BankAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = serializer.save(seller=request.user)
        log_security_event("bank_account_added", request=request,
                           details={"bank": account.bank_name, "user_id": request.user.id})
        return Response(BankAccountSerializer(account).data, status=201)


class BankAccountDetailView(APIView):
    """DELETE — remove bank account (FIX: requires 2FA)"""
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    def delete(self, request, pk):
        account = get_object_or_404(SellerBankAccount, pk=pk, seller=request.user)

        # FIX: Deleting a bank account requires 2FA
        if request.user.two_fa_enabled:
            totp_code = request.META.get("HTTP_X_TOTP_CODE", "").strip()
            if not totp_code:
                return Response({'error': '2fa_required',
                                 "detail": "Send your 2FA code in X-TOTP-Code header to remove a bank account."}, status=403)
            try:
                import pyotp
                totp = pyotp.TOTP(request.user.two_fa_secret)
                if not totp.verify(totp_code, valid_window=1):
                    return Response({'error': 'invalid_2fa', "detail": "Invalid 2FA code."}, status=403)
            except Exception:
                return Response({'error': '2fa_error', "detail": "2FA verification failed."}, status=403)

        log_security_event("bank_account_removed", request=request,
                           details={"bank": account.bank_name, "user_id": request.user.id})
        account.delete()
        return Response({"detail": "Bank account removed."})


class RequestPayoutView(APIView):
    """
    POST /api/payments/payout/request/
    FIX: Requires 2FA when enabled.
    Idempotency-Key header is REQUIRED — payouts are real money out of
    the platform; a duplicate request from a flaky network must NEVER
    issue two payouts.
    """
    throttle_classes = [PaymentThrottle]
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

    @idempotent(required=True)
    def post(self, request):
        # FIX: Payout requires 2FA
        if request.user.two_fa_enabled:
            totp_code = request.META.get("HTTP_X_TOTP_CODE", "").strip()
            if not totp_code:
                return Response({'error': '2fa_required',
                                 "detail": "Send your 2FA code in X-TOTP-Code header to request a payout."}, status=403)
            try:
                import pyotp
                totp = pyotp.TOTP(request.user.two_fa_secret)
                if not totp.verify(totp_code, valid_window=1):
                    log_security_event("payout_2fa_failed", request=request, severity="CRITICAL")
                    return Response({'error': 'invalid_2fa', "detail": "Invalid 2FA code."}, status=403)
            except Exception:
                return Response({'error': '2fa_error', "detail": "2FA verification failed."}, status=403)

        from apps.core.money import to_decimal

        raw_amount = request.data.get("amount")
        bank_id = request.data.get("bank_account_id")

        # Money MUST be Decimal end-to-end. The previous flow cast
        # to float() three times — would crash production payouts on
        # ``Decimal - float`` (TypeError) inside wallet.debit().
        try:
            amount = to_decimal(raw_amount)
        except (ValueError, TypeError):
            return Response({'error': 'validation_error',
                             "detail": "Invalid amount."}, status=400)
        if amount <= 0:
            return Response({'error': 'validation_error',
                             "detail": "Invalid amount."}, status=400)

        # R2: KYC tier gating. Below Tier 3, sellers have monthly
        # payout caps. Refuses the request BEFORE wallet/bank lookups
        # so fraudsters can't enumerate wallet state.
        from apps.payments.kyc_gating import check_payout_allowed
        allowed, err_code, details = check_payout_allowed(request.user, amount)
        if not allowed:
            log_security_event(
                'payout_kyc_blocked', request=request, severity='WARNING',
                details={'user_id': request.user.id,
                         'error': err_code, **details},
            )
            return Response(
                {'error': err_code,
                 'detail': details.get('message', 'Payout not allowed.'),
                 'tier': details.get('tier'),
                 'cap': details.get('cap'),
                 'used': details.get('used'),
                 'remaining': details.get('remaining')},
                status=403,
            )

        wallet, _ = SellerWallet.objects.get_or_create(seller=request.user)
        # Re-read with lock to prevent TOCTOU
        wallet = SellerWallet.objects.select_for_update(of=('self',)).get(pk=wallet.pk)
        if wallet.balance < amount:
            return Response({'error': 'insufficient_funds',
                             "detail": f"Balance is {wallet.balance} AOA."}, status=400)

        try:
            bank = SellerBankAccount.objects.get(pk=bank_id, seller=request.user)
        except SellerBankAccount.DoesNotExist:
            return Response({'error': 'not_found',
                             "detail": "Bank account not found."}, status=404)

        if PayoutRequest.objects.filter(seller=request.user,
                                         status__in=["pending", "processing"]).exists():
            return Response({'error': 'conflict',
                             "detail": "You already have a pending payout request."},
                            status=409)

        with transaction.atomic():
            payout = PayoutRequest.objects.create(
                seller=request.user, bank_account=bank, amount=amount,
            )
            wallet.debit(amount, f"Payout request {payout.id}",
                         reference=str(payout.id))
            try:
                from apps.ledger.service import record_payout_debit
                record_payout_debit(
                    seller=request.user, amount=amount, payout_id=payout.id,
                )
            except Exception:
                pass

        log_security_event("payout_requested", request=request,
                           details={"amount": str(amount), "user_id": request.user.id})
        return Response(PayoutSerializer(payout).data, status=201)


class AdminPayoutListView(generics.ListAPIView):
    serializer_class = PayoutSerializer
    permission_classes = [IsAdminOrSuperuser]
    queryset = PayoutRequest.objects.select_related("seller", "bank_account").order_by("-created_at")


class AdminPayoutActionView(APIView):
    """PATCH /api/v1/admin/payouts/<id>/ — approve / reject / process / complete.

    SECURITY: requires admin + 2FA on every call.

    Why both: IsAdminOrSuperuser proves the caller has the admin role.
    Requires2FAForFinancial demands a fresh TOTP code in the
    X-TOTP-Code header on every payout action. Without the 2FA gate,
    a stolen admin session (phished cookie, hijacked CSRF, abandoned
    workstation) is enough to drain seller payouts. With it, the
    attacker also needs the admin's authenticator app — defeating
    the realistic threat model.

    The 2FA code is verified with valid_window=1 (≈90s clock skew).
    Each failed verification logs a 'financial_2fa_failed' security
    event at WARNING severity — feeds into fraud signal correlation.

    Idempotency: each PATCH is treated as a fresh action. Multiple
    admins clicking 'approve' on the same payout in quick succession
    is handled by the row-level select_for_update inside
    SellerWallet.credit / debit; the 2FA challenge is per-request so
    a session cannot be reused across multiple payouts even within a
    short window.
    """
    permission_classes = [IsAdminOrSuperuser, Requires2FAForFinancial]

    def patch(self, request, pk):
        payout = get_object_or_404(PayoutRequest, pk=pk)
        action = request.data.get("action")
        if action not in ("approved", "processing", "completed", "rejected"):
            return Response({'error': 'validation_error', "detail": "Invalid action."}, status=400)
        with transaction.atomic():
            payout.status = action
            payout.admin_note = request.data.get("note", "")
            if action == "completed":
                payout.processed_at = timezone.now()
            elif action == "rejected":
                wallet, _ = SellerWallet.objects.get_or_create(seller=payout.seller)
                # payout.amount is already Decimal — pass it through.
                # The prior float() cast was a latent bug: Decimal +/- float
                # raises TypeError inside wallet.credit().
                wallet.credit(
                    payout.amount, "Payout rejected — refunded",
                    reference=str(payout.id),
                )
                try:
                    from apps.ledger.service import record_payout_reverse
                    record_payout_reverse(seller=payout.seller, amount=payout.amount, payout_id=payout.id)
                except Exception:
                    pass
            payout.save()
        from apps.admin_actions.models import AdminActionLog
        AdminActionLog.log(request, f"{action}_payout", payout.seller,
                           metadata={"payout_id": str(payout.id), "amount": str(payout.amount)})
        return Response({"detail": f"Payout {action}."})


class WebhookView(APIView):
    """Payment gateway webhook — HMAC verified."""
    permission_classes = [AllowAny]

    def _verify_flutterwave(self, request):
        import hmac as _hmac
        from django.conf import settings
        secret = getattr(settings, "FLUTTERWAVE_SECRET_HASH", "")
        if not secret:
            return False
        received = request.META.get("HTTP_VERIF_HASH", "")
        return _hmac.compare_digest(received, secret)

    def _verify_stripe(self, request):
        import hmac as _hmac, hashlib, time
        from django.conf import settings
        secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "")
        if not secret:
            return False
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
        payload = request.body.decode("utf-8")
        try:
            parts = {p.split("=")[0]: p.split("=")[1] for p in sig_header.split(",")}
            timestamp = parts.get("t", "0")
            sig = parts.get("v1", "")
            expected = _hmac.new(secret.encode(), f"{timestamp}.{payload}".encode(), hashlib.sha256).hexdigest()
            if abs(time.time() - int(timestamp)) > 300:
                return False
            return _hmac.compare_digest(sig, expected)
        except Exception:
            return False

    def post(self, request):
        import logging
        logger = logging.getLogger("micha")
        if "HTTP_VERIF_HASH" in request.META:
            if not self._verify_flutterwave(request):
                log_security_event("webhook_signature_failed", request=request, severity="CRITICAL",
                                   details={"gateway": "flutterwave"})
                return Response({'error': 'invalid_signature'}, status=400)
            gateway = "flutterwave"
        elif "HTTP_STRIPE_SIGNATURE" in request.META:
            if not self._verify_stripe(request):
                log_security_event("webhook_signature_failed", request=request, severity="CRITICAL",
                                   details={"gateway": "stripe"})
                return Response({'error': 'invalid_signature'}, status=400)
            gateway = "stripe"
        else:
            log_security_event("webhook_no_signature", request=request, severity="WARNING")
            return Response({'error': 'missing_signature'}, status=400)

        event = request.data.get("event") or request.data.get("type", "")
        logger.info(f"Verified webhook [{gateway}]: {event}")
        return Response({"status": "received"})


class PayoutScheduleView(APIView):
    """GET /api/v1/payments/payouts/schedule/ — Upcoming payout schedule."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from apps.payments.models import EarningsHold
        from django.utils import timezone
        holds = EarningsHold.objects.filter(
            seller=request.user,
            released=False,
            release_at__gte=timezone.now(),
        ).order_by('release_at').select_related('order')[:20]

        data = [{
            'id': h.id,
            'amount': str(h.amount),
            'release_at': h.release_at,
            'order_id': str(h.order_id),
            'released': h.released,
        } for h in holds]

        total = sum(h.amount for h in holds)
        return Response({'upcoming_payouts': data, 'total_pending': str(total)})


class AppyPayWebhookView(APIView):
    """
    APPYPAY Multicaixa Express webhook endpoint.
    URL: POST /api/v1/payments/appypay/webhook/

    Defense-in-depth via @verified_webhook:
      • HMAC-SHA256 signature verification on every request
      • Timestamp window enforcement (rejects replays older than 5 min if
        provider supplies X-AppyPay-Timestamp)
      • Body-hash dedupe at the storage layer — re-delivery of the byte-
        identical body returns the original response without re-executing
      • Forensic audit row per attempt (verified OR rejected)
      • Critical-severity security event log on any verification failure
    """
    permission_classes = [AllowAny]  # verified by HMAC

    @verified_webhook('appypay')
    def post(self, request):
        from apps.payments.gateway import PaymentProcessor

        # The decorator parsed + verified the payload and attached it.
        ctx = request._verified_webhook
        data = ctx['payload'] or {}
        event_type = ctx['event_type']
        reference = data.get('reference', '')
        amount = data.get('amount')

        logger.info('AppyPay webhook verified', extra={
            'event': event_type, 'reference': reference,
        })

        processor = PaymentProcessor()
        try:
            if event_type == 'payment.confirmed':
                processor.confirm_payment(reference, data)
            elif event_type == 'payment.failed':
                processor.fail_payment(reference, data.get('failure_reason', 'unknown'))
            elif event_type in ('payment.refunded', 'payment.reversed'):
                try:
                    from apps.orders.models import Payment
                    payment = Payment.objects.get(gateway_reference=reference)
                    from apps.payments.gateway import PaymentEventLogger
                    PaymentEventLogger.log(payment, event_type,
                                           {'amount': amount, 'reason': data.get('reason')})
                except Exception as e:
                    logger.error(f'Could not log refund event: {e}')
            else:
                logger.info(f'Unhandled AppyPay event: {event_type}')
        except Exception as e:
            logger.error('AppyPay webhook handler error', extra={
                'event': event_type, 'reference': reference, 'error': str(e),
            })
            # Acknowledge so the gateway doesn't retry forever; reconciliation
            # will pick up any stuck payments.
            return Response({'status': 'error_logged'}, status=200)

        return Response({'status': 'ok'}, status=200)


class PaymentReconcileView(APIView):
    """
    POST /api/v1/payments/reconcile/<order_id>/
    Manually trigger reconciliation for a specific order.
    For when webhook was missed and payment is stuck in pending.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, order_id):
        from apps.orders.models import Order
        from apps.payments.gateway import PaymentProcessor

        try:
            order = Order.objects.get(id=order_id, buyer=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=404)

        processor = PaymentProcessor()
        result = processor.reconcile_order(order)

        return Response(result)


class PaymentStatusView(APIView):
    """
    GET /api/v1/payments/status/<order_id>/
    Get current payment status for an order.
    Polls gateway if our status is still pending.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, order_id):
        from apps.orders.models import Order, Payment

        try:
            order = Order.objects.get(id=order_id, buyer=request.user)
        except Order.DoesNotExist:
            return Response({'error': 'Order not found'}, status=404)

        payment = Payment.objects.filter(order=order).order_by('-created_at').first()
        if not payment:
            return Response({'status': 'no_payment'})

        # If pending for > 5 minutes, check with gateway
        if payment.status == 'pending':
            age_minutes = (timezone.now() - payment.created_at).total_seconds() / 60
            if age_minutes > 5:
                from apps.payments.gateway import PaymentProcessor
                processor = PaymentProcessor()
                processor.reconcile_order(order)
                payment.refresh_from_db()

        return Response({
            'payment_id': str(payment.id),
            'status': payment.status,
            'amount': str(payment.amount),
            'method': payment.method,
            'paid_at': payment.paid_at,
            'reference': payment.gateway_reference,
        })
