"""
Gap-Coverage CH10 — service-principal scoping verification pass.

Machine principals (API keys) are the internal service identities. The
IAM spec requires them to be SCOPED, deny-by-default: a key granted only
its needed scopes must NOT reach anything else, so a compromised
integration has a bounded blast radius. These tests turn that from
"should work" into "provably works".
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.dev_keys.models import APIKey
from apps.dev_keys.permissions import (
    RequiresScope, make_scope_permission, method_requires_scope,
)


class _OrdersWriteView(APIView):
    authentication_classes = []
    permission_classes = []

    @method_requires_scope('orders:write')
    def post(self, request):
        return Response({'ok': True})


class ServicePrincipalScopingTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            email='svc@test.ao', password='pw12345678!', username='svc')
        cls.read_key = APIKey.objects.create(
            user=cls.user, name='read-only integration',
            key_hash='h' * 64, key_prefix='mk_read',
            scopes=['orders:read'])

    def test_scope_grant_is_minimal_not_broad(self):
        # A read scope must not imply write, and an unknown scope is denied
        # — deny-by-default, no wildcard behaviour.
        self.assertTrue(self.read_key.has_scope('orders:read'))
        self.assertFalse(self.read_key.has_scope('orders:write'))
        self.assertFalse(self.read_key.has_scope('payouts:manage'))
        self.assertFalse(self.read_key.has_scope(''))

    def test_permission_class_denies_out_of_scope_key(self):
        perm = make_scope_permission('orders:write')()
        request = APIRequestFactory().post('/x')
        request._api_key = self.read_key
        self.assertFalse(perm.has_permission(request, view=None))

    def test_permission_class_allows_in_scope_key(self):
        perm = make_scope_permission('orders:read')()
        request = APIRequestFactory().get('/x')
        request._api_key = self.read_key
        self.assertTrue(perm.has_permission(request, view=None))

    def test_permission_class_passthrough_for_non_key_auth(self):
        # No API key on the request → this layer defers to the user-level
        # permission classes (it must not block JWT-authenticated users).
        perm = make_scope_permission('orders:write')()
        request = APIRequestFactory().post('/x')
        self.assertTrue(perm.has_permission(request, view=None))

    def test_method_decorator_returns_403_insufficient_scope(self):
        factory = APIRequestFactory()
        request = factory.post('/x')
        request._api_key = self.read_key
        response = _OrdersWriteView.as_view()(request)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data['error'], 'insufficient_scope')
        self.assertEqual(response.data['required_scope'], 'orders:write')

    def test_method_decorator_allows_in_scope_key(self):
        write_key = APIKey.objects.create(
            user=self.user, name='writer', key_hash='w' * 64,
            key_prefix='mk_write', scopes=['orders:write'])
        request = APIRequestFactory().post('/x')
        request._api_key = write_key
        response = _OrdersWriteView.as_view()(request)
        self.assertEqual(response.status_code, 200)
