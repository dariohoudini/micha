"""
middleware/sentry_scrub.py
───────────────────────────

Sentry ``before_send`` hook that runs every error event through the
PII redactor before submission.

Why this exists
────────────────
The Sentry init in config/settings.py sets ``send_default_pii=False``,
which strips Django's default PII (cookies, body, user fields). But
that's only ~30% of the surface. The rest:

  • Log breadcrumbs auto-captured by the Sentry SDK's logging
    integration. ``log.error("Login failed for %s", user.email)``
    sends the formatted message to Sentry as a breadcrumb — full
    email plaintext, regardless of send_default_pii.

  • ``extra={...}`` kwargs on log calls. Same path: full plaintext
    into the breadcrumb's data dict.

  • Exception messages + traceback locals. Tracebacks frequently
    capture repr'd model instances, request bodies, sensitive
    function arguments. Sentry's stacktrace.frames[].vars carries
    every local variable in the frame.

  • Custom event tags / contexts set via sentry_sdk.set_tag /
    set_context. A developer who does set_context('user_meta',
    {'email': ..., 'phone': ...}) sends those directly.

  • Transaction event headers + params (for performance monitoring).
    A query string ``?email=foo@bar.com`` lands in
    transaction['contexts']['trace']['data']['url'].

The PII redactor (middleware/pii_redactor.py) already knows how to
scrub all the patterns we care about — emails, phones, tokens,
OTP-shape digit runs, sensitive-named keys. The ``before_send`` hook
just routes every Sentry event through ``redact_value`` so the same
rules apply to errors and traces as to log lines.

Why this is its own module
───────────────────────────
config/settings.py is already busy and the scrub logic + structure
of a Sentry event dict deserves a dedicated module. Tests can import
``before_send`` directly without spinning up the SDK.

What's NOT scrubbed
────────────────────
  • Sentry's own ``event_id``, ``platform``, ``sdk`` — these are
    SDK metadata, not user data.
  • Numeric fields (timestamps, sample rates) — pass through.
  • Stack frame ``filename`` / ``function`` / ``lineno`` — paths in
    the codebase are not PII.

Everything else (message, breadcrumbs, extra, contexts, tags, request
data, traceback frame locals) is recursively scrubbed.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)


# Keys at the top level of a Sentry event whose VALUES need recursive
# scrubbing. Other top-level keys (event_id, platform, sdk, level,
# server_name, transaction) are metadata/identifiers we leave alone.
_SCRUB_KEYS = frozenset({
    'message', 'logentry', 'exception', 'breadcrumbs',
    'extra', 'tags', 'contexts', 'request', 'user',
    'modules',  # rarely contains user data but be conservative
})


def _scrub(value):
    """Run a value through the PII redactor recursively."""
    try:
        from middleware.pii_redactor import redact_value
        return redact_value(value)
    except Exception:
        # If the redactor itself is broken, fail open — Sentry's
        # send_default_pii=False is still the main defence; we'd
        # rather see scrubbed-incompletely than no events.
        log.warning('sentry_scrub: redactor failed, passing through',
                    exc_info=True)
        return value


def _scrub_frame(frame: dict) -> dict:
    """Scrub a stacktrace frame.

    Frame structure: {filename, function, lineno, vars, pre_context,
    context_line, post_context, abs_path, ...}.

    ``vars`` is the dict of local variables in the frame at the time
    of the exception. These are the highest-PII-risk fields — repr'd
    model instances, request bodies, sensitive kwargs. Recursively
    scrub.

    ``context_line`` and ``pre/post_context`` are source code lines.
    Usually safe but a developer might have committed an f-string that
    contains a literal email. Scrub them as text.
    """
    if not isinstance(frame, dict):
        return frame
    out = dict(frame)
    if 'vars' in out:
        out['vars'] = _scrub(out['vars'])
    for k in ('context_line', 'pre_context', 'post_context'):
        if k in out and out[k] is not None:
            out[k] = _scrub(out[k])
    return out


def _scrub_exception(exc_dict: dict) -> dict:
    """Scrub an exception entry. Structure:
       {values: [{type, value, module, stacktrace: {frames: [...]}}, ...]}.
    """
    if not isinstance(exc_dict, dict):
        return exc_dict
    out = dict(exc_dict)
    vals = out.get('values') or []
    new_vals = []
    for v in vals:
        if not isinstance(v, dict):
            new_vals.append(v)
            continue
        nv = dict(v)
        if 'value' in nv and nv['value'] is not None:
            nv['value'] = _scrub(nv['value'])
        st = nv.get('stacktrace') or {}
        if isinstance(st, dict) and 'frames' in st:
            st = dict(st)
            st['frames'] = [_scrub_frame(f) for f in (st['frames'] or [])]
            nv['stacktrace'] = st
        new_vals.append(nv)
    out['values'] = new_vals
    return out


def _scrub_breadcrumbs(bc: dict) -> dict:
    """Scrub breadcrumbs. Structure: {values: [{type, category,
    message, data, timestamp, level}, ...]}.

    The ``message`` is the log-call's formatted text — primary
    PII vector. The ``data`` dict contains extra= kwargs.
    """
    if not isinstance(bc, dict):
        return bc
    out = dict(bc)
    vals = out.get('values') or []
    new_vals = []
    for v in vals:
        if not isinstance(v, dict):
            new_vals.append(v)
            continue
        nv = dict(v)
        if 'message' in nv and nv['message'] is not None:
            nv['message'] = _scrub(nv['message'])
        if 'data' in nv:
            nv['data'] = _scrub(nv['data'])
        new_vals.append(nv)
    out['values'] = new_vals
    return out


def _scrub_request(req: dict) -> dict:
    """Scrub the request dict. Structure: {url, method, headers, env,
    cookies, query_string, data}.

    ``send_default_pii=False`` already strips body+cookies in modern
    SDK versions, but we belt-and-braces:
      • url    — strip query string
      • headers — Authorization etc. caught by redactor's key scrub
      • query_string — scrub text (?email=...)
      • data   — recursive
    """
    if not isinstance(req, dict):
        return req
    out = dict(req)
    if 'url' in out and isinstance(out['url'], str):
        try:
            from middleware.pii_redactor import redact_path
            base, sep, _ = out['url'].partition('?')
            out['url'] = redact_path(base) if not sep else base
        except Exception:
            pass
    for k in ('query_string', 'headers', 'env', 'cookies', 'data'):
        if k in out:
            out[k] = _scrub(out[k])
    return out


def before_send(event, hint):
    """Sentry SDK ``before_send`` hook.

    Receives every error event before submission. We return either the
    scrubbed event (deliver to Sentry) or None (drop the event). We
    never drop — every reachable error is sendable; we just strip PII.
    """
    if not isinstance(event, dict):
        return event

    try:
        for key in list(event.keys()):
            if key not in _SCRUB_KEYS:
                continue
            val = event[key]
            if key == 'exception':
                event[key] = _scrub_exception(val)
            elif key == 'breadcrumbs':
                event[key] = _scrub_breadcrumbs(val)
            elif key == 'request':
                event[key] = _scrub_request(val)
            elif key == 'logentry':
                # logentry: {message, formatted, params}
                if isinstance(val, dict):
                    lv = dict(val)
                    for k in ('message', 'formatted'):
                        if k in lv:
                            lv[k] = _scrub(lv[k])
                    if 'params' in lv:
                        lv['params'] = _scrub(lv['params'])
                    event[key] = lv
            else:
                event[key] = _scrub(val)
    except Exception:
        # Hook MUST NOT crash the SDK — drop the scrub on errors and
        # let the unscrubbed event through (the SDK's send_default_pii
        # is still the floor).
        log.warning('sentry_scrub.before_send failed', exc_info=True)

    return event


def before_send_transaction(event, hint):
    """Performance / transaction events go through the same scrub.

    Transaction events carry ``contexts['trace']['data']``, request
    URL, and spans. URL query strings are the most common leak vector
    here (a transaction tagged with ``GET /api/users?email=x``).
    """
    return before_send(event, hint)
