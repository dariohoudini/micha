import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.core.api_errors import ApiError
from apps.core.responses import normalize_error_body

logger = logging.getLogger("micha")


def custom_exception_handler(exc, context):
    """Single error-shaping path for raised exceptions.

    Delegates body shaping to apps.core.responses.normalize_error_body so
    this path and the egress ErrorEnvelopeMiddleware produce byte-identical
    CH4-superset bodies. This handler keeps only the concerns specific to
    the raise-path: ApiError unwrapping, the 429 Retry-After header, and
    5xx logging.
    """
    request = context.get("request")
    request_id = getattr(request, "request_id", "-") if request else "-"

    # Canonical domain error raised by service/view code.
    if isinstance(exc, ApiError):
        body = normalize_error_body(exc.as_body(), exc.status_code, request)
        body["request_id"] = request_id
        return Response(body, status=exc.status_code)

    response = exception_handler(exc, context)

    if response is None:
        logger.exception(f"Unhandled exception [request_id={request_id}]: {exc}")
        body = normalize_error_body(None, 500, request)
        body["request_id"] = request_id
        return Response(body, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    if response.status_code >= 500:
        logger.error(f"{response.status_code} error [request_id={request_id}]: {exc}",
                     exc_info=True)

    body = normalize_error_body(response.data, response.status_code, request)
    body["request_id"] = request_id

    # 429 — surface the throttle wait both as a header (RFC 7231 §7.1.3) and
    # in the body so the client can show a countdown.
    if response.status_code == 429:
        retry_after = getattr(exc, "wait", None)
        if retry_after is not None:
            try:
                retry_after = int(round(float(retry_after)))
                response["Retry-After"] = str(retry_after)
                body["retry_after_seconds"] = retry_after
            except Exception:
                pass
        scope = getattr(getattr(exc, "detail", None), "code", None)
        if scope:
            body["scope"] = str(scope)

    response.data = body
    return response
