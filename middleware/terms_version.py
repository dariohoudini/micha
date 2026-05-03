"""
Terms Version Middleware
Forces users to re-accept T&C when a new version is published.
Set CURRENT_TC_VERSION in settings.py to trigger re-consent.
"""
from django.http import JsonResponse

EXEMPT_PATHS = [
    '/api/v1/auth/login/',
    '/api/v1/auth/logout/',
    '/api/v1/auth/token/refresh/',
    '/api/v1/auth/accept-terms/',
    '/health/',
]

class TermsVersionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path in EXEMPT_PATHS:
            return self.get_response(request)

        if request.user.is_authenticated:
            from django.conf import settings
            current_version = getattr(settings, 'CURRENT_TC_VERSION', '1.0')
            from apps.users.models import ConsentLog
            accepted = ConsentLog.objects.filter(
                user=request.user,
                consent_type='terms_of_service',
                version=current_version,
                granted=True,
            ).exists()
            if not accepted:
                return JsonResponse({
                    'error': 'terms_update_required',
                    'detail': 'Our Terms and Conditions have been updated. Please review and accept the new terms to continue.',
                    'version': current_version,
                    'accept_url': '/api/v1/auth/accept-terms/',
                }, status=403)

        return self.get_response(request)
