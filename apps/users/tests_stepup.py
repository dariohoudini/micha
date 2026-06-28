"""
Step-up authentication regression tests (IAM/RBAC doc CH7).

Guards against the regression where require_recent_auth assumed the request
was always the first positional arg and therefore 500'd on every DRF
APIView ``def post(self, request)`` it decorated — silently disabling the
step-up gate it was meant to enforce.
"""
import json

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.http import JsonResponse
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from middleware.security import require_recent_auth, _resolve_request


class _DummyReq:
    META = {}
    method = 'POST'


class ResolveRequestTests(SimpleTestCase):
    def test_finds_request_in_fbv_shape(self):
        req = _DummyReq()
        self.assertIs(_resolve_request((req,)), req)

    def test_finds_request_in_drf_shape(self):
        # DRF calls wrapper(self, request, ...); the View instance has no
        # META/method, so the request must still be found.
        view, req = object(), _DummyReq()
        self.assertIs(_resolve_request((view, req)), req)

    def test_none_when_no_request(self):
        self.assertIsNone(_resolve_request((object(),)))


class _GuardedView(APIView):
    authentication_classes = []
    permission_classes = []

    @require_recent_auth()
    def post(self, request):
        return Response({'ok': True})


class StepUpDecoratorOnDRFTests(TestCase):
    """The decorator must work on a real DRF APIView method (no 500)."""

    @classmethod
    def setUpTestData(cls):
        U = get_user_model()
        cls.user = U.objects.create(username='stepup@test.ao',
                                    email='stepup@test.ao')
        cls.user.set_password('CorrectHorse9')
        cls.user.save()

    def setUp(self):
        self.rf = APIRequestFactory()

    def _call(self, pw=None):
        headers = {'HTTP_X_CONFIRM_PASSWORD': pw} if pw else {}
        req = self.rf.post('/x', {}, format='json', **headers)
        force_authenticate(req, user=self.user)
        resp = _GuardedView.as_view()(req)
        return resp

    def test_missing_password_is_403_step_up(self):
        resp = self._call()
        self.assertEqual(resp.status_code, 403)
        self.assertIsInstance(resp, JsonResponse)
        self.assertEqual(json.loads(resp.content)['error'], 'step_up_required')

    def test_wrong_password_is_403_invalid(self):
        resp = self._call('nope')
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(json.loads(resp.content)['error'], 'invalid_password')

    def test_correct_password_proceeds(self):
        resp = self._call('CorrectHorse9')
        self.assertEqual(resp.status_code, 200)  # not 500
        self.assertTrue(resp.data['ok'])
