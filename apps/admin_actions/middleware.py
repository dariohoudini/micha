"""
apps/admin_actions/middleware.py

Automatic AdminActionLog coverage for every mutating admin request.

Why this exists
─────────────────
The existing patterns for audit logging are:

  1. ``AdminActionLog.log(request, action, target, ...)`` called manually
     inside the view's body. Used by 10 view files.

  2. ``@audit_admin_action`` decorator applied on the view method.
     Used by 1 view file (admin_api) on 4 endpoints.

A sweep across ~22 admin-gated view files (those importing
IsAdminOrSuperuser or IsAdminUser) shows the majority have neither.

The compliance cost: a regulator asks "show me every admin action
taken on user X" and the answer is "we logged about 30% of them."
That's a failed audit. The forensic cost is worse: during incident
response, you can't tell what an admin did or didn't do.

This middleware closes the gap by recording EVERY admin write
automatically. Manual log() and the decorator still work (they add
richer metadata / proper target_repr); the middleware is the safety
net for endpoints nobody remembered to instrument.

Trigger rules
──────────────
A write is logged iff ALL of:

  • request.path starts with /api/
  • request.method in {POST, PATCH, PUT, DELETE}
  • response.status_code in 2xx
  • request.user is authenticated AND (is_staff OR is_superuser)
  • the request did NOT already write an AdminActionLog row
    (we deduplicate via a marker on the request — if a decorator
    or manual call ran first, this middleware no-ops)

Opt-out
─────────
A view can declare ``admin_audit_skip = True`` to suppress the auto
log for known-safe-and-noisy endpoints (e.g. an admin "ping" endpoint
that's hit by health probes). Skipping is rare — default is log.

Action label
─────────────
The middleware sets action = 'auto:<view_name>:<http_method>' which
doesn't collide with the named choices in AdminActionLog.ACTION_TYPES.
Django's CharField.choices is only validated by full_clean(), not by
.create(), so storage is fine. The label is greppable for "find all
auto-logged admin actions" queries.

Metadata captured
──────────────────
  • view_class: the resolved view class name (e.g. AdminResolveDisputeView)
  • method: HTTP method
  • path: request path (no query string)
  • status: response status code
  • duration_ms: time inside the wrapped handler
  • body_keys: top-level keys of the request body (NOT values — values
    may be PII / passwords)

NEVER raises
─────────────
Audit-write failure must not break the legitimate admin action.
Failures go to log.warning and the response passes through unmodified.
"""
from __future__ import annotations

import logging
import time

from django.utils.deprecation import MiddlewareMixin


log = logging.getLogger(__name__)


# HTTP methods that count as "writes" for audit purposes.
_MUTATING_METHODS = frozenset({'POST', 'PATCH', 'PUT', 'DELETE'})

# Request attribute used to mark "we already logged this request."
# Set by AdminActionLog.log() and the @audit_admin_action decorator;
# this middleware checks before writing its own row.
_LOGGED_MARKER = '_admin_action_logged'


def mark_logged(request):
    """Called by manual log()/decorator paths to suppress the
    auto-log middleware for this request.

    DRF wraps the Django HttpRequest in its own ``rest_framework.request.Request``.
    Code running INSIDE a DRF view sees the wrapper; the middleware
    sees the underlying Django request. setattr on the wrapper alone
    won't propagate. Set the marker on both.
    """
    try:
        setattr(request, _LOGGED_MARKER, True)
    except Exception:
        pass
    inner = getattr(request, '_request', None)
    if inner is not None and inner is not request:
        try:
            setattr(inner, _LOGGED_MARKER, True)
        except Exception:
            pass


def _is_admin(request) -> bool:
    u = getattr(request, 'user', None)
    return bool(
        u and getattr(u, 'is_authenticated', False)
        and (getattr(u, 'is_staff', False) or getattr(u, 'is_superuser', False))
    )


def _view_class_name(request) -> str:
    """Best-effort view-class name for the action label."""
    try:
        match = getattr(request, 'resolver_match', None)
        if match is None:
            return ''
        func = match.func
        cls = getattr(func, 'cls', None) or getattr(func, 'view_class', None)
        if cls is not None:
            return cls.__name__
        return getattr(func, '__name__', '')
    except Exception:
        return ''


def _view_skip(request) -> bool:
    """View can opt out by declaring admin_audit_skip = True."""
    try:
        match = getattr(request, 'resolver_match', None)
        if match is None:
            return False
        func = match.func
        cls = getattr(func, 'cls', None) or getattr(func, 'view_class', None)
        if cls is not None:
            return bool(getattr(cls, 'admin_audit_skip', False))
        return bool(getattr(func, 'admin_audit_skip', False))
    except Exception:
        return False


def _body_keys(request) -> list:
    """Top-level keys of the request body for forensic context.
    Values are NOT captured — they may contain PII / passwords / tokens.
    """
    try:
        data = getattr(request, 'data', None)
        if isinstance(data, dict):
            return list(data.keys())[:30]
    except Exception:
        pass
    return []


def _client_ip(request) -> str:
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return (xff.split(',')[0].strip() if xff
            else request.META.get('REMOTE_ADDR') or '')[:45]


class AdminActionAuditMiddleware:
    """Auto-logs every successful mutating admin request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()
        response = self.get_response(request)

        # Quick rejects in order of cheapness — most requests bail at
        # one of the first checks.
        if request.method not in _MUTATING_METHODS:
            return response
        if not request.path.startswith('/api/'):
            return response
        if not (200 <= response.status_code < 300):
            return response
        if not _is_admin(request):
            return response
        if getattr(request, _LOGGED_MARKER, False):
            # Manual log() / decorator already wrote a richer row.
            return response
        if _view_skip(request):
            return response

        # Log the action. Wrapped wide because audit-write failure
        # must not break the legitimate admin response.
        try:
            from .models import AdminActionLog

            view_name = _view_class_name(request) or '?'
            action = f'auto:{view_name}:{request.method.lower()}'
            duration_ms = int((time.monotonic() - start) * 1000)

            AdminActionLog.objects.create(
                admin=request.user,
                action=action[:50],
                target_type='request',
                target_id=request.path[:100],
                target_repr=f'{request.method} {request.path}'[:200],
                ip_address=_client_ip(request) or None,
                user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:200],
                metadata={
                    'view_class': view_name,
                    'method': request.method,
                    'path': request.path,
                    'status': response.status_code,
                    'duration_ms': duration_ms,
                    'body_keys': _body_keys(request),
                    'auto_logged': True,
                },
            )
        except Exception:
            log.warning('admin_action_audit middleware: log write failed',
                        exc_info=True)

        return response
