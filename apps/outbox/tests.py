"""
Outbox DLQ alerting tests.

Validates Sprint 1 commit 4: severity escalation on the DLQ-health
check + per-topic CRITICAL logging on DEAD transitions.

Why this matters
─────────────────
The outbox is the marketplace's "events happened" backbone — when
an order is placed, dispute resolved, refund processed, all
downstream effects (notifications, analytics, webhooks) fan out via
outbox handlers. If a handler reaches DEAD, that downstream effect
is silently lost FOREVER unless a human notices and requeues.

The original behaviour:
  • Any DEAD event → logger.error (ERROR severity, generic)
  • Periodic check → logger.warning if dead > 0 (regardless of magnitude)

Result: 1 dead event looks identical to 1000 dead events in the alert
channel. Money-correctness topics (refund.*, payout.*, dispute.*,
payment.*) get the same alert volume as "user changed profile photo".

The fix tested here:
  • DEAD transition on a critical-topic event → CRITICAL severity,
    paged on-call. Non-critical topics still ERROR.
  • Periodic check escalates to CRITICAL when:
      - dead >= OUTBOX_DLQ_CRITICAL_DEAD_COUNT (default 10)
      - OR oldest_dead_age > OUTBOX_DLQ_CRITICAL_OLDEST_AGE (default 1h)
      - OR stale_retrying >= OUTBOX_DLQ_CRITICAL_STALE_RETRYING (default 5)
"""
import logging

import pytest
from django.utils import timezone
from datetime import timedelta

from apps.outbox.models import OutboxEvent, EventStatus
from apps.outbox.tasks import refresh_dlq_metrics


@pytest.fixture(autouse=True)
def clean_outbox(db):
    """Fresh outbox table for each test."""
    OutboxEvent.objects.all().delete()


def _mk_event(topic='order.placed', status=EventStatus.DEAD,
              attempts=10, dead_for_seconds=0):
    """Build an outbox event in a known state. ``dead_for_seconds`` >0
    backdates updated_at so oldest_dead_age_seconds rises."""
    e = OutboxEvent.objects.create(
        topic=topic,
        payload={'test': True},
        dedupe_key=f'test:{topic}:{timezone.now().timestamp()}',
        status=status,
        attempts=attempts,
        max_attempts=10,
    )
    if dead_for_seconds:
        OutboxEvent.objects.filter(pk=e.pk).update(
            updated_at=timezone.now() - timedelta(seconds=dead_for_seconds),
        )
    return e


@pytest.mark.django_db
class TestDLQSeverityEscalation:
    """The periodic health check must escalate severity based on
    quantitative thresholds, not just "anything bad → WARNING"."""

    def test_clean_outbox_is_silent(self, caplog):
        """No DEAD events + no stale RETRYING → no warning/critical
        log emitted. Don't spam the alert channel during normal ops."""
        caplog.set_level(logging.INFO, logger='apps.outbox.tasks')

        result = refresh_dlq_metrics()

        assert result['severity'] == 'ok'
        # No WARNING / CRITICAL records about dlq_health
        bad_records = [
            r for r in caplog.records
            if r.levelno >= logging.WARNING
            and 'dlq_health' in (r.message or '')
        ]
        assert bad_records == [], (
            f'clean outbox emitted alert-level logs: {bad_records}'
        )

    def test_single_dead_event_warns_but_not_critical(self, caplog, settings):
        """One DEAD event → WARNING (operator should look at it
        eventually) but NOT CRITICAL (doesn't page on-call at 3am)."""
        settings.OUTBOX_DLQ_CRITICAL_DEAD_COUNT = 10
        caplog.set_level(logging.INFO, logger='apps.outbox.tasks')

        _mk_event(status=EventStatus.DEAD)

        result = refresh_dlq_metrics()
        assert result['severity'] == 'warning', result
        assert result['dead'] == 1

        crit = [r for r in caplog.records if r.levelno == logging.CRITICAL]
        warn = [
            r for r in caplog.records
            if r.levelno == logging.WARNING
            and 'dlq_health' in (r.message or '')
        ]
        assert not crit, 'single dead event should NOT page'
        assert warn, 'single dead event should at least warn'

    def test_many_dead_events_escalate_to_critical(self, caplog, settings):
        """When dead_count >= threshold (default 10), severity flips
        to CRITICAL — the level that pages on-call in the prod
        logging pipeline."""
        settings.OUTBOX_DLQ_CRITICAL_DEAD_COUNT = 5  # low for test speed
        caplog.set_level(logging.INFO, logger='apps.outbox.tasks')

        # Create exactly threshold-count dead events
        for i in range(5):
            _mk_event(topic=f'topic{i}', status=EventStatus.DEAD)

        result = refresh_dlq_metrics()
        assert result['severity'] == 'critical', result

        crit = [
            r for r in caplog.records
            if r.levelno == logging.CRITICAL
            and 'CRITICAL' in (r.message or '')
        ]
        assert crit, 'over-threshold DLQ should emit CRITICAL log'

    def test_old_dead_event_escalates_to_critical(self, caplog, settings):
        """Even a SINGLE event sitting DEAD for > critical_oldest_age
        escalates. Meaning: someone hasn't been watching the queue.
        That's worth paging."""
        settings.OUTBOX_DLQ_CRITICAL_DEAD_COUNT = 100  # high
        settings.OUTBOX_DLQ_CRITICAL_OLDEST_AGE = 60   # 60s for test

        caplog.set_level(logging.INFO, logger='apps.outbox.tasks')

        # One DEAD event, 2 hours old
        _mk_event(status=EventStatus.DEAD, dead_for_seconds=7200)

        result = refresh_dlq_metrics()
        assert result['severity'] == 'critical', result
        assert result['oldest_dead_age_seconds'] > 60

    def test_thresholds_in_summary_for_runbook_lookup(self):
        """The result dict must include the threshold values that were
        applied — so when an on-call engineer reads the alert, they
        can see WHICH threshold tripped without having to re-derive."""
        result = refresh_dlq_metrics()
        assert 'thresholds' in result
        assert 'critical_dead_count' in result['thresholds']
        assert 'critical_oldest_age_seconds' in result['thresholds']
        assert 'critical_stale_retrying_count' in result['thresholds']


