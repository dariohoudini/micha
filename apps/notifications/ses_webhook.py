"""
apps/notifications/ses_webhook.py
──────────────────────────────────

SES → SNS → us bounce + complaint webhook handler.

Why this exists
────────────────
SES (Amazon's transactional email gateway) delivers bounce and
complaint feedback by publishing to an SNS topic that POSTs to our
HTTPS endpoint. Without a handler, MICHA receives the JSON payloads,
returns 200, and discards them — meaning:

  • Hard bounces (permanent address invalid) never reach the
    suppression list. We keep sending to addresses that bounce,
    AWS bumps our bounce rate, deliverability drops, and eventually
    SES suspends our sending account. At marketplace scale this is
    a "emails silently stop working for 2 days" outage.

  • Complaint events (recipient marked email as junk) never reach
    suppression either. Continuing to send to complainers spikes
    the complaint rate above 0.1% and triggers the same SES
    suspension path.

This module accepts the SES JSON envelope and routes hard bounces +
spam complaints to ``preferences.suppress()``. Soft bounces (transient
mailbox-full, DNS hiccups) are LOGGED but not suppressed — they
resolve on their own.

Two webhook message types from SNS
───────────────────────────────────
SNS sends two ``Type`` values, both via HTTPS POST to the same URL:

  • SubscriptionConfirmation — sent ONCE when the topic is first
    pointed at our endpoint. Contains a ``SubscribeURL``; we fetch
    that URL to confirm we're a willing subscriber. Without
    confirmation, AWS never sends real notifications.

  • Notification — every actual bounce / complaint / delivery event,
    wrapped in an SES JSON document under ``Message``.

SNS signature
──────────────
SNS signs the canonical message bytes with RSA-SHA1 (RSA-SHA256 in
newer signing versions). The signing certificate URL is in the
``SigningCertURL`` field; we verify ONLY if it matches an AWS pattern
(*.amazonaws.com) and the ``cryptography`` package is available.

If cryptography is missing the verifier falls back to
``WEBHOOK_ALLOWED_IPS`` from the existing inbound-webhooks pattern.
SNS publishes its egress IP ranges; operators populate the allowlist.

Operators set ``SES_WEBHOOK_INSECURE = True`` ONLY in development /
staging if there's no allowlist to populate and cryptography isn't
deployed yet.

Public API
──────────
  process_sns_envelope(envelope: dict) -> dict
      Dispatches by ``Type``. Returns {action: 'subscribed' |
      'suppressed_bounce' | 'suppressed_complaint' |
      'logged_transient' | 'ignored', ...}.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from urllib.parse import urlparse

log = logging.getLogger(__name__)


class SNSError(Exception):
    """Raised on malformed envelope or refused subscription."""


# ─── Allowed signing-cert hostname pattern ────────────────────────────
# SNS certs are published at *.amazonaws.com. Anything else is suspect.
# Region-specific URLs end in <region>.amazonaws.com (e.g.
# sns.us-east-1.amazonaws.com). We accept any subdomain of amazonaws.com.
_AWS_HOST_SUFFIX = '.amazonaws.com'


def _is_aws_signing_cert_url(url: str) -> bool:
    try:
        host = (urlparse(url).hostname or '').lower()
        return host.endswith(_AWS_HOST_SUFFIX) or host == 'amazonaws.com'
    except Exception:
        return False


# ─── SNS signature verification ───────────────────────────────────────

def _canonical_string(envelope: dict) -> bytes:
    """SNS canonicalisation: name + '\\n' + value + '\\n' for a fixed
    field order that varies by message type. From the AWS docs.
    """
    msg_type = envelope.get('Type', '')
    if msg_type == 'Notification':
        fields = ['Message', 'MessageId', 'Subject', 'Timestamp',
                  'TopicArn', 'Type']
    elif msg_type in ('SubscriptionConfirmation', 'UnsubscribeConfirmation'):
        fields = ['Message', 'MessageId', 'SubscribeURL', 'Timestamp',
                  'Token', 'TopicArn', 'Type']
    else:
        raise SNSError(f'unknown SNS message type {msg_type!r}')
    out = []
    for f in fields:
        v = envelope.get(f)
        if v is None and f == 'Subject':
            # Subject is optional in Notification; skip when absent
            continue
        if v is None:
            raise SNSError(f'missing field {f!r} in SNS envelope')
        out.append(f)
        out.append(str(v))
    return ('\n'.join(out) + '\n').encode('utf-8')


def _verify_signature(envelope: dict) -> bool:
    """Return True if SNS signature is verified. Falls open (True) when:
       • SES_WEBHOOK_INSECURE = True   (dev / staging escape hatch)
       • cryptography package missing  (logged WARNING, IP allowlist is
                                        the alternative defence layer)
    """
    try:
        from django.conf import settings
        if getattr(settings, 'SES_WEBHOOK_INSECURE', False):
            return True
    except Exception:
        pass

    sig_url = envelope.get('SigningCertURL', '')
    if not _is_aws_signing_cert_url(sig_url):
        log.warning('sns: signing cert URL not AWS: %s', sig_url[:200])
        return False

    sig_b64 = envelope.get('Signature', '')
    if not sig_b64:
        return False

    try:
        from cryptography.x509 import load_pem_x509_certificate
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        import base64
        import urllib.request
    except ImportError:
        log.warning('sns: cryptography package missing — falling back to '
                    'WEBHOOK_ALLOWED_IPS for defence; install cryptography '
                    'for cryptographic verification')
        return True  # fall-open; allowlist is the second layer

    try:
        # Fetch + parse the cert. SNS certs are small and cacheable;
        # in production this should be wrapped with a cache; for now
        # we accept the 10ms cost per webhook (SES bounce volume is low).
        with urllib.request.urlopen(sig_url, timeout=5) as resp:
            cert_pem = resp.read()
        cert = load_pem_x509_certificate(cert_pem)
        pub_key = cert.public_key()

        canon = _canonical_string(envelope)
        sig_bytes = base64.b64decode(sig_b64)

        # SNS uses SHA1 for SignatureVersion=1, SHA256 for version=2.
        version = envelope.get('SignatureVersion', '1')
        hash_alg = hashes.SHA256() if version == '2' else hashes.SHA1()
        pub_key.verify(sig_bytes, canon, padding.PKCS1v15(), hash_alg)
        return True
    except Exception as e:
        log.warning('sns: signature verification failed: %s', e)
        return False


# ─── Subscription confirmation ────────────────────────────────────────

def _confirm_subscription(envelope: dict) -> bool:
    """Hit the SubscribeURL once to complete the topic subscription
    handshake. AWS won't deliver real notifications until this fires.
    """
    sub_url = envelope.get('SubscribeURL', '')
    if not sub_url or not _is_aws_signing_cert_url(sub_url):
        # Same hostname guard as cert URL — if the URL isn't AWS,
        # someone is trying to phish us into hitting their endpoint.
        log.warning('sns: SubscribeURL not AWS: %s', sub_url[:200])
        return False
    try:
        import urllib.request
        with urllib.request.urlopen(sub_url, timeout=10) as resp:
            ok = 200 <= resp.status < 300
        log.info(
            'sns_subscription_confirmed',
            extra={'topic_arn': envelope.get('TopicArn', ''), 'ok': ok},
        )
        return ok
    except Exception as e:
        log.warning('sns: subscription confirmation failed: %s', e)
        return False


# ─── Bounce / complaint dispatch ──────────────────────────────────────

def _route_ses_event(ses_msg: dict) -> dict:
    """Given the SES event JSON (already parsed from envelope.Message),
    suppress affected addresses appropriately.

    Bounce types:
      Permanent      → hard_bounce → suppress (every recipient)
      Transient      → log only; resolves on its own
      Undetermined   → log only; conservative

    Complaint types:
      abuse / fraud / virus → spam_complaint → suppress
      not-spam              → ignore (user disputed the complaint)
      other / unknown       → spam_complaint → suppress (conservative)
    """
    from .preferences import suppress

    event_type = ses_msg.get('eventType') or ses_msg.get('notificationType', '')
    summary = {'action': 'ignored', 'event_type': event_type, 'count': 0}

    if event_type == 'Bounce':
        bounce = ses_msg.get('bounce', {}) or {}
        bounce_type = (bounce.get('bounceType') or '').lower()
        recipients = bounce.get('bouncedRecipients', []) or []
        if bounce_type == 'permanent':
            n = 0
            for r in recipients:
                addr = (r.get('emailAddress') or '').strip()
                if addr:
                    suppress(addr, reason='hard_bounce', source='ses_webhook')
                    n += 1
            summary = {
                'action': 'suppressed_bounce', 'event_type': 'Bounce',
                'count': n,
            }
        else:
            log.info('ses_transient_bounce',
                     extra={'bounce_type': bounce_type,
                            'recipient_count': len(recipients)})
            summary = {'action': 'logged_transient', 'count': len(recipients)}

    elif event_type == 'Complaint':
        comp = ses_msg.get('complaint', {}) or {}
        feedback = (comp.get('complaintFeedbackType') or '').lower()
        recipients = comp.get('complainedRecipients', []) or []
        # "not-spam" means the user explicitly retracted the complaint
        # (or the mailbox provider misclassified). Don't suppress.
        if feedback == 'not-spam':
            summary = {'action': 'ignored', 'event_type': 'Complaint',
                       'feedback': feedback}
        else:
            n = 0
            for r in recipients:
                addr = (r.get('emailAddress') or '').strip()
                if addr:
                    suppress(addr, reason='spam_complaint', source='ses_webhook')
                    n += 1
            summary = {
                'action': 'suppressed_complaint',
                'event_type': 'Complaint', 'count': n,
                'feedback': feedback,
            }
    else:
        log.info('ses_event_ignored',
                 extra={'event_type': event_type})

    return summary


# ─── Public entrypoint ────────────────────────────────────────────────

def process_sns_envelope(envelope: dict) -> dict:
    """Process an SNS envelope. Returns a summary dict.

    Raises SNSError on:
      • envelope structurally invalid
      • SNS signature verification fails (when enabled)
    """
    if not isinstance(envelope, dict):
        raise SNSError('envelope must be a dict')

    msg_type = envelope.get('Type', '')
    if not msg_type:
        raise SNSError('envelope missing Type')

    if not _verify_signature(envelope):
        raise SNSError('SNS signature verification failed')

    if msg_type == 'SubscriptionConfirmation':
        ok = _confirm_subscription(envelope)
        return {'action': 'subscribed' if ok else 'subscription_failed'}

    if msg_type == 'Notification':
        msg_str = envelope.get('Message', '')
        try:
            ses_msg = json.loads(msg_str) if isinstance(msg_str, str) else (msg_str or {})
        except Exception as e:
            raise SNSError(f'Message is not valid JSON: {e}')
        return _route_ses_event(ses_msg)

    if msg_type == 'UnsubscribeConfirmation':
        # Someone removed our subscription. Log loudly so ops notices.
        log.warning(
            'sns_unsubscribe_confirmation',
            extra={'topic_arn': envelope.get('TopicArn', '')},
        )
        return {'action': 'unsubscribe_confirmation'}

    return {'action': 'ignored', 'type': msg_type}
