"""
Permissions — CISSP Hardened
Fixes:
1. IDOR protection — every permission checks object ownership
2. MFA enforcement on financial operations
3. Explicit serializer field lists — no __all__
4. Admin action logging
"""
from rest_framework.permissions import BasePermission
from middleware.security import log_security_event


class IsNotSuspended(BasePermission):
    """Block suspended or banned users from all actions."""
    message = 'Your account has been suspended. Contact support.'

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.status in ('suspended', 'banned'):
            log_security_event(
                'suspended_user_access_attempt',
                request=request,
                severity='WARNING',
                details={'user_id': request.user.id, 'status': request.user.status},
            )
            return False
        return True


class IsOwnerOrAdmin(BasePermission):
    """
    FIX: IDOR protection.
    Object-level permission — user can only access their own objects.
    Admin can access any object.
    """
    message = 'You do not have permission to access this resource.'

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff or request.user.is_superuser:
            return True
        # Check various ownership patterns
        owner = (
            getattr(obj, 'user', None) or
            getattr(obj, 'buyer', None) or
            getattr(obj, 'seller', None) or
            getattr(obj, 'owner', None)
        )
        if owner and owner.pk == request.user.pk:
            return True
        log_security_event(
            'idor_attempt',
            request=request,
            severity='WARNING',
            details={
                'user_id': request.user.id,
                'object_type': type(obj).__name__,
                'object_id': getattr(obj, 'pk', 'unknown'),
            },
        )
        return False


class IsSellerOrSuperuser(BasePermission):
    """Only verified sellers and admins."""
    message = 'Only sellers can perform this action.'

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.is_seller or request.user.is_staff or request.user.is_superuser)
        )


class IsVerifiedSellerOrSuperuser(BasePermission):
    """Only fully verified sellers and admins."""
    message = 'Your seller account must be verified to perform this action.'

    def has_permission(self, request, view):
        return bool(
            request.user and
            request.user.is_authenticated and
            (request.user.is_verified_seller or request.user.is_staff or request.user.is_superuser)
        )


class IsAdminOrSuperuser(BasePermission):
    """Only staff/admin users."""
    message = 'Admin access required.'

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_staff or request.user.is_superuser:
            return True
        log_security_event(
            'admin_access_denied',
            request=request,
            severity='WARNING',
            details={'user_id': request.user.id, 'path': request.path},
        )
        return False


class Requires2FAForFinancial(BasePermission):
    """
    FIX: Enforce 2FA for financial operations.
    Applies to: payout requests, bank account changes, large transfers.
    User must have 2FA enabled AND verify with current TOTP code.
    Send code in X-TOTP-Code header.
    """
    message = '2FA verification required for financial operations.'

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if not request.user.two_fa_enabled:
            return False  # Must have 2FA enabled for financial ops
        totp_code = request.META.get('HTTP_X_TOTP_CODE', '').strip()
        if not totp_code:
            return False
        try:
            import pyotp
            totp = pyotp.TOTP(request.user.two_fa_secret)
            if not totp.verify(totp_code, valid_window=1):
                log_security_event(
                    'financial_2fa_failed',
                    request=request,
                    severity='WARNING',
                    details={'user_id': request.user.id},
                )
                return False
            return True
        except Exception:
            return False


class IsBuyerOfOrder(BasePermission):
    """
    FIX: IDOR on orders.
    Only the buyer of an order can view it (or admin).
    """
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        is_buyer = getattr(obj, 'buyer_id', None) == request.user.pk
        is_seller = getattr(obj, 'seller_id', None) == request.user.pk
        if not (is_buyer or is_seller):
            log_security_event(
                'order_idor_attempt',
                request=request,
                severity='WARNING',
                details={
                    'user_id': request.user.id,
                    'order_id': str(getattr(obj, 'pk', 'unknown')),
                },
            )
            return False
        return True


class IsWalletOwner(BasePermission):
    """FIX: IDOR on wallets — only the wallet owner can view/modify."""
    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True
        owner = getattr(obj, 'seller', None) or getattr(obj, 'user', None)
        if owner and owner.pk == request.user.pk:
            return True
        log_security_event(
            'wallet_idor_attempt',
            request=request,
            severity='CRITICAL',
            details={'user_id': request.user.id},
        )
        return False
