"""
Saga observability regression (Rollback & Recovery doc CH19-22).

The saga framework is MICHA's distributed-rollback engine: a multi-step money
flow (reserve stock -> charge -> create order) that UNWINDS on partial failure
by running each step's compensating action in reverse. Before this, the engine
emitted no metrics — so its worst failure mode, needs_attention (a compensation
that ITSELF failed: a charge left un-refunded or stock un-released), was
completely silent. These tests lock:

  - the outcome counter fires once per terminal transition (completed /
    compensated / needs_attention) and never double-counts on re-run;
  - the refresh task surfaces needs_attention as a gauge AND logs CRITICAL so
    on-call is paged (mirrors the outbox DLQ health task).
"""
from django.test import TestCase
from django.utils import timezone

from apps.sagas.registry import register, SagaDef, SagaStep
from apps.sagas.runner import start, run
from apps.sagas.models import Saga, SagaStatus
from apps.sagas.tasks import refresh_saga_metrics


# ── Test saga definitions (registered once at import) ────────────────
def _ok(payload, saga):
    payload.setdefault('did', []).append('forward')


def _comp_ok(payload, saga):
    payload.setdefault('comp', []).append('undone')


def _boom(payload, saga):
    raise RuntimeError('step blew up')


def _comp_boom(payload, saga):
    raise RuntimeError('compensation blew up too')


register(SagaDef(name='test_happy', steps=[
    SagaStep('s1', _ok, _comp_ok),
    SagaStep('s2', _ok, _comp_ok),
]))
register(SagaDef(name='test_compensated', steps=[
    SagaStep('s1', _ok, _comp_ok),   # completes, will be compensated cleanly
    SagaStep('s2', _boom, _comp_ok),  # fails -> triggers compensation
]))
register(SagaDef(name='test_needs_attention', steps=[
    SagaStep('s1', _ok, _comp_boom),  # completes; its compensation will fail
    SagaStep('s2', _boom, _comp_ok),  # fails -> compensate s1 -> blows up
]))


def _counter(outcome, name):
    from apps.telemetry.metrics import saga_terminal_total
    return saga_terminal_total.labels(name=name, outcome=outcome)._value.get()


class SagaOutcomeCounterTests(TestCase):
    def test_completed_saga_counts_once(self):
        before = _counter('completed', 'test_happy')
        s = start('test_happy', payload={})
        run(s.id)
        s.refresh_from_db()
        self.assertEqual(s.status, SagaStatus.COMPLETED)
        self.assertEqual(_counter('completed', 'test_happy'), before + 1)

    def test_terminal_counter_does_not_double_count_on_rerun(self):
        before = _counter('completed', 'test_happy')
        s = start('test_happy', payload={})
        run(s.id)
        run(s.id)   # second run hits the terminal-state early return
        run(s.id)
        self.assertEqual(_counter('completed', 'test_happy'), before + 1)

    def test_clean_compensation_counts_as_compensated(self):
        before = _counter('compensated', 'test_compensated')
        s = start('test_compensated', payload={})
        run(s.id)
        s.refresh_from_db()
        self.assertEqual(s.status, SagaStatus.FAILED)  # "compensated cleanly"
        self.assertEqual(_counter('compensated', 'test_compensated'), before + 1)

    def test_failed_compensation_counts_as_needs_attention(self):
        before = _counter('needs_attention', 'test_needs_attention')
        s = start('test_needs_attention', payload={})
        with self.assertLogs('sagas', level='ERROR') as cm:
            run(s.id)
        s.refresh_from_db()
        self.assertEqual(s.status, SagaStatus.NEEDS_ATTENTION)
        self.assertEqual(
            _counter('needs_attention', 'test_needs_attention'), before + 1)
        # The money-at-risk state is logged loudly for the alert pipeline.
        self.assertTrue(any('saga.needs_attention' in m for m in cm.output))


class SagaGaugeRefreshTests(TestCase):
    def test_refresh_surfaces_needs_attention_and_pages(self):
        Saga.objects.create(
            name='test_needs_attention', status=SagaStatus.NEEDS_ATTENTION,
            error='compensate(s1): boom',
        )
        # An open (non-terminal) saga should be counted separately.
        Saga.objects.create(name='test_happy', status=SagaStatus.RUNNING)

        with self.assertLogs('apps.sagas.tasks', level='CRITICAL') as cm:
            result = refresh_saga_metrics()

        self.assertEqual(result['needs_attention'], 1)
        self.assertEqual(result['open'], 1)
        self.assertTrue(
            any('needs_attention.CRITICAL' in m for m in cm.output))

        from apps.telemetry.metrics import saga_needs_attention, saga_open
        self.assertEqual(saga_needs_attention._value.get(), 1)
        self.assertEqual(saga_open._value.get(), 1)

    def test_refresh_clean_state_is_silent(self):
        # No needs_attention sagas -> gauge 0, no CRITICAL.
        result = refresh_saga_metrics()
        self.assertEqual(result['needs_attention'], 0)
        from apps.telemetry.metrics import saga_needs_attention
        self.assertEqual(saga_needs_attention._value.get(), 0)
