"""
middleware/celery_request_id.py

Propagates request_id end-to-end across the Celery boundary.

The problem: middleware.logging_middleware.RequestIDMiddleware stashes a
request_id in threadlocal storage so every log line carries it. When the
request handler dispatches a Celery task (e.g. order.send_confirmation_email),
the task runs in a DIFFERENT process — the threadlocal is gone, and every
log line from that task shows ``request_id=-``. Tracing breaks at the
async boundary.

The fix, with no call-site changes:

  1. ``before_task_publish`` signal — when ANY task is enqueued, read the
     current threadlocal request_id and attach it as a custom task header.
  2. ``task_prerun`` signal — when the worker picks up the task, read the
     header, push it into the worker's threadlocal storage, and attach it
     to the task instance for log adapters.
  3. ``task_postrun`` signal — clear the threadlocal afterwards so a
     subsequent task on the same worker doesn't inherit the previous
     task's request_id.

After this is wired:

  • A buyer's POST /checkout/ with X-Request-ID=abc123 triggers
    order.send_confirmation_email.delay()
  • The Celery task runs ~5 seconds later in a worker process
  • Every log line from that task shows request_id=abc123
  • Operators can grep one ID across web + worker logs

Wired in config/celery.py — calling install_celery_request_id_propagation()
registers the signal handlers exactly once at app startup.
"""
import logging

from celery.signals import before_task_publish, task_prerun, task_postrun

from middleware.logging_middleware import _local, get_request_id

log = logging.getLogger(__name__)

HEADER_KEY = 'X-Request-ID'


@before_task_publish.connect(weak=False)
def _attach_request_id(sender=None, headers=None, **kwargs):
    """When a task is about to be queued, stamp the current request_id
    into its headers. Safe to call when no request_id exists (default '-').
    Never raises — propagation failure must not break task dispatch."""
    try:
        rid = get_request_id()
        if rid and rid != '-':
            if headers is None:
                return
            headers[HEADER_KEY] = rid
    except Exception:
        # Never break .delay() over a logging-correlation hiccup.
        log.debug('attach_request_id failed', exc_info=True)


@task_prerun.connect(weak=False)
def _adopt_request_id(sender=None, task_id=None, task=None, **kwargs):
    """Worker is about to run a task — set the request_id from headers
    into threadlocal storage so log records carry it."""
    try:
        rid = ''
        # Celery 5: request.headers; older versions vary
        req = getattr(task, 'request', None)
        if req is not None:
            headers = getattr(req, 'headers', None) or {}
            rid = headers.get(HEADER_KEY) or ''
        _local.request_id = rid or f'task:{(task_id or "?")[:8]}'
    except Exception:
        _local.request_id = '-'


@task_postrun.connect(weak=False)
def _clear_request_id(sender=None, task_id=None, task=None, **kwargs):
    """Reset threadlocal so the next task on this worker thread doesn't
    inherit our request_id (workers reuse threads)."""
    try:
        _local.request_id = '-'
    except Exception:
        pass


def install_celery_request_id_propagation():
    """No-op marker — importing this module is what activates the signal
    handlers. Call this from config/celery.py for explicit intent."""
    return True
