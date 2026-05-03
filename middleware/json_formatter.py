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
        log = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'level': self.LEVEL_MAP.get(record.levelno, record.levelname),
            'logger': record.name,
            'msg': record.getMessage(),
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
            if key not in skip and not key.startswith('_'):
                try:
                    json.dumps(val)  # ensure serializable
                    log[key] = val
                except (TypeError, ValueError):
                    log[key] = str(val)

        # Exception info
        if record.exc_info:
            log['exception'] = {
                'type': record.exc_info[0].__name__ if record.exc_info[0] else None,
                'message': str(record.exc_info[1]) if record.exc_info[1] else None,
                'traceback': traceback.format_exception(*record.exc_info),
            }

        return json.dumps(log, ensure_ascii=False)
