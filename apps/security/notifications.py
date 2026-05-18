"""
apps/security/notifications.py

Email a user when their account is locked. This is incident response,
not security theater — the user is the only person who can decide:
  • "that was me, I forgot my password" → password reset
  • "that wasn't me" → change password immediately + check sessions

Without this notification, the user only discovers the lockout when
their next legitimate login fails, by which time the attacker has
moved on and there's nothing actionable to do.

Dedupe is enforced at the call site via lockout.should_send_lockout_notification
so a burst of failed attempts produces at most one email per hour.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone


log = logging.getLogger(__name__)


def send_account_locked_email(*, user, ip: str, attempt_count: int,
                              lockout_duration_s: int) -> None:
    """Best-effort — failures are logged but don't propagate."""
    if user is None or not user.email:
        return

    minutes = max(1, lockout_duration_s // 60)
    unlock_at = timezone.now() + timedelta(seconds=lockout_duration_s)

    frontend = getattr(settings, 'FRONTEND_URL', 'https://micha.app')
    reset_url = f'{frontend}/auth/forgot-password'
    sessions_url = f'{frontend}/account/security'

    masked_ip = _mask_ip(ip) if ip else 'unknown'

    body = (
        f'Hi,\n\n'
        f'We detected {attempt_count} failed login attempts on your MICHA '
        f'account, the latest from IP {masked_ip}.\n\n'
        f'To protect your account, we have temporarily locked it. '
        f'The lock will automatically lift in about {minutes} minutes '
        f'(at {unlock_at.strftime("%Y-%m-%d %H:%M UTC")}).\n\n'
        f'WHAT TO DO\n'
        f'  • If this was you (you forgot your password), reset it now '
        f'and the lock will be cleared:\n'
        f'    {reset_url}\n\n'
        f'  • If this was NOT you, someone is trying to access your '
        f'account. We strongly recommend:\n'
        f'    1. Change your password immediately via the link above.\n'
        f'    2. Review your active sessions and revoke any you do not '
        f'recognise:\n'
        f'       {sessions_url}\n'
        f'    3. Enable two-factor authentication if you have not already.\n\n'
        f'You do not need to do anything if you are simply waiting for '
        f'the lock to expire — but we recommend changing your password '
        f'either way.\n\n'
        f'— MICHA Security\n'
    )

    try:
        send_mail(
            subject='Security alert: your MICHA account is temporarily locked',
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )
        log.info('lockout notification sent to user_id=%s', user.id)
    except Exception:
        log.exception('lockout: failed to send notification')


def _mask_ip(ip: str) -> str:
    """Mask the final octet of an IPv4 address (or last segment of IPv6)
    so the email — which may be readable on the user's phone notification
    preview — doesn't leak the attacker's full IP. Forensics still have
    the full IP in the LoginAttempt row.
    """
    if not ip:
        return ''
    if '.' in ip:
        parts = ip.split('.')
        if len(parts) == 4:
            return '.'.join(parts[:3] + ['xxx'])
    if ':' in ip:
        parts = ip.split(':')
        return ':'.join(parts[:-1] + ['xxxx'])
    return ip
