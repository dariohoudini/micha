"""
ops.alert outbox handler — for now, structured logging.

Wiring to Slack / PagerDuty / email is a config swap; the durability
guarantee already exists in the outbox itself.
"""
import logging

from apps.outbox.handlers import handler

logger = logging.getLogger('ops.alert')


@handler('ops.alert')
def on_ops_alert(payload):
    severity = payload.get('severity', 'info')
    metric = payload.get('metric', 'unknown')
    message = payload.get('message', '')
    level = {
        'critical': logging.CRITICAL,
        'high': logging.ERROR,
        'medium': logging.WARNING,
        'low': logging.INFO,
    }.get(severity, logging.WARNING)
    logger.log(level, f'[ops.alert] {metric}: {message}', extra={
        'metric': metric,
        'severity': severity,
        'details': payload.get('details', {}),
    })
