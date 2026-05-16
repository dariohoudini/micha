"""
apps/two_factor/decorators.py

@requires_2fa_recent(within_seconds=300) — drop on any view that performs
a high-risk action (creating an API key, issuing a payout, admin override
of a return, etc.). Refuses requests from users with 2FA enabled who
haven't proven a code recently.

The "recent" window comes from successful ChallengeAttempt rows. The
client is expected to perform a fresh challenge before the action (a
step-up auth flow). Users WITHOUT 2FA configured pass through unchanged —
this decorator escalates security for users who opted in, it doesn't
force 2FA on those who haven't.
"""
from __future__ import annotations
import functools
from datetime import timedelta

from django.utils import timezone
from rest_framework.response import Response

from .models import UserTOTP, ChallengeAttempt, ChallengeOutcome


def requires_2fa_recent(within_seconds: int = 300, *, purpose: str = ''):
    """Refuse the request unless the user has a successful 2FA challenge
    within the last ``within_seconds``.

    No-op for users without 2FA enabled. Pre-check is a single indexed
    query; cheap to apply broadly."""
    def decorator(view_method):
        @functools.wraps(view_method)
        def wrapper(self, request, *args, **kwargs):
            user = getattr(request, 'user', None)
            if user is None or not getattr(user, 'is_authenticated', False):
                return view_method(self, request, *args, **kwargs)

            # If 2FA isn't enabled, skip — opting-in users get the extra
            # check; opt-out users continue using single-factor.
            totp = UserTOTP.objects.filter(user=user).only('enabled_at').first()
            if totp is None or totp.enabled_at is None:
                return view_method(self, request, *args, **kwargs)

            cutoff = timezone.now() - timedelta(seconds=within_seconds)
            recent_ok = ChallengeAttempt.objects.filter(
                user=user, created_at__gte=cutoff,
                outcome__in=(ChallengeOutcome.SUCCESS, ChallengeOutcome.BACKUP_USED),
            ).exists()
            if not recent_ok:
                return Response({
                    'error': 'two_factor_required',
                    'detail': 'Recent 2FA verification required for this action.',
                    'window_seconds': within_seconds,
                    'purpose': purpose,
                }, status=403)
            return view_method(self, request, *args, **kwargs)
        return wrapper
    return decorator
