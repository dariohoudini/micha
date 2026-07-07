"""
Admin User Management doc CH17 — impersonation / view-as.

The operator sees the platform AS the user for support ("what do they
see?"). The most powerful non-destructive action, so the most
controlled: a specific permission, TIME-BOXED, view-as-by-default, with
the dangerous actions (money-out, security changes) BLOCKED even under
impersonation, and recorded on BOTH sides so every act is attributable
to the REAL human behind it.

The token is a normal user access token for the target, stamped with
``imp`` + ``imp_by`` (the real operator) claims and a short lifetime.
The client shows a persistent banner and can exit at any time.
"""
from datetime import timedelta

from rest_framework_simplejwt.tokens import AccessToken

IMPERSONATION_MINUTES = 15


def issue_impersonation_token(target_user, operator):
    """Mint a short, claim-stamped access token to act AS target_user."""
    token = AccessToken.for_user(target_user)
    token['imp'] = True
    token['imp_by'] = operator.id
    token['imp_by_email'] = operator.email
    token.set_exp(lifetime=timedelta(minutes=IMPERSONATION_MINUTES))
    return str(token)


def impersonator_id(request):
    """The real operator id behind an impersonated request, or None."""
    auth = getattr(request, 'auth', None)
    if auth is None:
        return None
    try:
        if auth.get('imp'):
            return auth.get('imp_by')
    except (AttributeError, TypeError):
        return None
    return None


def is_impersonated(request):
    return impersonator_id(request) is not None
