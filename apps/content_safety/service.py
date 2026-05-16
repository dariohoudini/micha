"""
apps/content_safety/service.py

Public entrypoint:

  scan(text, *, ref_type, ref_id, actor=None, ip=None) -> ScanReport

ScanReport is a dataclass-like dict:
  {
    'action': 'allow' | 'flag' | 'hide' | 'block',
    'severity': 'info' | 'warn' | 'hide' | 'block',
    'matched_rules': [{'name', 'category', 'severity', 'user_message'}],
    'cleaned_text': str,           # text with sensitive matches redacted
    'user_message': str | None,    # what to show the user on block/hide
    'result_id': int | None,       # ScanResult.id for audit drill-down
  }

Side-effects on each invocation:
  • One ScanResult row written (regardless of action)
  • UserViolationCounter bumped on warn/hide/block
  • If recent_violations >= ESCALATION_THRESHOLD → auto-open a T&S Case
    and stamp last_case_id (idempotent — same user inside the window
    keeps the same case)
  • Outbox 'content.flagged' event published on block/hide

Rule lookup is cached via apps.core.cache_kit, tag 'content_safety:rules' —
ScanRule.save() bumps the tag so admin edits propagate within seconds.
"""
from __future__ import annotations
import logging
import re
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import (
    ScanRule, ScanResult, UserViolationCounter,
    RuleCategory, Severity, Action,
)

log = logging.getLogger(__name__)


# Rolling violation window
VIOLATION_WINDOW_SECONDS = 24 * 3600
# How many violations in the window before we auto-open a T&S case
ESCALATION_THRESHOLD = 3
# Cap on text size we scan — bound runtime regardless of input
MAX_SCAN_LENGTH = 10_000

# Severity ranking — drives final action picked when multiple rules fire
_SEVERITY_RANK = {
    Severity.INFO:  0,
    Severity.WARN:  1,
    Severity.HIDE:  2,
    Severity.BLOCK: 3,
}

_SEVERITY_TO_ACTION = {
    Severity.INFO:  Action.ALLOW,
    Severity.WARN:  Action.FLAG,
    Severity.HIDE:  Action.HIDE,
    Severity.BLOCK: Action.BLOCK,
}


# ─── Rule lookup (cached) ─────────────────────────────────────────────────

def _load_active_rules():
    """Compile all active rules into a list of (rule_dict, compiled_pattern)
    tuples. Cached via cache_kit — admin edits invalidate on save()."""
    try:
        from apps.core.cache_kit import cached_call, build_key
        key = build_key('content_safety_rules', ['content_safety:rules'])
        return cached_call(key, _compile_rules, ttl=300, swr_ttl=60)
    except Exception:
        return _compile_rules()


def _compile_rules():
    out = []
    for r in ScanRule.objects.filter(is_active=True):
        try:
            compiled = re.compile(r.pattern, re.IGNORECASE)
        except re.error as e:
            log.warning('bad regex in rule %s: %s', r.name, e)
            continue
        out.append({
            'name': r.name, 'category': r.category,
            'severity': r.severity, 'applies_to': r.applies_to or [],
            'user_message': r.user_message,
            'pattern': compiled,
        })
    return out


# ─── Main entrypoint ──────────────────────────────────────────────────────

def scan(text: str, *, ref_type: str, ref_id, actor=None, ip: str = '',
         metadata: dict | None = None) -> dict:
    """Run all active rules against ``text``. Returns the ScanReport dict
    (see module docstring). Writes a ScanResult row regardless of action."""
    text = (text or '')[:MAX_SCAN_LENGTH]
    rules = _load_active_rules()

    matched = []
    cleaned = text
    top_severity = Severity.INFO
    user_message = None

    for r in rules:
        # Honour applies_to whitelist — empty list = applies everywhere
        if r['applies_to'] and ref_type not in r['applies_to']:
            continue
        if r['pattern'].search(text):
            matched.append({
                'name': r['name'], 'category': r['category'],
                'severity': r['severity'], 'user_message': r['user_message'],
            })
            # PII / link rules also redact matches from cleaned_text
            if r['category'] in (RuleCategory.PII, RuleCategory.PHISHING):
                cleaned = r['pattern'].sub('[redacted]', cleaned)
            # Track the highest severity hit
            if _SEVERITY_RANK[r['severity']] > _SEVERITY_RANK[top_severity]:
                top_severity = r['severity']
                # Use the most-severe rule's user_message for display
                if r['user_message']:
                    user_message = r['user_message']

    action = _SEVERITY_TO_ACTION[top_severity]

    # Always write the audit row — even on allow. The "I scanned but allowed"
    # case is critical for ML training and tuning later.
    result = None
    try:
        result = ScanResult.objects.create(
            ref_type=ref_type[:40], ref_id=str(ref_id)[:80],
            actor=actor if (actor and getattr(actor, 'is_authenticated', False)) else None,
            severity=top_severity, action=action,
            matched_rules=[r['name'] for r in matched],
            text_hash=ScanResult.hash_text(text),
            text_length=len(text),
            metadata={**(metadata or {}), 'ip': ip or None},
        )
    except Exception:
        log.exception('content_safety: ScanResult insert failed')

    # Escalate when severity warrants AND we have a known actor
    if top_severity != Severity.INFO and actor is not None and getattr(actor, 'is_authenticated', False):
        _record_violation(actor, top_severity, matched_names=[r['name'] for r in matched])

    # Outbox publish on hide/block — async consumers (notify the other
    # party, decrement trust score, etc.)
    if top_severity in (Severity.HIDE, Severity.BLOCK):
        _publish(ref_type, ref_id, actor, top_severity, action, matched)

    return {
        'action': action,
        'severity': top_severity,
        'matched_rules': matched,
        'cleaned_text': cleaned,
        'user_message': user_message,
        'result_id': getattr(result, 'id', None),
    }


