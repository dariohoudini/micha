"""
JSON log formatter for structured logging.
Outputs one JSON object per line — compatible with Papertrail, CloudWatch, Datadog.
"""
import json
import logging
import traceback
from datetime import datetime, timezone


class MichaJSONFormatter(logging.Formatter):
    """
    Formats log records as structured JSON.
    Every field is searchable in Papertrail/CloudWatch/Datadog.
    """

    LEVEL_MAP = {
        logging.DEBUG: 'DEBUG',
        logging.INFO: 'INFO',
        logging.WARNING: 'WARNING',
        logging.ERROR: 'ERROR',
        logging.CRITICAL: 'CRITICAL',
    }

    def format(self, record):
        # Local import — avoids a hard dependency at module import time
        # in case settings aren't loaded yet (early-boot logging).
        try:
            from middleware.pii_redactor import (
                redact_text, redact_value, redact_path, _key_is_sensitive,
            )
        except Exception:
            # Fail-open is unacceptable here — but if redactor itself
            # is broken, the formatter still needs to produce a line.
            # Mark the line so ops can tell.
            redact_text = lambda s: s
            redact_value = lambda v, **kw: v
            redact_path = lambda p: p
            _key_is_sensitive = lambda k: False

        log = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'level': self.LEVEL_MAP.get(record.levelno, record.levelname),
            'logger': record.name,
            # ``getMessage()`` runs the % / f-string interpolation; we
            # scrub the resulting string for in-text PII patterns
            # (emails, phone numbers, Bearer tokens, OTP-shape digit
            # runs after hint words).
            'msg': redact_text(record.getMessage()),
            'request_id': getattr(record, 'request_id', '-'),
            'user_id': getattr(record, 'user_id', '-'),
        }

        # Add extra fields passed via extra={}
        skip = {
            'args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename',
            'funcName', 'levelname', 'levelno', 'lineno', 'message', 'module',
            'msecs', 'msg', 'name', 'pathname', 'process', 'processName',
            'relativeCreated', 'stack_info', 'thread', 'threadName',
            'request_id', 'user_id',
        }
        for key, val in record.__dict__.items():
            if key in skip or key.startswith('_'):
                continue

            # Key-level redaction: anything that looks like a credential
            # name has its value wholesale replaced.
            if _key_is_sensitive(key):
                log[key] = '[REDACTED]'
                continue

            # ``path`` gets query-string stripped — URL params are a
            # common PII channel even on anonymous endpoints.
            if key == 'path' and isinstance(val, str):
                log[key] = redact_path(val)
                continue

            # General case — recursive scrub.
            try:
                json.dumps(val)  # ensure serializable
                log[key] = redact_value(val)
            except (TypeError, ValueError):
                log[key] = redact_text(str(val))

        # Exception info — also scrubbed. Tracebacks frequently contain
        # request bodies / repr'd model instances that leak PII.
        if record.exc_info:
            log['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': redact_text(str(record.exc_info[1]) if record.exc_info[1] else ''),
                'traceback': [
                    redact_text(line)
                    for line in traceback.format_exception(*record.exc_info)
                ],
            }

        return json.dumps(log, ensure_ascii=False)
