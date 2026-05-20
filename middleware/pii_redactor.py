"""
middleware/pii_redactor.py
───────────────────────────

Defensive PII / secret scrub for structured log output.

Why this exists
────────────────
``MichaJSONFormatter`` serialises every ``extra=`` kwarg from every log
call straight into the JSON line. Without redaction:

  • A developer who writes ``log.info("login", extra={"email": x,
    "password": y})`` ships the password to CloudWatch.

  • The OTP-issuing path used to do
    ``logger.info(f"Phone OTP for {phone}: {otp}")`` — the OTP code
    was in the structured log file readable by every ops engineer
    with log access. That's a sub-second account-takeover primitive.

  • ``apps/orders/checkout.py`` and several other paths emit f-strings
    with ``user.email`` directly in the log message. Even when the
    intent is debugging, the email lands in retained logs, becoming
    a GDPR / Lei 22/11 personal-data disclosure that's expensive to
    de-list after the fact.

The redactor is defence-in-depth: callers SHOULD avoid logging PII
in the first place, but the formatter runs unconditionally so even
the next developer who forgets gets scrubbed output.

Layers
──────
  1. ``redact_value(v)``      — recursive scrub of any JSON-serializable
                                value (dicts, lists, strings, scalars).

  2. ``redact_text(s)``       — regex pattern pass that catches emails,
                                phone numbers, Bearer tokens, long
                                alphanumeric secrets, and OTP-shape
                                digit runs in free-form text.

  3. ``redact_key(key, val)`` — key-based scrub: keys matching the
                                sensitive-name pattern have their values
                                wholesale replaced with [REDACTED].

  4. ``redact_path(path)``    — strip query strings (preserves the
                                URL pattern for analytics, drops
                                ``?email=foo@bar.com``).

What's intentionally NOT redacted
──────────────────────────────────
  • Numeric user_id — needed for cross-line correlation in support.
  • request_id — random per-request UUID; no PII.
  • Timestamps, log level, logger name, status codes, duration_ms.
  • Path WITHOUT the query string (analytics need it).

Settings switch
───────────────
``LOG_PII_REDACTION_ENABLED`` (default True in production via settings):
turn off in dev/test if redaction is interfering with debugging. The
formatter checks this at format time so flipping it doesn't require
a restart.
"""
from __future__ import annotations

import re
from typing import Any


# ─── Sensitive key names ──────────────────────────────────────────────
# Matched case-insensitively against extra-kwarg keys + dict keys
# encountered during recursion. Values are wholesale [REDACTED]'d.
#
# Why these specifically:
#   password / passwd / secret / token / api_key — auth credentials.
#   cvv / cvc / pan / card_number — PCI DSS sensitive cardholder data.
#   otp / totp / 2fa_code / verification_code — auth-grade one-time secrets.
#   ssn — US social security (rare here but defensive).
#   nif — Angolan tax ID (Número de Identificação Fiscal).
#   iban / bank_account / routing / swift — banking instrument details.
#   authorization / x-api-key — common HTTP auth headers.
#   private_key / encryption_key — crypto material.
_SENSITIVE_KEY_PATTERN = re.compile(
    r'(?i)('
    r'password|passwd|pwd|secret|api[_-]?key|'
    r'token|access[_-]?token|refresh[_-]?token|id[_-]?token|bearer|'
    r'authoriz(?:ation|ed)?|x[_-]api[_-]?key|'
    r'otp|totp|2fa[_-]?code|verification[_-]?code|recovery[_-]?code|'
    r'cvv|cvc|pan|card[_-]?number|card[_-]?cvv|'
    r'ssn|nif|tax[_-]?id|'
    r'iban|swift|routing|bank[_-]?account|account[_-]?number|'
    r'private[_-]?key|encryption[_-]?key|signing[_-]?key|'
    r'session[_-]?key|cookie|csrf'
    r')'
)


# ─── In-text patterns ─────────────────────────────────────────────────

# Email: keep the domain for debugging context, scrub the local-part.
# Match conservatively to avoid mangling addresses inside URLs.
_EMAIL_RE = re.compile(
    r'\b([a-zA-Z0-9._%+-]+)@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b'
)

# Angolan phone: +244 9XX XXX XXX (9 digits after +244). Generic mobile
# patterns too. We keep the country code prefix and last 2 digits for
# debugging.
_PHONE_RE = re.compile(
    r'\+?\d{1,3}[\s.-]?\d{2,3}[\s.-]?\d{3}[\s.-]?\d{3,4}'
)

# Bearer / API key tokens — 30+ chars of base64-ish alphanumeric.
# Catches JWT, opaque tokens, Stripe-shape sk_*/pk_*, etc.
_LONG_TOKEN_RE = re.compile(
    r'\b(?:Bearer\s+)?([A-Za-z0-9_\-\.]{30,})\b'
)

# OTP shape: a standalone 4–8 digit sequence preceded by a code-like
# word ("OTP", "code", "verification"). Two variants:
#   _OTP_HINT_RE        — hint word adjacent to digits ("OTP: 123456")
#   _OTP_HINT_PRESENT_RE— hint appears anywhere in message; scrub ANY
#                         standalone 4–8 digit run (defends against
#                         "Phone OTP for +244…: 123456" where digits
#                         are far from the hint).
# Conservative on the standalone-digit form: requires whitespace or
# punctuation on both sides so we don't break inside order IDs, UUIDs,
# or timestamps.
_OTP_HINT_RE = re.compile(
    r'(?i)\b(otp|code|verification|2fa|totp)\b\s*[:=]?\s*(\d{4,8})\b'
)
_OTP_KEYWORDS_RE = re.compile(r'(?i)\b(otp|totp|2fa|verification[_\s-]?code|recovery[_\s-]?code)\b')
_STANDALONE_DIGITS_RE = re.compile(r'(?<![A-Za-z0-9])(\d{4,8})(?![A-Za-z0-9])')

