"""
apps/two_factor/service.py

Public entrypoints. All paths log a ChallengeAttempt row so an
investigator can reconstruct any account's 2FA history.

  start_setup(user) -> dict
    Creates / replaces the pending UserTOTP row, returns
    {secret, otpauth_uri} for the QR code. NOT yet enabled — user must
    verify a code first.

  confirm_setup(user, code) -> dict
    Verifies the user's first code against the pending secret. On success:
    stamps enabled_at, issues backup codes, returns
    {backup_codes: [...]} — ONE-TIME REVEAL.

  challenge(user, code, *, purpose, ip, ua) -> tuple[bool, str]
    The verify path. Tries TOTP first, then backup codes, then trusted-
    device token (if supplied separately). Returns (ok, outcome).

  trust_device(user, name, ip, ua, days=30) -> str
    Issues a device token (plaintext returned ONCE for setting as cookie).
    Caller stores hash + metadata.

  is_device_trusted(user, token) -> bool
    Constant-time lookup of an active trusted-device cookie.

  disable(user, *, actor) -> None
    Removes TOTP + backup codes + trusted devices in one call.
    Triggered from the account-recovery flow.

Rate-limiting:
  After MAX_FAILED_ATTEMPTS bad codes in a row the user is locked for
  LOCKOUT_MINUTES. A successful TOTP or backup-code use resets the
  counter. Lockout is at the per-user level (DB row); not per-IP.
"""
from __future__ import annotations
import hashlib
import logging
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import (
    UserTOTP, BackupCode, TrustedDevice, ChallengeAttempt, ChallengeOutcome,
)
from .totp import generate_secret, verify_totp, provisioning_uri

log = logging.getLogger(__name__)


MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 10
BACKUP_CODE_COUNT = 10
TRUSTED_DEVICE_DEFAULT_DAYS = 30


class TwoFactorError(Exception):
    pass


class LockedOut(TwoFactorError):
    pass


# ─── Setup flow ────────────────────────────────────────────────────────────

def start_setup(user, *, issuer: str = 'MICHA') -> dict:
    """Begin 2FA setup. Creates a PENDING UserTOTP row with a fresh secret
    and returns the secret + otpauth URI. Re-running this for an already-
    enabled user is refused — they must call disable() first."""
    existing = UserTOTP.objects.filter(user=user).first()
    if existing and existing.is_enabled:
        raise TwoFactorError('2FA already enabled — disable first to re-enrol')

    secret = generate_secret()
    if existing:
        existing.secret = secret
        existing.enabled_at = None
        existing.failed_attempts = 0
        existing.locked_until = None
        existing.save(update_fields=['secret', 'enabled_at',
                                       'failed_attempts', 'locked_until',
                                       'updated_at'])
    else:
        UserTOTP.objects.create(user=user, secret=secret)

    uri = provisioning_uri(secret, account=user.email or f'user-{user.id}',
                            issuer=issuer)
    return {'secret': secret, 'otpauth_uri': uri}


def confirm_setup(user, code: str, *, ip: str = '', ua: str = '') -> dict:
    """Verify the user's first code against the pending secret. On success:
    stamp enabled_at, issue backup codes, return the plaintext codes ONCE."""
    row = UserTOTP.objects.filter(user=user).first()
    if row is None:
        raise TwoFactorError('no setup in progress — call start_setup first')
    if row.is_enabled:
        raise TwoFactorError('already enabled')

    if not verify_totp(str(row.secret), code):
        _log_attempt(user, ChallengeOutcome.BAD_CODE, ip=ip, ua=ua,
                     purpose='setup')
        raise TwoFactorError('invalid code')

    with transaction.atomic():
        row.enabled_at = timezone.now()
        row.failed_attempts = 0
        row.locked_until = None
        row.save(update_fields=['enabled_at', 'failed_attempts',
                                  'locked_until', 'updated_at'])

        # Mirror onto the legacy User.two_fa_enabled for backward compat
        try:
            from django.contrib.auth import get_user_model
            U = get_user_model()
            U.objects.filter(pk=user.pk).update(two_fa_enabled=True)
        except Exception:
            pass

        codes = _issue_backup_codes(user)

    _log_attempt(user, ChallengeOutcome.SUCCESS, ip=ip, ua=ua, purpose='setup')
    return {'backup_codes': codes, 'enabled_at': row.enabled_at}


# ─── Challenge / verify ────────────────────────────────────────────────────

def challenge(user, code: str, *, purpose: str = 'login',
              ip: str = '', ua: str = '') -> tuple[bool, str]:
    """Verify a user-supplied code. Returns (ok, outcome) where outcome
    is one of ChallengeOutcome. Raises LockedOut if the user is currently
    locked from too many failed attempts."""
    row = UserTOTP.objects.filter(user=user).first()
    if row is None or not row.is_enabled:
        # 2FA not set up — nothing to challenge against
        return False, 'not_enabled'

    now = timezone.now()
    if row.locked_until and row.locked_until > now:
        _log_attempt(user, ChallengeOutcome.LOCKED, ip=ip, ua=ua, purpose=purpose)
        raise LockedOut(f'locked until {row.locked_until.isoformat()}')

    code = (code or '').strip()

    # Try TOTP first (6 digits)
    if len(code) == 6 and code.isdigit():
        if verify_totp(str(row.secret), code):
            _on_success(row, ip=ip, ua=ua, purpose=purpose,
                        outcome=ChallengeOutcome.SUCCESS)
            return True, ChallengeOutcome.SUCCESS

    # Try backup code (8 alphanumeric)
    if len(code) == 8 and code.isalnum():
        normalised = code.upper()
        h = BackupCode.hash_code(normalised)
        bc = BackupCode.objects.filter(user=user, code_hash=h, used_at__isnull=True).first()
        if bc is not None:
            with transaction.atomic():
                BackupCode.objects.filter(pk=bc.pk, used_at__isnull=True).update(
                    used_at=timezone.now(),
                )
                _on_success(row, ip=ip, ua=ua, purpose=purpose,
                            outcome=ChallengeOutcome.BACKUP_USED)
            return True, ChallengeOutcome.BACKUP_USED

    # Failure: bump counter, maybe lock
    _on_failure(row, ip=ip, ua=ua, purpose=purpose)
    return False, ChallengeOutcome.BAD_CODE


