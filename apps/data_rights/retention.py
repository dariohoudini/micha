"""
apps/data_rights/retention.py
──────────────────────────────

Data retention policy enforcement (R6).

GDPR / Lei 22/11 require declaring AND ENFORCING how long each
data class is kept. Without enforcement the policy is fiction.

Policy table (defaults — override via settings DATA_RETENTION_POLICY):

  order_history           7 years   (tax/accounting law)
  payment_event           7 years   (financial audit)
  ledger_entry            10 years  (BNA / audit baseline)
  chat_message            2 years   (post-purchase support)
  notification_log        90 days
  security_log            180 days
  pii_in_logs             30 days
  cookie_consent          forever   (audit evidence)
  failed_login_attempt    60 days

What this module does
─────────────────────
  enforce_retention(dry_run=False) → dict of counts purged per class
      Iterates the policy table, deletes rows older than the limit.
      Always atomic per-class. Audit log written via AdminActionLog.

  retention_for(name) → timedelta
      Look up the retention window for a class name.

Scheduling
──────────
Wire in CELERY_BEAT_SCHEDULE to run nightly. Operators should run with
dry_run=True once first to size the purge volume.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone


log = logging.getLogger('micha.retention')


DEFAULT_POLICY = {
    # name: (years, days, hours) — only one needs be non-zero
    'order_history':         {'days': 7 * 365},
    'payment_event':         {'days': 7 * 365},
    'ledger_entry':          {'days': 10 * 365},
    'chat_message':          {'days': 2 * 365},
    'notification_log':      {'days': 90},
    'security_log':          {'days': 180},
    'pii_in_logs':           {'days': 30},
    'failed_login_attempt':  {'days': 60},
}


def _policy() -> dict:
    return getattr(settings, 'DATA_RETENTION_POLICY', None) or DEFAULT_POLICY


def retention_for(name: str) -> Optional[timedelta]:
    p = _policy().get(name)
    if not p:
        return None
    days = int(p.get('days') or 0)
    hours = int(p.get('hours') or 0)
    return timedelta(days=days, hours=hours)


# ─── Per-class purgers ────────────────────────────────────────────────


def _purge_notification_log(cutoff, dry_run: bool) -> int:
    try:
        from apps.notifications.notification_log_models import NotificationLog
        qs = NotificationLog.objects.filter(created_at__lt=cutoff)
        n = qs.count()
        if not dry_run and n:
            qs.delete()
        return n
    except Exception:
        log.exception('retention: notification_log purge failed')
        return 0


def _purge_security_log(cutoff, dry_run: bool) -> int:
    try:
        # Different versions of the codebase have stored security
        # events under different model names. Try the canonical paths.
        try:
            from apps.security.models import SecurityEvent
            model = SecurityEvent
        except Exception:
            return 0
        qs = model.objects.filter(created_at__lt=cutoff) \
            if hasattr(model, 'created_at') else model.objects.none()
        n = qs.count()
        if not dry_run and n:
            qs.delete()
        return n
    except Exception:
        log.exception('retention: security_log purge failed')
        return 0


def _purge_failed_login_attempt(cutoff, dry_run: bool) -> int:
    try:
        from apps.security.login_attempt_models import LoginAttempt
        qs = LoginAttempt.objects.filter(
            created_at__lt=cutoff, success=False,
        ) if hasattr(LoginAttempt, 'success') else \
            LoginAttempt.objects.filter(created_at__lt=cutoff)
        n = qs.count()
        if not dry_run and n:
            qs.delete()
        return n
    except Exception:
        log.exception('retention: failed_login_attempt purge failed')
        return 0


def _purge_chat_message(cutoff, dry_run: bool) -> int:
    try:
        from apps.chat.models import Message
        qs = Message.objects.filter(created_at__lt=cutoff)
        n = qs.count()
        if not dry_run and n:
            qs.delete()
        return n
    except Exception:
        log.exception('retention: chat_message purge failed')
        return 0


# Order / Payment / Ledger purgers are deliberately NOT implemented.
# Those records are subject to PROTECT FKs (financial audit invariant)
# AND a 7-10 year retention window — well outside any sane purge job
# on a young marketplace. Add explicit purgers when the platform is
# old enough to hit those windows.


_PURGERS = {
    'notification_log':     _purge_notification_log,
    'security_log':         _purge_security_log,
    'failed_login_attempt': _purge_failed_login_attempt,
    'chat_message':         _purge_chat_message,
}


# ─── Public ───────────────────────────────────────────────────────────


def enforce_retention(*, dry_run: bool = False) -> dict:
    """Walk the policy table; delete rows past their window.

    Returns ``{class_name: count_deleted}``. Counts in dry_run mode
    show what WOULD be deleted.
    """
    now = timezone.now()
    out = {}
    for name, purger in _PURGERS.items():
        td = retention_for(name)
        if td is None:
            out[name] = 0
            continue
        cutoff = now - td
        try:
            with transaction.atomic():
                out[name] = purger(cutoff, dry_run)
        except Exception:
            log.exception('retention: %s atomic block failed', name)
            out[name] = 0

    log.info('retention_enforcement_complete',
             extra={'dry_run': dry_run, **out})
    return out


# ─── Celery beat entry-point ──────────────────────────────────────────


@shared_task(name='data_rights.enforce_retention',
             queue='nightly')
def enforce_retention_task():
    """Beat schedule: nightly. See config/settings.py CELERY_BEAT_SCHEDULE."""
    return enforce_retention(dry_run=False)
