"""
Fraud evaluation service.

`evaluate_fraud(action, context)` is the single entry point. It walks
three layers:

  1. Static checks    — IP manual_block, datacenter/Tor flags
  2. Velocity rules   — DB-driven counters per scope (user/device/ip/email)
  3. Cross-signals    — device fan-out (1 device, N users) etc.

Returns a `FraudDecision` row. Callers branch on `.decision` to
allow / review / challenge / block.

Designed to never throw — fraud evaluation must never fail an action
silently. On unexpected errors we log + default to `allow` (fail-open
for the dev environment; fail-closed via settings.FRAUD_DEFAULT_DECISION
in production).
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import (
    ACTION_CHOICES, ActionLog, DECISION_CHOICES, DeviceFingerprint,
    DeviceUserLink, FraudDecision, IpReputation, VelocityRule,
)

log = logging.getLogger(__name__)

DECISION_RANK = {'allow': 0, 'challenge': 1, 'review': 2, 'block': 3}


def _hardest(*decisions):
    return max(decisions, key=lambda d: DECISION_RANK.get(d, 0))


def register_device(*, ua: str, language: str = '', screen: str = '',
                    timezone_str: str = '', platform: str = '',
                    canvas_hash: str = '') -> str:
    """Upsert the fingerprint row and return its hash."""
    fp = DeviceFingerprint.hash_components(
        ua=ua, lang=language, screen=screen, tz=timezone_str, canvas=canvas_hash,
    )
    obj, created = DeviceFingerprint.objects.get_or_create(
        fingerprint_hash=fp,
        defaults={
            'raw_ua': (ua or '')[:255], 'language': language[:24],
            'screen': screen[:32], 'timezone': timezone_str[:64],
            'platform': platform[:32], 'canvas_hash': canvas_hash[:64],
        },
    )
    if not created:
        DeviceFingerprint.objects.filter(pk=fp).update(
            seen_count=obj.seen_count + 1,
        )
    return fp


def link_device_to_user(*, device_hash: str, user) -> None:
    if not device_hash or not user:
        return
    obj, created = DeviceUserLink.objects.get_or_create(
        device_id=device_hash, user=user,
    )
    if not created:
        DeviceUserLink.objects.filter(pk=obj.pk).update(
            seen_count=obj.seen_count + 1,
        )


def evaluate_fraud(*, action: str, user=None, ip: str = '',
                   device_hash: str = '', email: str = '',
                   amount=None, extra: dict = None) -> FraudDecision:
    """Run all checks for `action`. Always returns a FraudDecision
    row (never None)."""
    reasons = []
    score = 0
    decision = 'allow'

    try:
        # ─── 1. IP reputation ──────────────────────────────────
        if ip:
            rep = IpReputation.objects.filter(pk=ip).first()
            if rep:
                if rep.is_manual_block:
                    reasons.append({'rule': 'IP_MANUAL_BLOCK', 'weight': 100})
                    score = min(100, score + 100)
                    decision = _hardest(decision, 'block')
                if rep.is_tor:
                    reasons.append({'rule': 'IP_TOR', 'weight': 40})
                    score = min(100, score + 40)
                    decision = _hardest(decision, 'review')
                if rep.is_datacenter:
                    reasons.append({'rule': 'IP_DATACENTER', 'weight': 25})
                    score = min(100, score + 25)
                    decision = _hardest(decision, 'review')
                if rep.external_score >= 70:
                    reasons.append({'rule': 'IP_EXTERNAL_SCORE',
                                    'value': rep.external_score,
                                    'weight': 30})
                    score = min(100, score + 30)
                    decision = _hardest(decision, 'review')

        # ─── 2. Velocity rules ─────────────────────────────────
        rules = VelocityRule.objects.filter(action=action, is_active=True)
        for rule in rules:
            count = _scope_count(rule, user=user, device_hash=device_hash,
                                  ip=ip, email=email)
            if count >= rule.max_count:
                reasons.append({
                    'rule': f'velocity:{rule.name}',
                    'scope': rule.scope, 'count': count,
                    'limit': rule.max_count,
                    'window_seconds': rule.window_seconds,
                    'weight': rule.score_weight,
                })
                score = min(100, score + rule.score_weight)
                decision = _hardest(decision, rule.on_exceed)

        # ─── 3. Device fan-out ─────────────────────────────────
        if device_hash:
            fan = DeviceUserLink.objects.filter(device_id=device_hash).count()
            if fan >= 5:
                reasons.append({'rule': 'DEVICE_FANOUT_HIGH',
                                'distinct_users': fan, 'weight': 40})
                score = min(100, score + 40)
                decision = _hardest(decision, 'review')
            elif fan >= 3:
                reasons.append({'rule': 'DEVICE_FANOUT_MEDIUM',
                                'distinct_users': fan, 'weight': 20})
                score = min(100, score + 20)

        # ─── 4. Static threshold ───────────────────────────────
        if score >= 80 and decision in ('allow', 'challenge'):
            decision = 'review'
    except Exception as e:
        log.exception('fraud evaluator crashed: %s', e)
        decision = getattr(settings, 'FRAUD_DEFAULT_DECISION', 'allow')
        reasons.append({'rule': 'EVALUATOR_ERROR', 'error': str(e)[:200]})

    obj = FraudDecision.objects.create(
        action=action, user=user, device_hash=device_hash[:64],
        ip_address=ip or None, score=score, decision=decision,
        reasons=reasons,
        context={'email': email or '', 'amount': str(amount) if amount else ''},
    )

    # Always log the action so future velocity-rule evaluations
    # can count it.
    ActionLog.objects.create(
        action=action, user=user, device_hash=device_hash[:64],
        ip_address=ip or None, email=(email or '')[:254],
    )
    return obj


def _scope_count(rule: VelocityRule, *, user, device_hash, ip, email) -> int:
    """Count ActionLog rows matching the rule's scope inside its
    rolling window."""
    cutoff = timezone.now() - timedelta(seconds=rule.window_seconds)
    qs = ActionLog.objects.filter(
        action=rule.action, occurred_at__gte=cutoff,
    )
    if rule.scope == 'user' and user:
        qs = qs.filter(user=user)
    elif rule.scope == 'device' and device_hash:
        qs = qs.filter(device_hash=device_hash)
    elif rule.scope == 'ip' and ip:
        qs = qs.filter(ip_address=ip)
    elif rule.scope == 'email' and email:
        qs = qs.filter(email__iexact=email)
    else:
        return 0
    return qs.count()


def upsert_ip_reputation(*, ip: str, external_score: int = 0,
                          country: str = '', is_datacenter: bool = False,
                          is_tor: bool = False, is_proxy: bool = False,
                          manual_block: bool = False) -> IpReputation:
    obj, _ = IpReputation.objects.update_or_create(
        ip_address=ip,
        defaults={
            'external_score': external_score, 'country': country[:2],
            'is_datacenter': is_datacenter, 'is_tor': is_tor,
            'is_proxy': is_proxy, 'is_manual_block': manual_block,
        },
    )
    return obj