def _on_success(row: UserTOTP, *, ip, ua, purpose, outcome):
    row.failed_attempts = 0
    row.locked_until = None
    row.last_used_at = timezone.now()
    row.save(update_fields=['failed_attempts', 'locked_until',
                              'last_used_at', 'updated_at'])
    _log_attempt(row.user, outcome, ip=ip, ua=ua, purpose=purpose)


def _on_failure(row: UserTOTP, *, ip, ua, purpose):
    row.failed_attempts = (row.failed_attempts or 0) + 1
    if row.failed_attempts >= MAX_FAILED_ATTEMPTS:
        row.locked_until = timezone.now() + timedelta(minutes=LOCKOUT_MINUTES)
    row.save(update_fields=['failed_attempts', 'locked_until', 'updated_at'])
    _log_attempt(row.user, ChallengeOutcome.BAD_CODE, ip=ip, ua=ua, purpose=purpose)


def _log_attempt(user, outcome, *, ip='', ua='', purpose=''):
    try:
        ChallengeAttempt.objects.create(
            user=user, outcome=outcome,
            ip=(ip or None) if ip else None,
            user_agent=(ua or '')[:200],
            purpose=(purpose or '')[:40],
        )
    except Exception:
        log.debug('challenge attempt log failed', exc_info=True)


# ─── Backup codes ──────────────────────────────────────────────────────────

def _issue_backup_codes(user, count: int = BACKUP_CODE_COUNT) -> list[str]:
    """Replace all existing backup codes with a fresh set. Returns plaintext."""
    BackupCode.objects.filter(user=user).delete()
    plaintexts = [BackupCode.generate_plaintext() for _ in range(count)]
    BackupCode.objects.bulk_create([
        BackupCode(user=user, code_hash=BackupCode.hash_code(p))
        for p in plaintexts
    ])
    return plaintexts


def regenerate_backup_codes(user) -> list[str]:
    """Invalidate all existing backup codes and issue a fresh set. Use when
    a user thinks their codes may be compromised."""
    if not UserTOTP.objects.filter(user=user, enabled_at__isnull=False).exists():
        raise TwoFactorError('2FA not enabled')
    return _issue_backup_codes(user)


# ─── Trusted devices ───────────────────────────────────────────────────────

def trust_device(user, *, name: str = '', ip: str = '', ua: str = '',
                 days: int = TRUSTED_DEVICE_DEFAULT_DAYS) -> str:
    """Issue a new trusted-device token. Caller sets the plaintext as a
    cookie on the user's browser; we keep only the hash."""
    token = secrets.token_urlsafe(32)
    TrustedDevice.objects.create(
        user=user, token_hash=TrustedDevice.hash_token(token),
        name=name[:80], ip=(ip or None) if ip else None,
        user_agent=ua[:200],
        expires_at=timezone.now() + timedelta(days=days),
    )
    return token


def is_device_trusted(user, token: str) -> bool:
    if not token:
        return False
    h = TrustedDevice.hash_token(token)
    now = timezone.now()
    row = TrustedDevice.objects.filter(
        user=user, token_hash=h, expires_at__gt=now,
    ).first()
    if row is None:
        return False
    # Lazy-bump last_used_at (don't UPDATE on every request)
    if row.last_used_at is None or (now - row.last_used_at).total_seconds() > 60:
        TrustedDevice.objects.filter(pk=row.pk).update(last_used_at=now)
    return True


def revoke_device(user, token_or_id):
    """Revoke a specific trusted device, by token OR by pk."""
    try:
        pk = int(token_or_id)
        return TrustedDevice.objects.filter(user=user, pk=pk).delete()[0]
    except (ValueError, TypeError):
        h = TrustedDevice.hash_token(str(token_or_id))
        return TrustedDevice.objects.filter(user=user, token_hash=h).delete()[0]


# ─── Disable / reset ───────────────────────────────────────────────────────

def disable(user, *, actor=None) -> None:
    """Completely remove 2FA for a user. Drops TOTP, all backup codes,
    all trusted devices. Use only after the user has proven identity
    via another channel (account recovery email, customer support call,
    admin override)."""
    with transaction.atomic():
        UserTOTP.objects.filter(user=user).delete()
        BackupCode.objects.filter(user=user).delete()
        TrustedDevice.objects.filter(user=user).delete()
        try:
            from django.contrib.auth import get_user_model
            U = get_user_model()
            U.objects.filter(pk=user.pk).update(two_fa_enabled=False)
        except Exception:
            pass
    log.info('2FA disabled for user %s by %s', user.id,
             getattr(actor, 'email', 'system'))