@pytest.mark.django_db
class TestDeadTransitionLogging:
    """When an event transitions to DEAD, the dispatch_one() code
    must log with severity matching the topic's criticality.

    Critical topics: refund.*, payout.*, dispute.*, payment.*
    → logger.critical
    Other topics → logger.error (existing behaviour)
    """

    def test_refund_dead_logs_critical(self, caplog):
        """Refund topic going DEAD = money at risk = page on-call."""
        from apps.outbox.dispatcher import dispatch_one
        from apps.outbox.handlers import handler as register_handler

        # A handler that always raises so we trigger DEAD on max_attempts.
        @register_handler('refund.test_dead')
        def _broken(payload):
            raise RuntimeError('simulated handler failure')

        e = OutboxEvent.objects.create(
            topic='refund.test_dead',
            payload={'refund_id': 42, 'amount': '100.00'},
            dedupe_key=f'test:refund:{timezone.now().timestamp()}',
            status=EventStatus.PENDING,
            attempts=9,         # one more attempt → DEAD
            max_attempts=10,
        )

        caplog.set_level(logging.INFO, logger='outbox')
        dispatch_one(e)

        e.refresh_from_db()
        assert e.status == EventStatus.DEAD

        crit = [
            r for r in caplog.records
            if r.levelno == logging.CRITICAL
            and 'event_dead' in (r.message or '')
        ]
        assert crit, (
            'refund.* topic going DEAD should log at CRITICAL severity '
            '(routes to PagerDuty in prod)'
        )

    def test_non_critical_topic_dead_logs_error_not_critical(self, caplog):
        """A non-money-correctness topic (e.g. analytics, notification)
        going DEAD logs ERROR — bad, but not page-worthy at 3am."""
        from apps.outbox.dispatcher import dispatch_one
        from apps.outbox.handlers import handler as register_handler

        @register_handler('analytics.test_dead')
        def _broken(payload):
            raise RuntimeError('simulated handler failure')

        e = OutboxEvent.objects.create(
            topic='analytics.test_dead',
            payload={'event': 'test'},
            dedupe_key=f'test:analytics:{timezone.now().timestamp()}',
            status=EventStatus.PENDING,
            attempts=9,
            max_attempts=10,
        )

        caplog.set_level(logging.INFO, logger='outbox')
        dispatch_one(e)

        e.refresh_from_db()
        assert e.status == EventStatus.DEAD

        # ERROR yes, CRITICAL no
        errors = [
            r for r in caplog.records
            if r.levelno == logging.ERROR
            and 'event_dead' in (r.message or '')
        ]
        criticals = [
            r for r in caplog.records
            if r.levelno == logging.CRITICAL
            and 'event_dead' in (r.message or '')
        ]
        assert errors, 'non-critical-topic dead should log ERROR'
        assert not criticals, (
            f'non-critical-topic dead should NOT escalate to CRITICAL '
            f'(would create alert fatigue). Got: {criticals}'
        )

    def test_dead_log_includes_redacted_payload(self, caplog):
        """The DEAD log carries the payload (so on-call doesn't need
        to query DB) — but routed through the PII redactor first,
        so emails / tokens don't leak into alert channels."""
        from apps.outbox.dispatcher import dispatch_one
        from apps.outbox.handlers import handler as register_handler

        @register_handler('payment.test_dead_payload')
        def _broken(payload):
            raise RuntimeError('boom')

        e = OutboxEvent.objects.create(
            topic='payment.test_dead_payload',
            payload={
                'order_id': 'abc',
                'buyer_email': 'real-user@example.com',
                'api_key': 'sk_live_xxx',
            },
            dedupe_key=f'test:payment:{timezone.now().timestamp()}',
            status=EventStatus.PENDING,
            attempts=9,
            max_attempts=10,
        )

        caplog.set_level(logging.INFO, logger='outbox')
        dispatch_one(e)

        crit = [r for r in caplog.records if r.levelno == logging.CRITICAL]
        assert crit, 'expected CRITICAL log for payment topic'
        record = crit[0]

        # The payload extra should be scrubbed
        payload_in_log = getattr(record, 'payload', None)
        assert payload_in_log is not None
        # api_key was scrubbed
        assert payload_in_log.get('api_key') == '[REDACTED]', payload_in_log
        # email partially masked
        be = payload_in_log.get('buyer_email', '')
        assert 'real-user@example.com' not in be, (
            f'full email leaked into alert: {payload_in_log}'
        )
