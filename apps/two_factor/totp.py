"""
apps/two_factor/totp.py

Pure-Python RFC 6238 TOTP implementation. No third-party dep needed —
the algorithm is ~30 lines.

Why roll our own:
  • pyotp is a fine library but adds a dependency for a tiny algorithm
  • Owning it lets us pick the time window for clock-skew tolerance
  • We can plug telemetry directly into verify() (count failures per user)

Compatible with Google Authenticator, 1Password, Authy, anything else
that follows the otpauth:// URI scheme.
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote


TOTP_STEP_SECONDS = 30  # standard RFC 6238 default
TOTP_DIGITS = 6         # standard 6-digit code
# Number of past+future steps to accept beyond the current one. Window=1
# means we accept codes from -30s, current, +30s — protecting against
# minor client clock skew without weakening security materially.
TOTP_WINDOW = 1


def generate_secret(*, length_bytes: int = 20) -> str:
    """Return a base32-encoded random secret. 20 bytes = 160 bits, the
    HMAC-SHA1 native size."""
    raw = secrets.token_bytes(length_bytes)
    return base64.b32encode(raw).decode('ascii').rstrip('=')


def _hotp(secret_b32: str, counter: int, digits: int = TOTP_DIGITS) -> str:
    """RFC 4226 HOTP. TOTP just feeds it ``counter = time // step``."""
    # Pad base32 string if necessary (b32decode is picky about padding)
    pad = '=' * ((8 - len(secret_b32) % 8) % 8)
    key = base64.b32decode((secret_b32 + pad).upper())
    msg = struct.pack('>Q', counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    # Dynamic truncation per RFC
    offset = digest[-1] & 0x0F
    code_int = ((digest[offset] & 0x7F) << 24
                | (digest[offset + 1] & 0xFF) << 16
                | (digest[offset + 2] & 0xFF) << 8
                | (digest[offset + 3] & 0xFF))
    return str(code_int % (10 ** digits)).zfill(digits)


def current_code(secret_b32: str, *, at: float | None = None,
                 step: int = TOTP_STEP_SECONDS, digits: int = TOTP_DIGITS) -> str:
    """Produce the current TOTP code. Used in tests + setup-verify flow."""
    now = at if at is not None else time.time()
    counter = int(now // step)
    return _hotp(secret_b32, counter, digits)


def verify_totp(secret_b32: str, code: str, *,
                at: float | None = None,
                step: int = TOTP_STEP_SECONDS,
                window: int = TOTP_WINDOW,
                digits: int = TOTP_DIGITS) -> bool:
    """Constant-time verify of a user-supplied TOTP code.

    Accepts the current code AND ±``window`` steps around it (default ±30s)
    to absorb client clock skew. Constant-time comparison so the response
    time doesn't leak which step matched."""
    if not (secret_b32 and code):
        return False
    code = code.strip()
    if len(code) != digits or not code.isdigit():
        return False
    now = at if at is not None else time.time()
    counter = int(now // step)
    ok = False
    for delta in range(-window, window + 1):
        candidate = _hotp(secret_b32, counter + delta, digits)
        # Constant-time per-step; OR with running result, no short-circuit
        ok = hmac.compare_digest(candidate, code) or ok
    return ok


def provisioning_uri(secret_b32: str, *, account: str, issuer: str) -> str:
    """Build an otpauth:// URI for QR-code provisioning. Authenticator apps
    scan this and add the account without user typing the secret."""
    label = f'{issuer}:{account}'
    params = '&'.join([
        f'secret={secret_b32}',
        f'issuer={quote(issuer)}',
        f'algorithm=SHA1',
        f'digits={TOTP_DIGITS}',
        f'period={TOTP_STEP_SECONDS}',
    ])
    return f'otpauth://totp/{quote(label)}?{params}'
