import json
import logging

logger = logging.getLogger("micha")

try:
    import bleach
    BLEACH_AVAILABLE = True
except ImportError:
    BLEACH_AVAILABLE = False
    logger.warning("bleach not installed — input sanitisation disabled. Run: pip install bleach")

ALLOWED_TAGS = []
ALLOWED_ATTRIBUTES = {}
SKIP_PATHS = ["/api/payments/webhook/", "/api/v1/payments/webhook/"]


def sanitise_value(value):
    if not BLEACH_AVAILABLE:
        return value
    if isinstance(value, str):
        cleaned = bleach.clean(value, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES, strip=True)
        return cleaned
    elif isinstance(value, dict):
        return {k: sanitise_value(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [sanitise_value(i) for i in value]
    return value


class SanitiseInputMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in ("POST", "PUT", "PATCH"):
            skip = any(request.path.startswith(p) for p in SKIP_PATHS)
            if not skip and request.content_type and "application/json" in request.content_type:
                try:
                    body = json.loads(request.body)
                    sanitised = sanitise_value(body)
                    request._body = json.dumps(sanitised).encode("utf-8")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    pass
        return self.get_response(request)
