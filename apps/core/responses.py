"""
apps/core/responses.py — canonical error envelope.

Every error response across the API should match this shape:

  {
    "error":        "snake_case_code",
    "detail":       "Human-readable message.",
    "request_id":   "abc12345",
    "field_errors": { "field_name": ["msg", ...] }   # optional
  }

Three layers enforce it:

  1. ``apps/core/responses.error_response()`` and friends — new code
     should call these helpers, not build dicts by hand.

  2. ``middleware/exception_handler.custom_exception_handler`` — handles
     responses produced by DRF when a view RAISES (ValidationError,
     PermissionDenied, NotFound, …). Delegates body shaping to
     ``normalize_error_body()`` here for consistency.

  3. ``middleware/error_envelope.ErrorEnvelopeMiddleware`` — catches the
     long tail: ad-hoc ``return Response({'error': ...}, status=400)``
     sites that bypass the DRF exception handler. Walks the response
     body through ``normalize_error_body()`` on the way out.

The contract is enforced at egress so legacy view code keeps working
while the response shape is uniform. New code should use the helpers,
but missing them isn't a correctness bug — the middleware backstops it.
"""
from __future__ import annotations

from rest_framework.response import Response


# ── Status → default error-code map ─────────────────────────────────────────

_STATUS_TO_CODE = {
    400: 'bad_request',
    401: 'authentication_required',
    403: 'permission_denied',
    404: 'not_found',
    405: 'method_not_allowed',
    406: 'not_acceptable',
    408: 'request_timeout',
    409: 'conflict',
    410: 'gone',
    413: 'payload_too_large',
    415: 'unsupported_media_type',
    422: 'unprocessable_entity',
    429: 'rate_limited',
}

_DEFAULT_DETAIL = {
    400: 'Bad request.',
    401: 'Authentication credentials were not provided or are invalid.',
    403: 'You do not have permission to perform this action.',
    404: 'The requested resource was not found.',
    405: 'Method not allowed.',
    409: 'Conflict.',
    422: 'Unprocessable entity.',
    429: 'Too many requests. Please slow down and try again later.',
}


def code_for_status(status_code: int) -> str:
    if status_code >= 500:
        return 'server_error'
    return _STATUS_TO_CODE.get(status_code, 'error')


def detail_for_status(status_code: int) -> str:
    if status_code >= 500:
        return 'An internal error occurred. Our team has been notified.'
    return _DEFAULT_DETAIL.get(status_code, 'An error occurred.')


# ── Canonical builders ─────────────────────────────────────────────────────

def error_response(
    code: str,
    detail: str,
    *,
    status: int = 400,
    field_errors: dict | None = None,
    request=None,
) -> Response:
    """Build a canonical error response.

    Usage:
        return error_response('invalid_otp', 'Invalid or expired code.',
                              status=400)

    The middleware will fill request_id later — passing request here is
    optional and only used if you want it stamped immediately (rare).
    """
    body: dict = {'error': code, 'detail': detail}
    if field_errors:
        body['field_errors'] = field_errors
    if request is not None:
        body['request_id'] = getattr(request, 'request_id', '-')
    return Response(body, status=status)


def validation_error(
    detail: str = 'Validation failed.',
    *,
    field_errors: dict | None = None,
    request=None,
) -> Response:
    return error_response('validation_error', detail,
                          status=400, field_errors=field_errors,
                          request=request)


def not_found(detail: str = 'The requested resource was not found.',
              *, request=None) -> Response:
    return error_response('not_found', detail, status=404, request=request)


def forbidden(detail: str = 'You do not have permission to perform this action.',
              *, request=None) -> Response:
    return error_response('permission_denied', detail, status=403,
                          request=request)


def conflict(code: str = 'conflict', detail: str = 'Conflict.',
             *, request=None) -> Response:
    return error_response(code, detail, status=409, request=request)


# ── Shape detection + normalization ────────────────────────────────────────

def is_canonical(data) -> bool:
    """True if ``data`` already matches the canonical envelope.

    Canonical means: dict with non-empty 'error' (a code, not a sentence)
    AND non-empty 'detail'. We treat 'error' as a code when it's short,
    has no spaces, and isn't title-cased — heuristic but reliable for
    snake_case codes vs human messages.
    """
    if not isinstance(data, dict):
        return False
    err = data.get('error')
    det = data.get('detail')
    if not isinstance(err, str) or not err:
        return False
    if not isinstance(det, str) or not det:
        return False
    if ' ' in err or len(err) > 60:
        return False
    return True


def _looks_like_code(value) -> bool:
    """Heuristic: is this 'error' value a snake_case code (not a sentence)?"""
    if not isinstance(value, str):
        return False
    if not value or ' ' in value:
        return False
    if len(value) > 60:
        return False
    return True


def normalize_error_body(data, status_code: int, request=None) -> dict:
    """Walk any 4xx/5xx response body to canonical shape.

    Pure function — returns a new dict, does not mutate ``data``.

    Used by both the DRF exception handler (for raised exceptions) and
    the error-envelope middleware (for ad-hoc Response({...}) returns).
    Keeping the logic here means both paths produce byte-identical
    output for the same input.
    """
    request_id = getattr(request, 'request_id', '-') if request else '-'

    # 5xx — never leak internal details. Always replace with generic.
    if status_code >= 500:
        return {
            'error': 'server_error',
            'detail': detail_for_status(status_code),
            'request_id': request_id,
        }

    default_code = code_for_status(status_code)
    default_detail = detail_for_status(status_code)

    # Case 1: scalar or list bodies — wrap with defaults.
    if not isinstance(data, dict):
        return {
            'error': default_code,
            'detail': str(data) if data else default_detail,
            'request_id': request_id,
        }

    err = data.get('error')
    det = data.get('detail')

    # Case 2: DRF validation errors — dict of {field: [messages]} with no
    # 'error' / 'detail' keys. Flatten to field_errors.
    if err is None and det is None:
        field_errors = {}
        non_field = []
        for k, v in data.items():
            if k == 'non_field_errors':
                non_field.extend(v if isinstance(v, list) else [v])
            else:
                field_errors[k] = v if isinstance(v, list) else [v]
        body = {
            'error': 'validation_error' if field_errors or non_field else default_code,
            'detail': ' '.join(str(m) for m in non_field) or default_detail,
            'request_id': request_id,
        }
        if field_errors:
            body['field_errors'] = field_errors
        return body

    # Case 3: 'error' present.
    if err is not None:
        if _looks_like_code(err):
            # 'error' is a snake_case code — keep, ensure 'detail' is set.
            body = {
                'error': err,
                'detail': det if det else default_detail,
                'request_id': request_id,
            }
        else:
            # 'error' looks like a sentence — promote to 'detail', derive code.
            body = {
                'error': default_code,
                'detail': str(err),
                'request_id': request_id,
            }
        # Preserve field_errors / errors if the caller included one.
        if data.get('field_errors'):
            body['field_errors'] = data['field_errors']
        elif data.get('errors') and isinstance(data['errors'], dict):
            body['field_errors'] = data['errors']
        return body

    # Case 4: only 'detail' — derive code from status.
    return {
        'error': default_code,
        'detail': str(det),
        'request_id': request_id,
    }
