"""
Fail-open / fail-closed rate-limit behaviour (Rate Limiting doc CH2/CH11/CH14).

The load-bearing property: when the counter store (Redis) is unavailable,
GENERAL traffic fails OPEN (served — availability) but SECURITY-CRITICAL
limits (login/OTP/money) fail CLOSED (denied — the abuse cost is too high).
"""
from unittest import mock

from rest_framework.exceptions import Throttled
from rest_framework.test import APIRequestFactory
from django.test import SimpleTestCase

from apps.core.throttling import (
    FailClosedAnonRateThrottle, FailClosedUserRateThrottle,
    FailOpenAnonRateThrottle, FailOpenUserRateThrottle,
)


class _AnonReq:
    """Minimal request: anonymous, with a client IP for the cache key."""
    method = 'POST'
    META = {'REMOTE_ADDR': '203.0.113.7'}

    class user:
        is_authenticated = False
    auth = None


def _store_down(throttle_cls, scope='login'):
    """Build a throttle whose cache.get raises (Redis down)."""
    t = throttle_cls()
    t.scope = scope
    # Give it a rate so get_rate() doesn't short-circuit.
    t.rate = '5/min'
    t.num_requests, t.duration = 5, 60
    return t


class FailClosedTests(SimpleTestCase):
    def test_login_denies_when_store_unavailable(self):
        t = _store_down(FailClosedAnonRateThrottle, 'login')
        with mock.patch.object(t, 'get_cache_key', return_value='rl:login:x'), \
             mock.patch.object(t, 'cache', create=True) as cache:
            cache.get.side_effect = ConnectionError('redis down')
            with self.assertRaises(Throttled):               # DENIED (429)
                t.allow_request(_AnonReq(), None)

    def test_payment_denies_when_store_unavailable(self):
        t = FailClosedUserRateThrottle()
        t.scope = 'payment'
        t.rate = '20/hour'
        t.num_requests, t.duration = 20, 3600
        with mock.patch.object(t, 'get_cache_key', return_value='rl:pay:x'), \
             mock.patch.object(t, 'cache', create=True) as cache:
            cache.get.side_effect = ConnectionError('redis down')
            with self.assertRaises(Throttled):
                t.allow_request(_AnonReq(), None)


class FailOpenTests(SimpleTestCase):
    def test_general_allows_when_store_unavailable(self):
        t = FailOpenAnonRateThrottle()
        t.scope = 'anon'
        t.rate = '1000/hour'
        t.num_requests, t.duration = 1000, 3600
        with mock.patch.object(t, 'get_cache_key', return_value='rl:anon:x'), \
             mock.patch.object(t, 'cache', create=True) as cache:
            cache.get.side_effect = ConnectionError('redis down')
            # Availability: served despite the store being down.
            self.assertTrue(t.allow_request(_AnonReq(), None))

    def test_general_user_allows_when_store_unavailable(self):
        t = FailOpenUserRateThrottle()
        t.scope = 'user'
        t.rate = '1000/hour'
        t.num_requests, t.duration = 1000, 3600
        with mock.patch.object(t, 'get_cache_key', return_value='rl:user:x'), \
             mock.patch.object(t, 'cache', create=True) as cache:
            cache.get.side_effect = ConnectionError('redis down')
            self.assertTrue(t.allow_request(_AnonReq(), None))


class NormalOperationTests(SimpleTestCase):
    def test_under_limit_allows_when_store_works(self):
        t = FailClosedAnonRateThrottle()
        t.scope = 'login'
        t.rate = '5/min'
        t.num_requests, t.duration = 5, 60
        with mock.patch.object(t, 'get_cache_key', return_value='rl:login:y'), \
             mock.patch.object(t, 'cache', create=True) as cache:
            cache.get.return_value = []          # empty history → under limit
            cache.set.return_value = None
            self.assertTrue(t.allow_request(_AnonReq(), None))
