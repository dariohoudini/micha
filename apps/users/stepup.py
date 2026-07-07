"""
Gap-Coverage CH16/CH17 — windowed step-up for money-out.

The #1 money gap: payout + bank-change must require a FRESH SECOND
FACTOR, so a stolen session or password alone can never move funds. A
successful TOTP verification writes a short, single-purpose Redis/cache
window; the money-out endpoints require a live window (or a fresh TOTP
on the request itself). Password/session alone NEVER suffices.

Product decision (the strongest posture the doc recommends): money-out
REQUIRES an enrolled second factor. A seller without 2FA is asked to
enrol before withdrawing — the account's own money is protected.
"""
import logging

from django.core.cache import cache

log = logging.getLogger('micha.security')

WINDOW_SECONDS = 300          # 5-minute one-time proof (doc CH17)
_KEY = 'stepup:{scope}:{uid}'


def _key(user_id, scope):
    return _KEY.format(scope=scope, uid=user_id)


def verify_totp(user, code):
    """Verify a TOTP code against the user's enrolled secret. Returns
    bool; never raises."""
    if not (user and getattr(user, 'two_fa_enabled', False)
            and getattr(user, 'two_fa_secret', '')):
        return False
    try:
        import pyotp
        return bool(pyotp.TOTP(user.two_fa_secret).verify(str(code).strip(),
                                                          valid_window=1))
    except Exception:
        return False


def grant_stepup(user_id, scope='money_out'):
    """Open a short step-up window after a verified second factor."""
    try:
        cache.set(_key(user_id, scope), 1, WINDOW_SECONDS)
    except Exception:
        log.debug('step-up window set failed', exc_info=True)


def has_stepup(user_id, scope='money_out'):
    try:
        return bool(cache.get(_key(user_id, scope)))
    except Exception:
        return False


def consume_stepup(user_id, scope='money_out'):
    """One-time: clear the window after it authorises an action."""
    try:
        cache.delete(_key(user_id, scope))
    except Exception:
        pass


def check_money_out_stepup(request, scope='money_out'):
    """Gate a money-out action. Returns (ok, error_response_dict, status).

    Accepts EITHER a live step-up window OR a fresh X-TOTP-Code on this
    request. Requires 2FA to be enrolled — money-out demands a second
    factor, so an unenrolled user is told to enable it first (never
    allowed through on session alone). On success the window is consumed
    (single-use)."""
    user = request.user
    if not getattr(user, 'two_fa_enabled', False):
        return (False,
                {'error': 'mfa_required_for_payout',
                 'detail': 'Active a verificação em duas etapas (2FA) para '
                           'poder levantar fundos. É a proteção do seu '
                           'próprio dinheiro.'},
                403)

    # Fresh code on the request itself also authorises (and refreshes the
    # window for the rest of a multi-step flow).
    code = request.META.get('HTTP_X_TOTP_CODE', '').strip()
    if code:
        if verify_totp(user, code):
            grant_stepup(user.id, scope)
        else:
            from middleware.security import log_security_event
            log_security_event('money_out_2fa_failed', request=request,
                               severity='CRITICAL',
                               details={'user_id': user.id, 'scope': scope})
            return (False,
                    {'error': 'invalid_2fa', 'detail': 'Código 2FA inválido.'},
                    403)

    if has_stepup(user.id, scope):
        consume_stepup(user.id, scope)
        return (True, None, 200)

    return (False,
            {'error': 'stepup_required',
             'detail': 'Confirme com o seu código 2FA para continuar.'},
            403)
