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

from apps.users.permissions import IsNotSuspended, IsSellerOrSuperuser, IsAdminOrSuperuser, Requires2FAForFinancial, IsWalletOwner
from middleware.security import log_security_event
from .models import SellerWallet, WalletTransaction, SellerBankAccount, PayoutRequest, PlatformCommission


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


class WalletTransactionListView(generics.ListAPIView):
    serializer_class = TransactionSerializer
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
                return Response({"error": "2fa_required",
                                 "detail": "Send your 2FA code in X-TOTP-Code header to add a bank account."}, status=403)
            try:
                import pyotp
                totp = pyotp.TOTP(request.user.two_fa_secret)
                if not totp.verify(totp_code, valid_window=1):
                    log_security_event("bank_account_2fa_failed", request=request, severity="WARNING")
                    return Response({"error": "invalid_2fa", "detail": "Invalid 2FA code."}, status=403)
            except Exception:
                return Response({"error": "2fa_error", "detail": "2FA verification failed."}, status=403)

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
                return Response({"error": "2fa_required",
                                 "detail": "Send your 2FA code in X-TOTP-Code header to remove a bank account."}, status=403)
            try:
                import pyotp
                totp = pyotp.TOTP(request.user.two_fa_secret)
                if not totp.verify(totp_code, valid_window=1):
                    return Response({"error": "invalid_2fa", "detail": "Invalid 2FA code."}, status=403)
            except Exception:
                return Response({"error": "2fa_error", "detail": "2FA verification failed."}, status=403)

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
                return Response({"error": "2fa_required",
                                 "detail": "Send your 2FA code in X-TOTP-Code header to request a payout."}, status=403)
            try:
                import pyotp
                totp = pyotp.TOTP(request.user.two_fa_secret)
                if not totp.verify(totp_code, valid_window=1):
                    log_security_event("payout_2fa_failed", request=request, severity="CRITICAL")
                    return Response({"error": "invalid_2fa", "detail": "Invalid 2FA code."}, status=403)
            except Exception:
                return Response({"error": "2fa_error", "detail": "2FA verification failed."}, status=403)

        amount = request.data.get("amount")
        bank_id = request.data.get("bank_account_id")

        if not amount or float(amount) <= 0:
            return Response({"error": "validation_error", "detail": "Invalid amount."}, status=400)

        wallet, _ = SellerWallet.objects.get_or_create(seller=request.user)
        if wallet.balance < float(amount):
            return Response({"error": "insufficient_funds",
                             "detail": f"Balance is {wallet.balance} AOA."}, status=400)

        try:
            bank = SellerBankAccount.objects.get(pk=bank_id, seller=request.user)
        except SellerBankAccount.DoesNotExist:
            return Response({"error": "not_found", "detail": "Bank account not found."}, status=404)

        if PayoutRequest.objects.filter(seller=request.user, status__in=["pending", "processing"]).exists():
            return Response({"error": "conflict",
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
            return Response({"error": "validation_error", "detail": "Invalid action."}, status=400)
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
    permission_classes = [permissions.AllowAny]

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
                return Response({"error": "invalid_signature"}, status=400)
            gateway = "flutterwave"
        elif "HTTP_STRIPE_SIGNATURE" in request.META:
            if not self._verify_stripe(request):
                log_security_event("webhook_signature_failed", request=request, severity="CRITICAL",
                                   details={"gateway": "stripe"})
                return Response({"error": "invalid_signature"}, status=400)
            gateway = "stripe"
        else:
            log_security_event("webhook_no_signature", request=request, severity="WARNING")
            return Response({"error": "missing_signature"}, status=400)

        event = request.data.get("event") or request.data.get("type", "")
        logger.info(f"Verified webhook [{gateway}]: {event}")
        return Response({"status": "received"})
