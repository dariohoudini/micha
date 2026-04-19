"""
Input Sanitisation Middleware
Strips HTML tags and dangerous content from all user-submitted text fields.
Prevents stored XSS attacks where malicious script tags are saved to DB
and later rendered in the frontend.

Requires: pip install bleach
"""
import json
import bleach
import logging

logger = logging.getLogger('micha')

# Tags and attributes that are safe to allow in user content
ALLOWED_TAGS = []       # no HTML at all in API fields
ALLOWED_ATTRIBUTES = {}

# Endpoints where we skip sanitisation (binary uploads, webhooks)
SKIP_PATHS = [
    '/api/payments/webhook/',
    '/api/products/',           # handled per-field in serialiser
]


def sanitise_value(value):
    """Recursively sanitise string values in dicts/lists."""
    if isinstance(value, str):
        cleaned = bleach.clean(value, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)
        if cleaned != value:
            logger.warning(f"Sanitised input: stripped HTML from user value")
        return cleaned
    elif isinstance(value, dict):
        return {k: sanitise_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [sanitise_value(i) for i in value]
    return value


class SanitiseInputMiddleware:
    """
    Sanitise JSON body of all POST/PUT/PATCH requests.
    Does NOT modify GET params — those should be handled in views.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in ('POST', 'PUT', 'PATCH'):
            skip = any(request.path.startswith(p) for p in SKIP_PATHS)
            if not skip and request.content_type and 'application/json' in request.content_type:
                try:
                    body = json.loads(request.body)
                    sanitised = sanitise_value(body)
                    request._sanitised_body = sanitised
                    # Monkey-patch data so DRF picks it up
                    request._body = json.dumps(sanitised).encode('utf-8')
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass  # not JSON — leave it alone

        return self.get_response(request)
