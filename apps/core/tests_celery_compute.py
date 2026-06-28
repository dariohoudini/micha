"""
Celery worker resource-safety regression (Cloud & Compute doc Part 1 CH8/CH11).

Locks the worker-tier reliability + resource-safety contract so it can't
silently regress:
  * acks_late + reject_on_worker_lost  — a crashed worker re-delivers its
    task (no lost work); requires idempotent tasks (which MICHA's are).
  * prefetch_multiplier == 1           — fair distribution; one worker can't
    hoard tasks behind a long-running one.
  * task_time_limit / soft_time_limit  — a wedged task cannot occupy a
    prefork child forever (soft fires before hard so the task can clean up).
  * worker_max_tasks_per_child / max_memory_per_child — bound memory leaks
    over long uptime (recycle a child between tasks).
"""
from django.test import SimpleTestCase

from config.celery import app


class CeleryWorkerSafetyTests(SimpleTestCase):
    @property
    def conf(self):
        return app.conf

    def test_acks_late_with_reject_on_worker_lost(self):
        # At-least-once delivery for crash safety (CH11). Both required:
        # acks_late alone won't re-queue a task whose worker was lost.
        self.assertTrue(self.conf.task_acks_late)
        self.assertTrue(self.conf.task_reject_on_worker_lost)

    def test_prefetch_multiplier_is_one(self):
        self.assertEqual(self.conf.worker_prefetch_multiplier, 1)

    def test_time_limits_present_and_ordered(self):
        soft = self.conf.task_soft_time_limit
        hard = self.conf.task_time_limit
        self.assertIsNotNone(soft, 'soft time limit must be set (CH11)')
        self.assertIsNotNone(hard, 'hard time limit must be set (CH11)')
        # Soft must fire strictly before hard so the task gets a chance to
        # clean up / record failure before the child is force-killed.
        self.assertLess(soft, hard)

    def test_memory_recycling_guards(self):
        self.assertGreater(self.conf.worker_max_tasks_per_child, 0)
        self.assertGreater(self.conf.worker_max_memory_per_child, 0)

    def test_queue_isolation_defined(self):
        # Critical money paths must not share a queue with bulk/media work.
        queues = set(self.conf.task_queues or [])
        # task_queues may be a list of Queue objects; normalise to names.
        names = {getattr(q, 'name', q) for q in (self.conf.task_queues or [])}
        self.assertIn('high', names)
        self.assertIn('default', names)
