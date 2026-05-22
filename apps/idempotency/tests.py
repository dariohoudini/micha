"""
Idempotency decorator tests.

The ``@idempotent`` decorator wraps mutating DRF endpoints and
guarantees that a retry with the same Idempotency-Key replays the
original response — never re-executes the side effect. This is the
single most important defence against double-orders / double-charges
during network instability.

These tests verify:

  • Retry with same key → cached response replayed; handler runs ONCE
  • Retry with different key → handler runs AGAIN (fresh execution)
  • In-flight retry (key claimed but not completed) → 409
  • Key reused with DIFFERENT body → 422 (likely client bug)
  • Anonymous user → handler always runs (no idempotency without identity)
  • Non-success responses (4xx/5xx) → NOT cached (client should retry)

Why this file exists
─────────────────────
The audit found apps/idempotency had ZERO tests despite being used
by CheckoutView and 7 other money-mutating endpoints. The decorator's
correctness is the structural defence against duplicate charges.
A regression here would silently leak money.
"""
import uuid
from types import SimpleNamespace

import pytest
from rest_framework.response import Response

from apps.idempotency.decorators import idempotent
from apps.idempotency.models import IdempotencyKey, IdempotencyStatus


# ─── Helpers ──────────────────────────────────────────────────────────
#
# We test the decorator by invoking the wrapped method DIRECTLY with a
# constructed pseudo-request. The decorator only reads request.META,
# request.data, request.body, and request.user — we can build all of
# those without spinning up DRF's URL + auth dispatch machinery.
#
# Why not use APIClient + a real view: routing a one-off view through
# APIClient requires installing it in ROOT_URLCONF, which leaks into
# other tests via Django's URL caches. The direct-invoke approach is
# isolated, fast, and exercises the EXACT decorator logic we want to
# verify.


def _make_view(handler_calls, *, required=False, status=200):
    """Build a callable that mimics the @idempotent-wrapped post() of
    an APIView. The wrapped function increments handler_calls['n']
    each time it actually executes (so tests can assert ran-once)."""

    class _FakeView:
        @idempotent(required=required)
        def post(self, request):
            handler_calls['n'] += 1
            return Response({'count': handler_calls['n']}, status=status)

    return _FakeView()


def _fake_request(user, body, key=None):
    """Build a minimal pseudo-request the decorator can consume."""
    import json as _json
    meta = {}
    if key:
        meta['HTTP_IDEMPOTENCY_KEY'] = key
    req = SimpleNamespace(
        META=meta,
        data=body or {},
        body=_json.dumps(body or {}).encode('utf-8'),
        user=user,
    )
    return req


def _post(view, user, body=None, key=None):
    """Invoke the @idempotent-wrapped post() with the fake request."""
    return view.post(_fake_request(user, body, key=key))


# ─── Tests ────────────────────────────────────────────────────────────


