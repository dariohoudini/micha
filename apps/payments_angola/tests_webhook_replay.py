"""CH33 webhook security: HMAC + receive-time replay protection + retry-safety."""
import hashlib
import hmac
import json
import uuid

from django.conf import settings
from django.test import RequestFactory, TestCase

from apps.payments_angola.models import ProcessedWebhookEvent
from apps.payments_angola.views import AppypayWebhookView


def _sign(body: bytes) -> str:
    secret = (getattr(settings, 'APPYPAY_WEBHOOK_SECRET', '') or 'dev-secret')
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _call(payload, *, sig=None):
    body = json.dumps(payload).encode()
    rf = RequestFactory()
    req = rf.post('/api/v1/payments-ao/webhook', data=body,
                  content_type='application/json',
                  HTTP_X_APPYPAY_SIGNATURE=sig if sig is not None else _sign(body))
    return AppypayWebhookView.as_view()(req)


class WebhookSecurityTests(TestCase):
    def test_bad_signature_rejected_with_canonical_code(self):
        r = _call({'merchant_order_id': str(uuid.uuid4()), 'status': 'PAID',
                   'amount': 100}, sig='deadbeef')
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.data['error'], 'webhook_signature_invalid')

    def test_replay_is_noop(self):
        payload = {'merchant_order_id': str(uuid.uuid4()), 'amount': 1000,
                   'status': 'FAILED', 'psp_reference': 'PSP-1',
                   'event_id': 'evt_replay_1'}
        r1 = _call(payload)
        r2 = _call(payload)
        r3 = _call(payload)
        self.assertIsNone(r1.data.get('replay'))     # first processes
        self.assertTrue(r2.data.get('replay'))        # replays no-op
        self.assertTrue(r3.data.get('replay'))
        self.assertEqual(
            ProcessedWebhookEvent.objects.filter(
                event_key='appypay:evt_replay_1').count(), 1)

    def test_failure_releases_claim_so_retry_reprocesses(self):
        # 'NOT-A-UUID' makes the service raise -> 500; the dedupe receipt
        # must be released so a genuine PSP retry can re-process (CH5.1).
        bad = {'merchant_order_id': 'NOT-A-UUID', 'amount': 1000,
               'status': 'FAILED', 'event_id': 'evt_fail_1'}
        before = ProcessedWebhookEvent.objects.count()
        r1 = _call(bad)
        self.assertGreaterEqual(r1.status_code, 500)
        self.assertEqual(ProcessedWebhookEvent.objects.count(), before)
        # retry must attempt again, not be silently deduped
        r2 = _call(bad)
        self.assertGreaterEqual(r2.status_code, 500)
        self.assertIsNone(r2.data.get('replay'))
