"""
apps/verification_gate/middleware.py

Verification gate middleware for MICHA Express.

Blocks ALL seller/store API endpoints if:
- Seller has not submitted verification
- Verification is pending/rejected
- BI is expired
- Monthly selfie is overdue

Buyers are never blocked — they browse and buy freely.

Returns HTTP 403 with structured JSON so frontend can show the right screen.
"""
from django.http import JsonResponse
from django.utils import timezone


# Routes that require seller verification
SELLER_ROUTE_PREFIXES = [
    '/api/v1/seller/',
    '/api/v1/stores/',
    '/api/v1/inventory/',
    '/api/v1/analytics/',
    '/api/seller/',
    '/api/stores/',
    '/api/inventory/',
    '/api/analytics/',
    '/api/v1/products/',   # POST/PUT/PATCH/DELETE only
    '/api/products/',       # POST/PUT/PATCH/DELETE only
]

# These methods on product routes require verification
SELLER_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}

# Routes always allowed — even for locked sellers
ALWAYS_ALLOWED = [
    '/api/v1/auth/',
    '/api/auth/',
    '/api/v1/verification-gate/',
    '/api/verification-gate/',
    '/django-admin/',
    '/health/',
]


class SellerVerificationMiddleware:
    """
    Checks seller verification status on every request.
    Only runs for authenticated users with is_seller=True.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only check authenticated sellers
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return self.get_response(request)

        if not getattr(request.user, 'is_seller', False):
            return self.get_response(request)

        # Staff/admin bypass
        if request.user.is_staff:
            return self.get_response(request)

        path = request.path

        # Always allow auth + verification routes
        if any(path.startswith(p) for p in ALWAYS_ALLOWED):
            return self.get_response(request)

        # Check if this is a seller-restricted route
        is_seller_route = any(path.startswith(p) for p in SELLER_ROUTE_PREFIXES)

        # For product routes, only block write operations
        is_product_route = '/products/' in path
        if is_product_route and request.method not in SELLER_METHODS:
            return self.get_response(request)

        if not is_seller_route:
            return self.get_response(request)

        # Check verification status
        block_response = self._check_verification(request.user)
        if block_response:
            return block_response

        return self.get_response(request)

    def _check_verification(self, user):
        """
        Returns JsonResponse if seller should be blocked, None if OK.
        """
        try:
            v = user.seller_verification
        except Exception:
            # No verification record at all
            return JsonResponse({
                'verification_required': True,
                'status': 'not_submitted',
                'message': 'Verificação de identidade obrigatória para vendedores.',
                'action': 'submit_verification',
            }, status=403)

        if not v.is_active:
            return self._build_block_response(v)

        return None

    def _build_block_response(self, v):
        """Builds the appropriate block response based on verification status."""
        today = timezone.now().date()

        if v.status == 'not_submitted':
            return JsonResponse({
                'verification_required': True,
                'status': 'not_submitted',
                'message': 'Complete a verificação de identidade para começar a vender.',
                'action': 'submit_verification',
            }, status=403)

        if v.status == 'pending':
            return JsonResponse({
                'verification_required': True,
                'status': 'pending',
                'message': 'A sua verificação está a ser analisada. Aguarde a aprovação.',
                'action': 'wait',
                'submitted_at': v.first_submitted_at.isoformat() if v.first_submitted_at else None,
            }, status=403)

        if v.status == 'rejected':
            return JsonResponse({
                'verification_required': True,
                'status': 'rejected',
                'message': 'A sua verificação foi rejeitada. Submeta novamente.',
                'rejection_reason': v.rejection_reason,
                'rejection_notes': v.rejection_notes,
                'action': 'resubmit',
            }, status=403)

        if v.status == 'locked':
            if v.lock_reason == 'bi_expired':
                return JsonResponse({
                    'verification_required': True,
                    'status': 'locked',
                    'lock_reason': 'bi_expired',
                    'message': 'O seu BI expirou. Submeta um novo BI para reactivar a conta.',
                    'action': 'submit_new_bi',
                }, status=403)

            if v.lock_reason == 'selfie_overdue':
                return JsonResponse({
                    'verification_required': True,
                    'status': 'locked',
                    'lock_reason': 'selfie_overdue',
                    'message': 'A sua selfie mensal está em falta. Submeta uma selfie para reactivar.',
                    'action': 'submit_monthly_selfie',
                }, status=403)

            return JsonResponse({
                'verification_required': True,
                'status': 'locked',
                'lock_reason': v.lock_reason,
                'message': 'Conta bloqueada. Contacte o suporte.',
                'action': 'contact_support',
            }, status=403)

        return None