# Authorization header value when it appears inline (e.g. in error
# traces): "Authorization: Bearer xxxxx".
_AUTH_HEADER_RE = re.compile(
    r'(?i)(authorization\s*[:=]\s*)(\S+)'
)

# Inline credential assignments — common in source code lines captured
# in tracebacks: ``password="hunter2"``, ``api_key=sk_live_xxx``,
# ``token: 'abc'``. We catch a small set of credential-named keywords
# and mask the value. Keeps the keyword so the masked output stays
# readable; masks the value out to the next quote / comma / whitespace.
_INLINE_CRED_RE = re.compile(
    r'(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|'
    r'access[_-]?token|refresh[_-]?token|cvv|cvc|pan|card[_-]?number|'
    r'otp|totp|2fa[_-]?code|private[_-]?key)\s*[:=]\s*'
    r'(["\']?)([^"\'\s,;)\]}]+)\2'
)


_REDACT = '[REDACTED]'


def _is_redaction_enabled() -> bool:
    try:
        from django.conf import settings
        return bool(getattr(settings, 'LOG_PII_REDACTION_ENABLED', True))
    except Exception:
        # If settings aren't loaded yet, default ON — safer.
        return True


def redact_text(text: str) -> str:
    """Scrub PII / secret-shape substrings from free-form text.

    Order matters: auth-header pattern runs BEFORE the long-token
    catch-all so we don't double-redact the same span.
    """
    if not text or not isinstance(text, str):
        return text
    if not _is_redaction_enabled():
        return text

    # Authorization headers: keep the prefix so debugging can see
    # what header was set, scrub the value.
    text = _AUTH_HEADER_RE.sub(lambda m: f'{m.group(1)}{_REDACT}', text)

    # Inline credential assignments (password="x", api_key=foo) — most
    # commonly hit in source-code lines captured by Sentry stacktraces
    # and in shell-style log strings.
    text = _INLINE_CRED_RE.sub(
        lambda m: f'{m.group(1)}={m.group(2)}{_REDACT}{m.group(2)}',
        text,
    )

    # OTP-shape with hint: replace the digit run, keep the hint word.
    text = _OTP_HINT_RE.sub(lambda m: f'{m.group(1)} {_REDACT}', text)

    # If the message contains any OTP-family keyword, also scrub
    # standalone 4–8 digit runs anywhere in the message. This catches
    # "Phone OTP for +244...: 123456" where the digits are far from
    # the hint word. Boundary on non-alphanumeric so order IDs / PKs
    # / UUIDs aren't munged.
    if _OTP_KEYWORDS_RE.search(text):
        text = _STANDALONE_DIGITS_RE.sub(_REDACT, text)

    # Emails: partial — keep domain.
    text = _EMAIL_RE.sub(lambda m: f'***@{m.group(2)}', text)

    # Phone numbers — partial mask.
    def _mask_phone(m):
        s = m.group(0)
        # Keep first 4 chars (often +244) and last 2 digits.
        if len(s) > 8:
            return s[:4] + '***' + s[-2:]
        return _REDACT
    text = _PHONE_RE.sub(_mask_phone, text)

    # Long opaque tokens — only when they're NOT inside an obvious
    # word boundary like a UUID-with-dashes that's known-safe. We
    # accept some false positives on long order IDs — they're not
    # secrets anyway, just less readable.
    # NB: applied LAST so the more specific patterns above already
    # caught their cases.
    # Skip if string is short overall.
    if len(text) > 30:
        text = _LONG_TOKEN_RE.sub(
            lambda m: f'{_REDACT}' if len(m.group(1)) >= 30 else m.group(0),
            text,
        )

    return text


def _key_is_sensitive(key: str) -> bool:
    return bool(_SENSITIVE_KEY_PATTERN.search(str(key)))


def redact_value(value: Any, *, depth: int = 0) -> Any:
    """Recursively scrub PII from any JSON-serializable value.

    Sensitive-named keys at any depth have their values wholesale
    replaced. String leaves get the regex scrub. Numeric / bool / None
    pass through unchanged.

    Depth-limited at 8 to bound CPU on adversarial nesting.
    """
    if not _is_redaction_enabled():
        return value
    if depth > 8:
        return value

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if _key_is_sensitive(k):
                out[k] = _REDACT
            else:
                out[k] = redact_value(v, depth=depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [redact_value(v, depth=depth + 1) for v in value]
    # Fallback — stringify + scrub.
    try:
        return redact_text(str(value))
    except Exception:
        return value


def redact_path(path: str) -> str:
    """Strip query strings from a URL path.

    Query strings frequently contain PII even on otherwise-anonymous
    endpoints (``?email=...``, ``?phone=...``, ``?token=...``). For
    structured-log analytics we only need the path pattern; the query
    string is rarely useful and frequently leaky.
    """
    if not path or not isinstance(path, str):
        return path
    if '?' not in path:
        return path
    return path.split('?', 1)[0]
