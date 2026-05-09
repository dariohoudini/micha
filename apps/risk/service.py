"""
Risk scoring API.

Public surface
--------------
assess(scope, ref_type, ref_id, *, user=None, context=None) → RiskAssessment
    Run all rules registered for `scope`, sum deltas, persist a
    RiskAssessment row, return it. Caller decides what to do with
    `assessment.action` (allow / flag / hold / block).

record_fingerprint(user, fingerprint, ip=None)
    Upsert into DeviceFingerprint (one row per (fp, user)). Bumps the
    last_seen_at + ip + use_count counter — drives the
    `shared_device_farm` rule.
"""
from typing import Optional

from .models import (
    DeviceFingerprint, RiskAction, RiskAssessment, action_for_score,
)
from .rules import rules_for


def assess(scope: str, *, ref_type: str, ref_id, user=None, context: Optional[dict] = None) -> RiskAssessment:
    """Run all rules for `scope` and persist the assessment.

    `context` is a dict the caller can populate freely. Common keys:
        order_amount, fingerprint, ip, user_agent, address_id, payment_method
    Rules consult these as best they can.
    """
    ctx = dict(context or {})
    if user is not None:
        ctx.setdefault('user', user)

    score = 0
    reasons: list[dict] = []
    for name, fn in rules_for(scope):
        try:
            result = fn(ctx)
        except Exception as e:
            # A buggy rule should never break checkout
            reasons.append({'rule': name, 'delta': 0, 'reason': f'Rule errored: {e}'})
            continue
        if not result:
            continue
        delta, reason = result
        score += int(delta)
        reasons.append({'rule': name, 'delta': int(delta), 'reason': reason})

    score = max(0, min(100, score))
    action = action_for_score(score)

    # Persist forensically — context should not contain secrets, only signals.
    safe_context = {
        k: v for k, v in ctx.items()
        if k in ('order_amount', 'fingerprint', 'ip', 'user_agent', 'address_id', 'payment_method')
    }

    return RiskAssessment.objects.create(
        user=user,
        ref_type=ref_type,
        ref_id=str(ref_id)[:80] if ref_id else '',
        score=score,
        action=action,
        reasons=reasons,
        context=safe_context,
    )


def record_fingerprint(*, user, fingerprint: str, ip: Optional[str] = None):
    """Upsert a (fingerprint, user) pair. Bumps use_count + last_seen_at."""
    if not user or not fingerprint:
        return None
    fp = (fingerprint or '')[:128]
    obj, created = DeviceFingerprint.objects.get_or_create(
        fingerprint=fp, user=user,
        defaults={'last_seen_ip': ip},
    )
    if not created:
        DeviceFingerprint.objects.filter(pk=obj.pk).update(
            use_count=obj.use_count + 1,
            last_seen_ip=ip or obj.last_seen_ip,
        )
    return obj


# Convenience aliases for action checks at call sites
def is_blocking(action: str) -> bool:
    return action in (RiskAction.BLOCK, RiskAction.HOLD)
