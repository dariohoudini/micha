"""
DRF EXCEPTION_HANDLER.

Catches exceptions RAISED inside DRF dispatch (ValidationError,
PermissionDenied, NotFound, etc.). Delegates body shaping to the
canonical normalizer in apps/core/responses.py so this path produces
byte-identical output to the egress middleware for the same input.

The ``return Response({'error': ...}, status=400)`` ad-hoc path inside
views does NOT come through here — that's caught by the egress
middleware (middleware/error_envelope.py).
"""
import logging

from rest_framework.views import exception_handler as drf_default_exception_handler
from rest_framework.response import Response
from rest_framework import status as drf_status


logger = logging.getLogger('micha')


def custom_exception_handler(exc, context):
    request = context.get('request')

    response = drf_default_exception_handler(exc, context)

    # Unhandled exceptions — DRF returns None. Synthesize a 500.
    if response is None:
        request_id = getattr(request, 'request_id', '-') if request else '-'
        logger.exception('Unhandled exception [request_id=%s]: %s', request_id, exc)
        from apps.core.responses import normalize_error_body
        return Response(
            normalize_error_body({}, 500, request=request),
            status=drf_status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # DRF returned a structured error — walk through the normalizer for
    # canonical shape. The middleware would also catch this on the way
    # out, but doing it here means the body is canonical immediately,
    # which is helpful for downstream middleware that inspects the body.
    from apps.core.responses import normalize_error_body
    response.data = normalize_error_body(
        response.data, response.status_code, request=request,
    )

    # 5xx — log with request_id for correlation.
    if response.status_code >= 500:
        request_id = getattr(request, 'request_id', '-') if request else '-'
        logger.error('5xx error [request_id=%s]: %s', request_id, exc, exc_info=True)

    return response
