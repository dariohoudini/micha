"""
apps/idempotency/decorators.py

Drop-in decorator for DRF/APIView ``post`` methods that should be safe to
retry. Reads the ``Idempotency-Key`` header, claims the key, runs the handler,
caches the response, replays it on retry.

Usage:
    class CheckoutView(APIView):
        @idempotent(required=True)
        def post(self, request):
            ...

When ``required=False`` (default), requests without the header pass through
unchanged. When ``required=True``, missing/empty header → 400. The latter is
appropriate for high-stakes endpoints (checkout, payouts) where we want to
*force* clients to be retry-safe.
"""
from __future__ import annotations

import hashlib
import json
import functools
import logging

from rest_framework.response import Response

from .models import (
    IdempotencyKey,
    IdempotencyInProgress,
    IdempotencyMismatch,
)

log = logging.getLogger(__name__)

HEADER = 'HTTP_IDEMPOTENCY_KEY'  # WSGI form of "Idempotency-Key"
MAX_KEY_LEN = 128


def _hash_body(request) -> str:
    """Stable hash of the request body — JSON when possible, raw bytes fallback."""
    try:
        # request.data is parsed by DRF; serialize with sorted keys so dict
        # ordering doesn't change the hash.
        payload = json.dumps(request.data, sort_keys=True, default=str).encode('utf-8')
    except Exception:
        payload = request.body or b''
    return hashlib.sha256(payload).hexdigest()


def _serialize_response(resp):
    """Extract status_code + JSON-safe body from a DRF Response or dict."""
    if isinstance(resp, Response):
        # ``resp.data`` may contain DRF-rendered structures; JSON round-trip
        # via the renderer is the most faithful representation.
        try:
            body = json.loads(json.dumps(resp.data, default=str))
        except Exception:
            body = resp.data
        return resp.status_code, body
    # Bare dict / value
    return 200, resp


def _build_replay(cached) -> Response:
    """Build a DRF Response from a cached entry. Adds a marker header so
    callers can see they hit the replay path during debugging."""
    r = Response(cached['body'], status=cached['status_code'])
    r['Idempotent-Replay'] = 'true'
    return r


def idempotent(required: bool = False):
    """Decorator factory.

    Args:
        required: if True, requests missing the header are rejected with 400.
                  if False (default), they pass through unchanged.
    """
    def decorator(view_method):
        @functools.wraps(view_method)
        def wrapper(self, request, *args, **kwargs):
            key = (request.META.get(HEADER) or '').strip()[:MAX_KEY_LEN]

            if not key:
                if required:
                    return Response(
                        {'error': 'idempotency_key_required',
                         'detail': 'This endpoint requires an Idempotency-Key header.'},
                        status=400,
                    )
                return view_method(self, request, *args, **kwargs)

            # Anonymous users get no idempotency — they shouldn't be hitting
            # write endpoints anyway, but be defensive.
            user = getattr(request, 'user', None)
            if not user or not user.is_authenticated:
                return view_method(self, request, *args, **kwargs)

            req_hash = _hash_body(request)

            try:
                row, replay = IdempotencyKey.claim(
                    user=user, key=key, request_hash=req_hash,
                )
            except IdempotencyMismatch:
                return Response(
                    {'error': 'idempotency_key_mismatch',
                     'detail': 'Idempotency-Key reused with a different request body.'},
                    status=422,
                )
            except IdempotencyInProgress:
                return Response(
                    {'error': 'idempotency_in_progress',
                     'detail': 'A request with this Idempotency-Key is already running.'},
                    status=409,
                )
            except Exception:
                # Never let the idempotency layer break the write path — if
                # the dedupe table is unavailable, fall through and accept the
                # (rare) risk of a duplicate over outright 500.
                log.exception('idempotency: claim failed, falling through')
                return view_method(self, request, *args, **kwargs)

            if replay is not None:
                return _build_replay(replay)

            try:
                resp = view_method(self, request, *args, **kwargs)
            except Exception:
                # Handler exploded — release the claim so the client can retry
                # cleanly with the same key instead of being stuck at 409.
                try:
                    row.abandon()
                except Exception:
                    pass
                raise

            # Only cache successful, JSON-shaped responses. 4xx/5xx are not
            # cached because the client retry is expected to recover.
            status_code, body = _serialize_response(resp)
            if 200 <= status_code < 300:
                try:
                    row.complete(status_code=status_code, body=body)
                except Exception:
                    log.exception('idempotency: complete failed')
            else:
                # Don't lock the key over a transient failure response.
                try:
                    row.abandon()
                except Exception:
                    pass

            return resp
        return wrapper
    return decorator
