"""
middleware/error_envelope.py

Final-egress normalizer: walks every 4xx/5xx DRF Response on its way out
and rewrites the body to the canonical envelope defined in
``apps/core/responses.py``.

Why a middleware AND not a codemod across the 240+ ad-hoc Response
sites in views.py files:

  • Codemod risk — 240 sites means a lot of opportunity to introduce
    regressions for shapes that vary subtly per endpoint.

  • Single source of truth — the middleware is the one place where
    the egress contract lives. Add a status code to the map and every
    view that returns it automatically gets the new shape.

  • Backstops new code — a developer adding a fresh view that returns
    ``Response({'error': 'foo'}, status=400)`` doesn't need to know
    about the helpers in apps/core/responses.py. The middleware fixes
    the shape on the way out.

──────────────────────────────────────────────────────────────────────
Why process_template_response, not process_response
──────────────────────────────────────────────────────────────────────

DRF Response is a SimpleTemplateResponse subclass. Django renders
TemplateResponses INSIDE BaseHandler._get_response() BEFORE the
process_response middleware chain runs. By the time process_response
sees the Response, ``_is_rendered`` is True and mutating ``.data``
is a no-op (the bytes have already been committed to ``.content``).

Django provides ``process_template_response(self, request, response)``
specifically for this scenario — it fires BEFORE render(), so the
Response's data is still mutable. This is the only correct hook for
egress normalization of DRF Response bodies.

The middleware is conservative:
  • Only touches DRF Response objects (responses with .data + .status_code).
  • Only touches 4xx / 5xx statuses.
  • Skips responses headed for non-JSON renderers (PDF, HTML, CSV).
  • Skips responses that are already canonical AND have request_id.

5xx responses get a generic body regardless of input — we never leak
internal details to clients.
"""
from __future__ import annotations

from apps.core.responses import normalize_error_body, is_canonical


class ErrorEnvelopeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_template_response(self, request, response):
        """Called by Django for every TemplateResponse (DRF Response is one)
        BEFORE render(). The response's ``.data`` is still mutable here."""

        # Sanity: DRF Response has both .data and .status_code.
        if not hasattr(response, 'data') or not hasattr(response, 'status_code'):
            return response

        # Skip success responses entirely
        if response.status_code < 400:
            return response

        # Skip non-JSON renderers (PDF, HTML download, CSV export) —
        # the data on those is intended for the renderer, not for the
        # JSON envelope.
        renderer = getattr(response, 'accepted_renderer', None)
        if renderer is not None:
            media = getattr(renderer, 'media_type', '') or ''
            if media and 'json' not in media:
                return response

        data = response.data

        # If body is already canonical AND carries the CH4 superset fields
        # (request_id + code), leave it alone. The exception_handler path
        # produces fully-decorated bodies, so this is a no-op for that flow.
        # A legacy-canonical body missing 'code' still falls through to
        # normalize_error_body so it gains code/http_status/documentation_url.
        if (is_canonical(data) and isinstance(data, dict)
                and 'request_id' in data and 'code' in data):
            return response

        response.data = normalize_error_body(
            data, response.status_code, request=request,
        )
        return response
