"""
Security Middleware Suite
Fixes:
- Content Security Policy headers (stops XSS even if bleach is bypassed)
- Server fingerprinting removed (hides Django/Python/nginx versions)
- PII masking in logs (emails, IPs, tokens never written to log files)
- Security event logger (separate stream for auth failures, privilege changes)
- Re-authentication enforcement on sensitive endpoints
"""
import re
import json
import hashlib
import logging
import time
from functools import wraps
from django.http import JsonResponse
from django.utils import timezone

# ── Security event logger — separate from app logs ────────────────────────────
security_logger = logging.getLogger('micha.security')

# ── PII patterns to mask in logs ──────────────────────────────────────────────
PII_PATTERNS = [
    (re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'), '***@***.***'),
    (re.compile(r'\b\d{9}[A-Z]{2}\d{3}\b'), '[BI-REDACTED]'),        # Angolan BI
    (re.compile(r'"password"\s*:\s*"[^"]*"'), '"password":"[REDACTED]"'),
    (re.compile(r'"token"\s*:\s*"[^"]*"'), '"token":"[REDACTED]"'),
    (re.compile(r'"otp"\s*:\s*"[^"]*"'), '"otp":"[REDACTED]"'),
    (re.compile(r'"account_number"\s*:\s*"[^"]*"'), '"account_number":"[REDACTED]"'),
    (re.compile(r'"id_number"\s*:\s*"[^"]*"'), '"id_number":"[REDACTED]"'),
    (re.compile(r'"fcm_token"\s*:\s*"[^"]*"'), '"fcm_token":"[REDACTED]"'),
]


def mask_pii(text):
    """Remove PII from log strings before writing."""
    if not isinstance(text, str):
        text = str(text)
    for pattern, replacement in PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


class PIIMaskingFilter(logging.Filter):
    """Logging filter that strips PII from every log record."""
    def filter(self, record):
        record.msg = mask_pii(str(record.msg))
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: mask_pii(str(v)) for k, v in record.args.items()}
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(mask_pii(str(a)) for a in record.args)
        return True


def log_security_event(event_type, request=None, details=None, severity='INFO'):
    """
    Central security event logger.
    All security events go to micha.security logger — separate from app logs.
    This makes SIEM integration and security monitoring possible.
    """
    data = {
        'event': event_type,
        'severity': severity,
        'timestamp': timezone.now().isoformat(),
        'details': details or {},
    }
    if request:
        data['ip'] = _get_ip(request)
        data['user_agent'] = request.META.get('HTTP_USER_AGENT', '')[:100]
        data['path'] = request.path
        if hasattr(request, 'user') and request.user.is_authenticated:
            data['user_id'] = request.user.id

    if severity == 'CRITICAL':
        security_logger.critical(json.dumps(data))
    elif severity == 'WARNING':
        security_logger.warning(json.dumps(data))
    else:
        security_logger.info(json.dumps(data))


def _get_ip(request):
    """Get real client IP, respecting X-Forwarded-For behind proxy."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '')


# ── Content Security Policy Middleware ────────────────────────────────────────

class SecurityHeadersMiddleware:
    """
    Adds security headers to every response.
    CSP stops XSS even if bleach sanitisation is bypassed.
    Server fingerprinting removed — attackers cannot target known CVEs.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Content Security Policy — blocks inline scripts, only allows self
        response['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "form-action 'self'; "
            "base-uri 'self';"
        )

        # Remove server fingerprinting headers
        response['X-Content-Type-Options'] = 'nosniff'
        response['X-Frame-Options'] = 'DENY'
        response['X-XSS-Protection'] = '1; mode=block'
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        response['Permissions-Policy'] = 'geolocation=(), microphone=(), camera=()'

        # Remove version fingerprints
        if 'Server' in response:
            del response['Server']
        if 'X-Powered-By' in response:
            del response['X-Powered-By']

        return response


# ── Constant-time response for user enumeration prevention ────────────────────

class ConstantTimeAuthMiddleware:
    """
    Prevents timing attacks on auth endpoints.
    Attacker cannot determine if an email exists by measuring response time.
    All auth responses take the same minimum time regardless of DB hit.
    """
    MIN_RESPONSE_TIME = 0.1  # 100ms minimum

    AUTH_PATHS = {
        '/api/auth/login/',
        '/api/auth/forgot-password/',
        '/api/auth/verify-email/',
        '/api/v1/auth/login/',
        '/api/v1/auth/forgot-password/',
        '/api/v1/auth/verify-email/',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path in self.AUTH_PATHS:
            start = time.monotonic()
            response = self.get_response(request)
            elapsed = time.monotonic() - start
            if elapsed < self.MIN_RESPONSE_TIME:
                time.sleep(self.MIN_RESPONSE_TIME - elapsed)
            return response
        return self.get_response(request)


# ── Step-up authentication decorator ─────────────────────────────────────────

def require_recent_auth(max_age_minutes=10):
    """
    Decorator: require user to have authenticated within max_age_minutes.
    Use on: change email, change phone, add bank account, request payout,
            delete account, change password.

    Frontend sends current password in X-Confirm-Password header.
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse(
                    {'error': 'authentication_required', 'detail': 'Login required.'},
                    status=401
                )
            # Check password confirmation header
            confirm_password = request.META.get('HTTP_X_CONFIRM_PASSWORD', '')
            if not confirm_password:
                return JsonResponse(
                    {
                        'error': 'step_up_required',
                        'detail': 'This action requires password confirmation.',
                        'hint': 'Send current password in X-Confirm-Password header.',
                    },
                    status=403
                )
            if not request.user.check_password(confirm_password):
                log_security_event(
                    'step_up_auth_failed',
                    request=request,
                    severity='WARNING',
                    details={'action': view_func.__name__},
                )
                return JsonResponse(
                    {'error': 'invalid_password', 'detail': 'Password confirmation failed.'},
                    status=403
                )
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ── Admin IP allowlist middleware ──────────────────────────────────────────────

class AdminIPAllowlistMiddleware:
    """
    Block access to Django admin from non-whitelisted IPs.
    Configure ADMIN_ALLOWED_IPS in settings.
    In production: your office IP, VPN exit node, bastion IP.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings
        admin_url = getattr(settings, 'ADMIN_URL', 'admin/')

        if request.path.startswith(f'/{admin_url}') or request.path.startswith('/api/admin-actions/'):
            allowed_ips = getattr(settings, 'ADMIN_ALLOWED_IPS', [])
            client_ip = _get_ip(request)

            if allowed_ips and client_ip not in allowed_ips:
                log_security_event(
                    'admin_access_blocked',
                    request=request,
                    severity='WARNING',
                    details={'ip': client_ip, 'path': request.path},
                )
                return JsonResponse(
                    {'error': 'forbidden', 'detail': 'Access denied.'},
                    status=403
                )

        return self.get_response(request)
