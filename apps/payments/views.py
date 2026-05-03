from rest_framework.permissions import AllowAny
from rest_framework.pagination import PageNumberPagination
"""
Payments Views — 2FA enforcement on financial operations
FIX: Requires2FAForFinancial applied to payout, bank account add/delete
"""
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import generics, permissions, serializers
from rest_framework.throttling import UserRateThrottle

from apps.users.permissions import IsNotSuspended, IsSellerOrSuperuser, IsAdminOrSuperuser
from middleware.security import log_security_event
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
    FIX: Requires 2FA when enabled
    """
    throttle_classes = [PaymentThrottle]
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]

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

        amount = request.data.get("amount")
        bank_id = request.data.get("bank_account_id")

        if not amount or float(amount) <= 0:
            return Response({'error': 'validation_error', "detail": "Invalid amount."}, status=400)

        wallet, _ = SellerWallet.objects.get_or_create(seller=request.user)
        # Re-read with lock to prevent TOCTOU
        wallet = SellerWallet.objects.select_for_update(of=('self',)).get(pk=wallet.pk)
        if wallet.balance < float(amount):
            return Response({'error': 'insufficient_funds',
                             "detail": f"Balance is {wallet.balance} AOA."}, status=400)

        try:
            bank = SellerBankAccount.objects.get(pk=bank_id, seller=request.user)
        except SellerBankAccount.DoesNotExist:
            return Response({'error': 'not_found', "detail": "Bank account not found."}, status=404)

        if PayoutRequest.objects.filter(seller=request.user, status__in=["pending", "processing"]).exists():
            return Response({'error': 'conflict',
                             "detail": "You already have a pending payout request."}, status=409)

        with transaction.atomic():
            payout = PayoutRequest.objects.create(seller=request.user, bank_account=bank, amount=amount)
            wallet.debit(float(amount), f"Payout request {payout.id}", reference=str(payout.id))

        log_security_event("payout_requested", request=request,
                           details={"amount": str(amount), "user_id": request.user.id})
        return Response(PayoutSerializer(payout).data, status=201)


class AdminPayoutListView(generics.ListAPIView):
    serializer_class = PayoutSerializer
    permission_classes = [IsAdminOrSuperuser]
    queryset = PayoutRequest.objects.select_related("seller", "bank_account").order_by("-created_at")


class AdminPayoutActionView(APIView):
    permission_classes = [IsAdminOrSuperuser]

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
                wallet.credit(float(payout.amount), "Payout rejected — refunded", reference=str(payout.id))
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

    Security:
    - HMAC-SHA256 signature verification (rejects anything unsigned)
    - Idempotent processing (duplicate events are safe)
    - Append-only event log for full audit trail

    APPYPAY sends webhooks for:
    - payment.confirmed  — user approved payment on phone
    - payment.failed     — user rejected or timed out
    - payment.refunded   — refund processed
    - payment.reversed   — chargeback/dispute
    """
    permission_classes = [AllowAny]  # verified by HMAC

    def post(self, request):
        from apps.payments.gateway import AppyPayGateway, PaymentProcessor

        # 1. Verify signature FIRST — reject anything unverified
        gateway = AppyPayGateway()
        signature = request.META.get('HTTP_X_APPYPAY_SIGNATURE', '')

        if not signature:
            logger.warning('AppyPay webhook missing signature', extra={
                'ip': request.META.get('REMOTE_ADDR'),
            })
            return Response({'error': 'missing_signature'}, status=400)

        if not gateway.verify_webhook_signature(request.body, signature):
            logger.error('AppyPay webhook invalid signature — REJECTED', extra={
                'ip': request.META.get('REMOTE_ADDR'),
                'signature': signature[:20],
            })
            log_security_event('webhook_signature_failed', request=request,
                               severity='CRITICAL', details={'gateway': 'appypay'})
            return Response({'error': 'invalid_signature'}, status=400)

        # 2. Parse event
        try:
            data = request.data
            event_type = data.get('event', '')
            reference = data.get('reference', '')
            amount = data.get('amount')
        except Exception as e:
            return Response({'error': 'invalid_payload'}, status=400)

        logger.info('AppyPay webhook received', extra={
            'event': event_type,
            'reference': reference,
        })

        # 3. Process event
        processor = PaymentProcessor()

        try:
            if event_type == 'payment.confirmed':
                processor.confirm_payment(reference, data)

            elif event_type == 'payment.failed':
                reason = data.get('failure_reason', 'unknown')
                processor.fail_payment(reference, reason)

            elif event_type in ('payment.refunded', 'payment.reversed'):
                # Gateway-initiated refund (chargeback)
                try:
                    from apps.orders.models import Payment
                    payment = Payment.objects.get(gateway_reference=reference)
                    from apps.payments.gateway import PaymentEventLogger
                    PaymentEventLogger.log(
                        payment, event_type,
                        {'amount': amount, 'reason': data.get('reason')}
                    )
                except Exception as e:
                    logger.error(f'Could not log refund event: {e}')

            else:
                logger.info(f'Unhandled AppyPay event: {event_type}')

        except Exception as e:
            logger.error('AppyPay webhook processing error', extra={
                'event': event_type,
                'reference': reference,
                'error': str(e),
            })
            # Return 200 to prevent gateway from retrying permanently
            # The error is logged and will be caught by reconciliation
            return Response({'status': 'error_logged'}, status=200)

        # Always return 200 to acknowledge receipt
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
