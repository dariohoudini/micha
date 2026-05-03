"""
Request/Response structured logging middleware.
Adds request_id, user_id, duration to every log record.
"""
import uuid
import time
import logging
import threading

logger = logging.getLogger('micha.requests')

_local = threading.local()


def get_request_id():
    return getattr(_local, 'request_id', '-')


def get_user_id():
    return getattr(_local, 'user_id', '-')


class RequestIDMiddleware:
    """Injects a unique request_id into every request and log record."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get('X-Request-ID', str(uuid.uuid4())[:8])
        _local.request_id = request_id
        _local.start_time = time.time()

        # Attach to request for use in views
        request.request_id = request_id

        response = self.get_response(request)

        # Log completed request
        duration_ms = int((time.time() - _local.start_time) * 1000)
        user_id = None
        if hasattr(request, 'user') and request.user.is_authenticated:
            user_id = str(request.user.id)
            _local.user_id = user_id

        # Only log API requests, skip static/admin
        if request.path.startswith('/api/'):
            level = logging.WARNING if response.status_code >= 400 else logging.INFO
            logger.log(level, 'request', extra={
                'request_id': request_id,
                'method': request.method,
                'path': request.path,
                'status': response.status_code,
                'duration_ms': duration_ms,
                'user_id': user_id,
                'ip': _get_client_ip(request),
            })

        response['X-Request-ID'] = request_id
        return response


def _get_client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '-')


class StructuredLogFilter(logging.Filter):
    """Injects request_id and user_id into every log record."""

    def filter(self, record):
        record.request_id = getattr(_local, 'request_id', '-')
        record.user_id = getattr(_local, 'user_id', '-')
        return True
