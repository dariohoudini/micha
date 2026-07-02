"""CH33 + Gap-Coverage CH4 webhook security: the single APPYPAY ingress.

AppypayWebhookView is decorated with @verified_webhook — signature
verification, body-hash replay protection, inbox persistence, and the
forensic audit row live in the shared pipeline; the view only dispatches.
These tests lock the consolidation: forgery rejected with the canonical
code, redelivery cannot double-apply (both dedup layers), and a failed
attempt is retryable (crash + retry is safe), never wedged on a cached 500.
"""
import hashlib
import hmac
import json
import uuid

from django.test import RequestFactory, TestCase, override_settings

from apps.inbound_webhooks.models import InboundWebhookEvent, WebhookStatus
from apps.payments_angola.models import ProcessedWebhookEvent
from apps.payments_angola.views import AppypayWebhookView

# The verifier fails CLOSED without a configured secret (the test runner
# forces DEBUG=False, so the dev-secret fallback is correctly absent here).
# Tests configure an explicit secret — same as production must.
TEST_SECRET = 'test-webhook-secret'


def _sign(body: bytes) -> str:
    return hmac.new(TEST_SECRET.encode(), body, hashlib.sha256).hexdigest()


def _call(payload, *, sig=None):
    body = json.dumps(payload).encode()
    rf = RequestFactory()
    req = rf.post('/api/v1/payments-ao/webhooks/appypay/', data=body,
                  content_type='application/json',
                  HTTP_X_APPYPAY_SIGNATURE=sig if sig is not None else _sign(body))
    return AppypayWebhookView.as_view()(req)


def _body(response):
    """Responses may be DRF Response (fresh) or HttpResponse (replayed /
    rejected by the pipeline) — read the rendered JSON uniformly."""
    if hasattr(response, 'render') and callable(response.render):
        try:
            response.render()
        except Exception:
            pass
    return json.loads(response.content.decode('utf-8') or '{}')


@override_settings(APPYPAY_WEBHOOK_SECRET=TEST_SECRET)
class WebhookSecurityTests(TestCase):
    def test_bad_signature_rejected_with_canonical_code(self):
        r = _call({'merchant_order_id': str(uuid.uuid4()), 'status': 'PAID',
                   'amount': 100}, sig='deadbeef')
        self.assertEqual(r.status_code, 401)
        self.assertEqual(_body(r)['error'], 'webhook_signature_invalid')
        # Forensic row records the rejection.
        self.assertTrue(InboundWebhookEvent.objects.filter(
            provider='appypay',
            status=WebhookStatus.SIGNATURE_INVALID).exists())

    def test_missing_signature_same_canonical_code(self):
        # The response must not reveal WHY verification failed (missing vs
        # wrong vs stale) — one vague canonical code for all of them.
        r = _call({'merchant_order_id': str(uuid.uuid4()), 'status': 'PAID',
                   'amount': 100}, sig='')
        self.assertEqual(r.status_code, 401)
        self.assertEqual(_body(r)['error'], 'webhook_signature_invalid')

    def test_identical_redelivery_is_replay_safe(self):
        # Layer 1 (pipeline): byte-identical redelivery returns the cached
        # response without re-executing the handler.
        payload = {'merchant_order_id': str(uuid.uuid4()), 'amount': 1000,
                   'status': 'FAILED', 'psp_reference': 'PSP-1',
                   'event_id': 'evt_replay_1'}
        r1 = _call(payload)
        r2 = _call(payload)
        r3 = _call(payload)
        self.assertEqual(r1.status_code, 200)
        self.assertTrue(_body(r1)['received'])
        # Replays serve the original outcome verbatim.
        self.assertEqual(_body(r2), _body(r1))
        self.assertEqual(_body(r3), _body(r1))
        # Handler effect happened exactly once.
        self.assertEqual(
            ProcessedWebhookEvent.objects.filter(
                event_key='appypay:evt_replay_1').count(), 1)
        # And only one inbox row exists for the body.
        self.assertEqual(InboundWebhookEvent.objects.filter(
            provider='appypay', status=WebhookStatus.PROCESSED).count(), 1)

    def test_resend_with_different_body_hits_event_key_claim(self):
        # Layer 2 (dispatch): the provider re-sends the SAME event with a
        # slightly different body (e.g. fresh internal timestamp) — the
        # body-hash layer misses, the event-key claim catches it.
        base = {'merchant_order_id': str(uuid.uuid4()), 'amount': 1000,
                'status': 'FAILED', 'psp_reference': 'PSP-2',
                'event_id': 'evt_replay_2'}
        r1 = _call(base)
        self.assertEqual(r1.status_code, 200)
        resend = dict(base, provider_ts='2026-07-02T12:00:00Z')
        r2 = _call(resend)
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(_body(r2).get('replay'))
        self.assertEqual(
            ProcessedWebhookEvent.objects.filter(
                event_key='appypay:evt_replay_2').count(), 1)

    def test_failure_is_retryable_not_wedged(self):
        # 'NOT-A-UUID' makes the service raise → the view releases its
        # event-key claim and the pipeline records HANDLER_FAILED (500).
        # A retry with the identical body must RE-RUN the handler — not
        # be served the cached 500 forever (Gap-Coverage CH4: crash +
        # retry is safe).
        bad = {'merchant_order_id': 'NOT-A-UUID', 'amount': 1000,
               'status': 'FAILED', 'event_id': 'evt_fail_1'}
        before = ProcessedWebhookEvent.objects.count()
        r1 = _call(bad)
        self.assertEqual(r1.status_code, 500)
        self.assertEqual(_body(r1)['error'], 'handler_failed')
        self.assertEqual(ProcessedWebhookEvent.objects.count(), before)
        # Retry re-attempts (fails again here, but is NOT a cached replay
        # and NOT silently deduped).
        r2 = _call(bad)
        self.assertEqual(r2.status_code, 500)
        self.assertEqual(ProcessedWebhookEvent.objects.count(), before)
        # The forensic row was reused for the retry, not duplicated.
        self.assertEqual(InboundWebhookEvent.objects.filter(
            provider='appypay',
            status=WebhookStatus.HANDLER_FAILED).count(), 1)
