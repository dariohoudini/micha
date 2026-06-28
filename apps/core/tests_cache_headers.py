"""
Secure-by-default cache headers (Caching & CDN doc CH14; Security cache-bypass).

The load-bearing property: a per-user / credentialed response that didn't
deliberately set a cache policy is marked private,no-store so no SHARED
cache (CDN/proxy) can ever store one user's data and serve it to another —
RLS protects the database, not the cache. Anonymous-public responses and
responses the view deliberately marked cacheable are left untouched.
"""
from django.http import HttpResponse, JsonResponse
from django.test import SimpleTestCase

from middleware.cache_control import PrivateByDefaultCacheMiddleware


class _Req:
    def __init__(self, *, authorization=None, user_authed=False):
        self.META = {}
        if authorization:
            self.META['HTTP_AUTHORIZATION'] = authorization

        class _U:
            is_authenticated = user_authed
        self.user = _U()


def _run(req, response):
    mw = PrivateByDefaultCacheMiddleware(lambda r: response)
    return mw(req)


class PrivateByDefaultTests(SimpleTestCase):
    def test_token_authed_response_forced_no_store(self):
        # API request with Authorization header, no cache policy set.
        resp = _run(_Req(authorization='Bearer abc'), JsonResponse({'cart': 1}))
        self.assertEqual(resp['Cache-Control'], 'private, no-store')
        self.assertIn('Authorization', resp['Vary'])

    def test_session_authed_response_forced_no_store(self):
        resp = _run(_Req(user_authed=True), JsonResponse({'profile': 1}))
        self.assertEqual(resp['Cache-Control'], 'private, no-store')

    def test_anonymous_response_untouched(self):
        # No credentials → not a private-leak risk → leave header decisions
        # to the view / CDN (public cacheability is allowed).
        resp = _run(_Req(), JsonResponse({'public_catalog': 1}))
        self.assertFalse(resp.has_header('Cache-Control'))

    def test_explicit_view_policy_is_respected(self):
        # A view that deliberately marked an authenticated response cacheable
        # (e.g. per-user browser cache) must NOT be clobbered.
        r = JsonResponse({'x': 1})
        r['Cache-Control'] = 'private, max-age=60'
        resp = _run(_Req(authorization='Bearer abc'), r)
        self.assertEqual(resp['Cache-Control'], 'private, max-age=60')

    def test_explicit_public_policy_respected(self):
        # An authenticated-but-deliberately-public response (rare) is kept.
        r = HttpResponse('ok')
        r['Cache-Control'] = 'public, max-age=300'
        resp = _run(_Req(user_authed=True), r)
        self.assertEqual(resp['Cache-Control'], 'public, max-age=300')
