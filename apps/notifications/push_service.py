"""
apps/notifications/push_service.py
───────────────────────────────────

Multi-device push dispatcher.

Pre-R5, ``apps/notifications/utils.py:send_push`` accepted one token
and called FCM. That couldn't service users with multiple devices.
This module fans out: given a user, find their active DeviceTokens,
send to each, handle FCM error responses to deactivate dead tokens.

Public API
──────────
  send_to_user(user, *, title, body, data=None) -> dict
      Synchronous multi-device send. Returns a summary
      {sent, failed, deactivated, skipped}. Safe to call from
      synchronous code (called by Notification.send()).

  send_to_token(token, *, title, body, data=None) -> dict
      Single-token send. Returned summary same shape. Existing
      callers using apps.notifications.utils.send_push can keep
      calling that — it now delegates here.

FCM error handling
──────────────────
firebase_admin raises subclasses of FirebaseError. The two we care
about for token lifecycle:

  UnregisteredError    → app was uninstalled OR token rotated.
                          Deactivate with reason='fcm_unregistered'.
  InvalidArgumentError → token is malformed (frontend bug or stale).
                          Deactivate with reason='fcm_invalid'.

All other exceptions (network timeout, FCM 5xx, etc.) are logged
but do NOT deactivate the token — those are transient and the next
send should retry.

Settings gate
──────────────
``PUSH_NOTIFICATIONS_ENABLED`` (default True) — master switch. When
False, send is a no-op returning {skipped: 1}. Lets ops turn off
push during a launch incident without code change.
"""
from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings

log = logging.getLogger('micha.push')


def _enabled() -> bool:
    return bool(getattr(settings, 'PUSH_NOTIFICATIONS_ENABLED', True))


def _firebase_credentials_path() -> str:
    return getattr(settings, 'FIREBASE_CREDENTIALS_PATH', '') or ''


# ─── FCM client (lazy + cached) ───────────────────────────────────────

_fcm_initialised = False


def _ensure_fcm():
    """Initialise the firebase_admin app once per process.

    Returns the messaging module on success, None if disabled or if
    initialisation failed (missing creds, missing package).
    """
    global _fcm_initialised
    if not _enabled():
        return None
    try:
        import firebase_admin
        from firebase_admin import credentials, messaging
    except ImportError:
        log.warning(
            'push: firebase-admin not installed; pushes will be no-op',
        )
        return None

    if firebase_admin._apps:
        return messaging

    cred_path = _firebase_credentials_path()
    if not cred_path:
        log.warning(
            'push: FIREBASE_CREDENTIALS_PATH not set; pushes will be no-op',
        )
        return None

    if not _fcm_initialised:
        try:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            _fcm_initialised = True
        except Exception:
            log.exception('push: firebase initialization failed')
            return None
    return messaging


# ─── Public API ───────────────────────────────────────────────────────

def send_to_user(user, *, title: str, body: str,
                 data: Optional[dict] = None) -> dict:
    """Send a push to every active DeviceToken belonging to ``user``.

    Returns a summary dict. Does NOT raise on per-token failures —
    one bad device shouldn't crash the notification path.
    """
    from .device_models import DeviceToken

    summary = {'sent': 0, 'failed': 0, 'deactivated': 0, 'skipped': 0}

    if user is None or not getattr(user, 'pk', None):
        summary['skipped'] = 1
        return summary

    # Honour the user-level preference if present (legacy flag).
    if hasattr(user, 'push_notifications') and not user.push_notifications:
        summary['skipped'] = 1
        return summary

    tokens = list(DeviceToken.objects.filter(user=user, is_active=True))

    # Back-compat: legacy ``User.fcm_token`` field. Migrate-on-read —
    # if the user has a legacy token but no DeviceToken row, treat the
    # legacy field as an Android registration so the user keeps
    # receiving pushes during the transition. Future logins will write
    # a proper DeviceToken via the register endpoint.
    if not tokens:
        legacy = getattr(user, 'fcm_token', None)
        if legacy:
            try:
                t, _ = DeviceToken.objects.get_or_create(
                    token=legacy,
                    defaults={'user': user, 'platform': 'android'},
                )
                if t.user_id != user.pk:
                    # Token now belongs to a different user; skip.
                    summary['skipped'] = 1
                    return summary
                tokens = [t]
            except Exception:
                log.warning('push: legacy fcm_token migration failed',
                            exc_info=True)

    if not tokens:
        summary['skipped'] = 1
        return summary

    for t in tokens:
        result = send_to_token(
            t.token, title=title, body=body, data=data,
            _token_obj=t,
        )
        summary['sent'] += result['sent']
        summary['failed'] += result['failed']
        summary['deactivated'] += result['deactivated']
        summary['skipped'] += result['skipped']

    return summary


def send_to_token(token: str, *, title: str, body: str,
                  data: Optional[dict] = None,
                  _token_obj=None) -> dict:
    """Single-token send. Returns the {sent, failed, deactivated,
    skipped} summary shape so callers can aggregate uniformly.

    If ``_token_obj`` (DeviceToken) is provided, FCM errors that
    indicate the token is dead deactivate it. Without _token_obj
    (raw-string callers), failures only log.
    """
    summary = {'sent': 0, 'failed': 0, 'deactivated': 0, 'skipped': 0}

    if not token:
        summary['skipped'] = 1
        return summary

    messaging = _ensure_fcm()
    if messaging is None:
        summary['skipped'] = 1
        return summary

    try:
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            token=token,
        )
        messaging.send(message)
        summary['sent'] = 1
        # Touch the token so prune jobs see it as live.
        if _token_obj is not None:
            try:
                _token_obj.touch()
            except Exception:
                log.debug('push: touch failed', exc_info=True)
        return summary

    except Exception as e:
        # Distinguish dead-token errors from transient. The FCM SDK
        # exposes typed errors (UnregisteredError, etc.) but exact
        # imports vary across firebase_admin versions; match by class
        # name string for robustness.
        err_name = type(e).__name__
        dead_token = err_name in (
            'UnregisteredError',
            'InvalidArgumentError',
            'SenderIdMismatchError',
        )
        log.warning(
            'push: send failed token=…%s err=%s',
            (token or '')[-8:], err_name,
            exc_info=True,
        )
        summary['failed'] = 1
        if dead_token and _token_obj is not None:
            reason = (
                'fcm_unregistered'
                if err_name == 'UnregisteredError'
                else 'fcm_invalid'
            )
            try:
                _token_obj.deactivate(reason=reason)
                summary['deactivated'] = 1
            except Exception:
                log.warning('push: deactivate failed', exc_info=True)
        return summary