@pytest.mark.django_db
class TestIdempotencyReplay:
    """The core retry-safety guarantee: same key → same response, side
    effect runs once."""

    def test_anonymous_user_bypasses_idempotency(self):
        """Without an authenticated user, the decorator can't key the
        idempotency table on (user, key). It must pass through. Test
        that the handler runs on every call from an anonymous user."""
        from django.contrib.auth.models import AnonymousUser
        calls = {'n': 0}
        view = _make_view(calls)
        key = f'test-{uuid.uuid4().hex}'
        anon = AnonymousUser()

        _post(view, user=anon, key=key)
        _post(view, user=anon, key=key)

        assert calls['n'] == 2, (
            'anonymous user should bypass idempotency '
            f'(handler ran {calls["n"]}× expected 2)'
        )

    def test_authenticated_retry_with_same_key_replays(self, buyer):
        """The headline guarantee: authenticated user, same key, retry
        → cached response served; handler runs exactly once."""
        calls = {'n': 0}
        view = _make_view(calls)
        key = f'test-{uuid.uuid4().hex}'

        r1 = _post(view, user=buyer, key=key)
        r2 = _post(view, user=buyer, key=key)

        assert calls['n'] == 1, (
            f'handler ran {calls["n"]}× on retry — must be 1 (cached replay)'
        )
        assert r1.status_code == r2.status_code
        # Response bodies should match
        assert r1.data == r2.data, (
            f'replay returned different body: {r1.data} vs {r2.data}'
        )
        # Replay header marker — DRF Response stores headers in
        # ``._headers`` (legacy) or via the headers property. Check
        # by indexing the Response like an HttpResponse.
        try:
            replay_marker = r2['Idempotent-Replay']
        except KeyError:
            replay_marker = r2.headers.get('Idempotent-Replay', '') if hasattr(r2, 'headers') else ''
        assert replay_marker == 'true', (
            f'cached replay should carry Idempotent-Replay: true header; got {replay_marker!r}'
        )

    def test_different_key_runs_handler_again(self, buyer):
        """Different idempotency key = different intent = handler runs
        each time."""
        calls = {'n': 0}
        view = _make_view(calls)

        _post(view, user=buyer, key=f'key-a-{uuid.uuid4().hex}')
        _post(view, user=buyer, key=f'key-b-{uuid.uuid4().hex}')

        assert calls['n'] == 2

    def test_same_key_with_different_body_rejected(self, buyer):
        """Same key + DIFFERENT request body = client bug. Return 422
        rather than replay the wrong response."""
        calls = {'n': 0}
        view = _make_view(calls)
        key = f'test-{uuid.uuid4().hex}'

        r1 = _post(view, user=buyer, key=key, body={'amount': 100})
        r2 = _post(view, user=buyer, key=key, body={'amount': 9999})  # changed!

        assert r1.status_code == 200
        assert r2.status_code == 422
        body = r2.data
        assert body.get('error') == 'idempotency_key_mismatch', body

    def test_failure_response_not_cached(self, buyer):
        """4xx/5xx responses must NOT be cached — the client expects to
        retry and recover. If we cached a 500, the retry would replay
        the 500 forever instead of letting the handler succeed."""
        calls = {'n': 0}
        view = _make_view(calls, status=500)
        key = f'test-{uuid.uuid4().hex}'

        _post(view, user=buyer, key=key)
        # The IdempotencyKey row should be ABANDONED (or absent), not COMPLETED.
        row = IdempotencyKey.objects.filter(user=buyer, key=key).first()
        if row:
            # If a row exists, it must NOT be marked completed.
            assert row.status != IdempotencyStatus.COMPLETED, (
                'non-2xx response was cached as completed — client retries '
                'would now replay the failure forever'
            )

    def test_required_true_rejects_without_key(self, buyer):
        """When @idempotent(required=True), requests missing the
        header are rejected with 400 instead of passing through."""
        calls = {'n': 0}
        view = _make_view(calls, required=True)

        r = _post(view, user=buyer)  # no key
        assert r.status_code == 400
        assert calls['n'] == 0
        assert r.data.get('error') == 'idempotency_key_required'


@pytest.mark.django_db
class TestIdempotencyClaim:
    """Direct tests of the IdempotencyKey.claim() classmethod — the
    low-level primitive the decorator wraps."""

    def test_first_claim_creates_in_progress_row(self, buyer):
        from apps.idempotency.models import IdempotencyKey
        key = 'test-claim-1'
        req_hash = 'hash-a'

        row, replay = IdempotencyKey.claim(
            user=buyer, key=key, request_hash=req_hash,
        )
        assert row is not None
        assert replay is None  # first call, no cached response
        assert row.status == IdempotencyStatus.IN_PROGRESS

    def test_claim_after_complete_returns_replay(self, buyer):
        from apps.idempotency.models import IdempotencyKey
        key = 'test-claim-2'
        req_hash = 'hash-b'

        row, _ = IdempotencyKey.claim(user=buyer, key=key, request_hash=req_hash)
        row.complete(status_code=201, body={'ok': True})

        # Second claim with same hash → replay payload returned
        row2, replay = IdempotencyKey.claim(
            user=buyer, key=key, request_hash=req_hash,
        )
        assert replay is not None
        assert replay['status_code'] == 201
        assert replay['body'] == {'ok': True}

    def test_claim_in_progress_raises_conflict(self, buyer):
        """Same key claimed twice while still in-progress → conflict.
        The decorator returns 409 to make the client back off rather
        than fight itself with parallel duplicate attempts."""
        from apps.idempotency.models import (
            IdempotencyKey, IdempotencyInProgress,
        )
        key = 'test-claim-3'
        req_hash = 'hash-c'

        IdempotencyKey.claim(user=buyer, key=key, request_hash=req_hash)
        # Don't complete — try to claim again
        with pytest.raises(IdempotencyInProgress):
            IdempotencyKey.claim(user=buyer, key=key, request_hash=req_hash)

    def test_claim_with_different_hash_raises_mismatch(self, buyer):
        """Same key + DIFFERENT request hash = client bug. Refuse
        rather than silently serve a stale response for the wrong
        intent."""
        from apps.idempotency.models import (
            IdempotencyKey, IdempotencyMismatch,
        )
        key = 'test-claim-4'

        row, _ = IdempotencyKey.claim(
            user=buyer, key=key, request_hash='hash-original',
        )
        row.complete(status_code=200, body={'ok': True})

        with pytest.raises(IdempotencyMismatch):
            IdempotencyKey.claim(
                user=buyer, key=key, request_hash='hash-CHANGED',
            )