# ─── Violation counter + auto-escalation ──────────────────────────────────

def _record_violation(user, severity: str, matched_names: list[str]):
    """Bump the rolling counter; auto-open a case at threshold."""
    now = timezone.now()
    try:
        with transaction.atomic():
            row, created = UserViolationCounter.objects.select_for_update().get_or_create(
                user=user, defaults={'window_started_at': now},
            )
            # Reset the window if it's stale (24h+)
            elapsed = (now - row.window_started_at).total_seconds()
            if elapsed > VIOLATION_WINDOW_SECONDS:
                row.count_24h = 0
                row.window_started_at = now
                row.last_case_id = None  # fresh window → next escalation opens a new case
            row.count_24h += 1
            row.last_violation_at = now
            row.last_severity = severity
            # NOTE: last_case_id MUST be in update_fields so the reset
            # persists. Forgetting it means the window-reset path silently
            # keeps the old case id and never opens a fresh one.
            row.save(update_fields=['count_24h', 'window_started_at',
                                      'last_violation_at', 'last_severity',
                                      'last_case_id'])

            # Auto-open case at threshold (idempotent per window)
            if row.count_24h >= ESCALATION_THRESHOLD and row.last_case_id is None:
                case_id = _open_case_for(user, row, matched_names)
                if case_id:
                    row.last_case_id = case_id
                    row.save(update_fields=['last_case_id'])
    except Exception:
        log.exception('content_safety: violation counter update failed')


def _open_case_for(user, counter_row, matched_names) -> int | None:
    """Open a T&S case attributing the violations to ``user``."""
    try:
        from apps.cases.service import open_case
        from apps.cases.models import CaseKind, CasePriority
        case = open_case(
            kind=CaseKind.POLICY, title=f'Repeat policy violations by {user.email}',
            priority=CasePriority.HIGH,
            subject_type='user', subject_id=str(user.id),
            summary=(f'User had {counter_row.count_24h} content-safety violations '
                     f'in the last 24h. Last severity: {counter_row.last_severity}. '
                     f'Rules: {", ".join(matched_names[:5])}'),
        )
        return case.id
    except Exception:
        log.exception('content_safety: auto-open case failed')
        return None


def _publish(ref_type, ref_id, actor, severity, action, matched):
    try:
        from apps.outbox.service import publish
        publish(
            topic='content.flagged',
            payload={
                'ref_type': ref_type, 'ref_id': str(ref_id),
                'actor_id': actor.id if actor and getattr(actor, 'is_authenticated', False) else None,
                'severity': severity, 'action': action,
                'rule_names': [r['name'] for r in matched],
            },
            dedupe_key=f'content.flagged:{ref_type}:{ref_id}:{int(timezone.now().timestamp())}',
            ref_type=ref_type, ref_id=str(ref_id),
        )
    except Exception:
        log.debug('content_safety: outbox publish failed', exc_info=True)


# ─── Bootstrap helper ─────────────────────────────────────────────────────

def seed_default_rules():
    """Idempotent — adds the baseline ruleset if absent. Called from a
    data migration AND can be invoked manually."""
    seeds = [
        ('phone_local_ao', r'9[2-9]\d\s?\d{3}\s?\d{3}', RuleCategory.PII, Severity.BLOCK,
         'Não é permitido partilhar números de telefone no chat.'),
        ('phone_intl_ao',  r'\+244\s?\d{3}\s?\d{3}\s?\d{3}', RuleCategory.PII, Severity.BLOCK,
         'Não é permitido partilhar números de telefone.'),
        ('whatsapp_mention', r'wh?at?s?app|zap\s*:?\s*\d', RuleCategory.SCAM, Severity.BLOCK,
         'WhatsApp não é permitido — comuniquem dentro da MICHA.'),
        ('email_address',  r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
         RuleCategory.PII, Severity.WARN,
         'Lembrete: mantenham a comunicação dentro da plataforma.'),
        ('iban',           r'iban\s*:?\s*[A-Z]{2}\d{2}', RuleCategory.SCAM, Severity.BLOCK,
         'Não solicitem transferências fora da plataforma.'),
        ('multicaixa',     r'multicaixa\s*(express)?\s*:\s*\d', RuleCategory.SCAM, Severity.BLOCK,
         'Pagamentos só pela MICHA Express.'),
        ('external_link',  r'https?://(?!micha\.ao)\S+', RuleCategory.PHISHING, Severity.HIDE,
         'Links externos foram ocultados.'),
        ('url_shortener',  r'bit\.ly|tinyurl|shorturl', RuleCategory.PHISHING, Severity.BLOCK,
         'Links encurtados não são permitidos.'),
        ('pay_outside',    r'pague?\s*(fora|directo|direct)', RuleCategory.SCAM, Severity.WARN,
         'Sinalização: tentativa de pagamento fora da plataforma.'),
    ]
    created = 0
    for name, pattern, category, severity, msg in seeds:
        _, was_new = ScanRule.objects.get_or_create(
            name=name,
            defaults={
                'pattern': pattern, 'category': category,
                'severity': severity, 'user_message': msg,
                'description': f'Bootstrap rule: {name}',
            },
        )
        if was_new:
            created += 1
    return {'created': created}
