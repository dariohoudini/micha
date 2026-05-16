"""
apps/flags/evaluator.py

Public entrypoint:

    evaluate(flag_name, user=None, default=None, *,
             anon_token='', log_exposure=False) -> Any

Determinism contract:
  Same (flag_name, user_id) ALWAYS evaluates to the same result, regardless
  of which process/host computes it. Hash-based bucketing — no random state
  shared between workers.

Fail-safety contract:
  evaluate() never raises. Any exception (DB unreachable, flag malformed,
  cache backend down) is logged and the caller gets the default value. A
  flag misconfiguration must never break a feature.

Cache contract:
  Reads go through cache_kit (tag 'flag:<name>') with single-flight. Flag
  updates bump the tag → all cached evaluations for that flag become misses
  on next read. Per-user evaluations also cache for a short window so a
  burst of flag reads inside one request returns from RAM.
"""
from __future__ import annotations
import hashlib
import logging

log = logging.getLogger(__name__)

# Salt baked into bucket hashes. Changing it would reshuffle every user's
# bucket — DO NOT change in production without explicit rollout planning.
_BUCKET_SALT = 'micha-flags-v1'

# Cache window for evaluation results. Short enough that toggling a flag
# in admin propagates within a minute even without explicit invalidation.
_EVAL_TTL = 60
_EVAL_SWR = 30


def evaluate(flag_name: str, user=None, default=None, *,
             anon_token: str = '', log_exposure: bool = False):
    """Return the value of ``flag_name`` for ``user``.

    Args:
      flag_name: stable identifier matching a Flag row.
      user: Django auth user object (or anything with .id and is_authenticated).
            May be None / AnonymousUser — anon_token is used in that case.
      default: returned if the flag doesn't exist, is inactive, or eval fails.
      anon_token: stable session-derived token used to bucket anonymous users.
      log_exposure: write an ExperimentExposure row. Caller MUST call with
        True only when the flag's result is actually surfaced to the user
        (rendering, action taken). Logging on a flag that's evaluated but
        never shown corrupts A/B analysis.
    """
    try:
        return _evaluate(flag_name, user, default, anon_token, log_exposure)
    except Exception as e:
        log.exception('flag evaluator failure on %s: %s', flag_name, e)
        return default


def _evaluate(flag_name, user, default, anon_token, log_exposure):
    flag = _load_flag(flag_name)
    if flag is None or not flag.get('is_active', True):
        # Unknown flag or paused — return the default. We still log
        # exposure with variant='__default__' so analysis can distinguish
        # "flag was off" from "user wasn't in scope".
        value = default if default is not None else flag.get('default_value', False) if flag else default
        if log_exposure and (user or anon_token):
            _record_exposure(flag_name, user, anon_token, '__default__')
        return value

    # Per-user override always wins
    if user is not None and getattr(user, 'is_authenticated', False):
        override = _load_override(flag['id'], user.id)
        if override is not None:
            if log_exposure:
                _record_exposure(flag_name, user, anon_token, str(override), source='override')
            return override

    rules = flag.get('rules') or {}
    kind = flag.get('kind')

    # Segment rules evaluated before percentage. "is_staff" / "is_superuser"
    # / "is_seller" segments force a positive outcome.
    if _matches_segment(user, rules.get('segments') or []):
        value = _value_for_positive_outcome(flag, rules)
        if log_exposure:
            _record_exposure(flag_name, user, anon_token, str(value), source='segment')
        return value

    # Percentage / variant bucketing
    bucket = _bucket_for(flag_name, user, anon_token)

    if kind == 'boolean' or kind == 'percentage':
        pct = int(rules.get('percentage', 0))
        is_on = bucket < pct
        result = True if is_on else flag.get('default_value', False)
        if log_exposure:
            _record_exposure(flag_name, user, anon_token, str(result), source='rollout')
        return result

    if kind == 'variant':
        variants = rules.get('variants') or {}
        if not variants:
            return flag.get('default_value', default)
        result = _bucket_to_variant(bucket, variants)
        if log_exposure:
            _record_exposure(flag_name, user, anon_token, result, source='variant')
        return result

    return flag.get('default_value', default)


def _bucket_for(flag_name: str, user, anon_token: str) -> int:
    """Map (flag, identity) → [0, 100). Stable across calls and processes."""
    key = anon_token or ''
    if user is not None and getattr(user, 'is_authenticated', False):
        key = f'u:{user.id}'
    digest = hashlib.sha256(f'{_BUCKET_SALT}:{flag_name}:{key}'.encode()).digest()
    # Take first 4 bytes as unsigned int, mod 100 → [0, 100).
    return int.from_bytes(digest[:4], 'big') % 100


def _bucket_to_variant(bucket: int, variants: dict) -> str:
    """Map a [0,100) bucket to a variant name. ``variants`` is a dict of
    {name: weight}. Weights are interpreted as relative — we normalise so
    they sum to 100 internally."""
    total = sum(int(w) for w in variants.values()) or 100
    cumulative = 0
    # Sort by name for determinism — Python dict order is insertion order
    # but flag rules JSON may load in any order across processes.
    for name in sorted(variants.keys()):
        weight = int(variants[name])
        cumulative += int(round(weight * 100 / total))
        if bucket < cumulative:
            return name
    # Round-off guard
    return sorted(variants.keys())[-1]


def _matches_segment(user, segments: list) -> bool:
    if user is None or not getattr(user, 'is_authenticated', False):
        return False
    for seg in segments:
        if seg == 'is_staff' and getattr(user, 'is_staff', False):
            return True
        if seg == 'is_superuser' and getattr(user, 'is_superuser', False):
            return True
        if seg == 'is_seller' and getattr(user, 'is_seller', False):
            return True
    return False


def _value_for_positive_outcome(flag, rules):
    """For variant flags, segment-matched users get the first non-control
    variant. For booleans, they get True."""
    if flag.get('kind') == 'variant':
        variants = rules.get('variants') or {}
        non_control = [k for k in sorted(variants.keys()) if k != 'control']
        return non_control[0] if non_control else (sorted(variants.keys())[0] if variants else True)
    return True


# ─── Cached loaders ───────────────────────────────────────────────────────

def _load_flag(name: str):
    """Load a flag by name. Cached with tag invalidation on save."""
    try:
        from apps.core.cache_kit import cached_call, build_key
        key = build_key('flag_def', [f'flag:{name}'], name)
        return cached_call(key, lambda: _load_flag_db(name),
                           ttl=_EVAL_TTL, swr_ttl=_EVAL_SWR)
    except Exception:
        return _load_flag_db(name)


def _load_flag_db(name):
    from .models import Flag
    f = Flag.objects.filter(name=name).first()
    if f is None:
        return None
    return {
        'id': f.id, 'name': f.name, 'kind': f.kind, 'is_active': f.is_active,
        'rules': f.rules or {}, 'default_value': f.default_value,
    }


def _load_override(flag_id, user_id):
    """Per-user override lookup. Cached briefly so a burst of evaluations
    for the same user inside one request doesn't fan out to DB."""
    try:
        from apps.core.cache_kit import cached_call, build_key
        key = build_key('flag_override', [f'flag_override:{flag_id}:{user_id}'],
                        flag_id, user_id)
        v = cached_call(key, lambda: _load_override_db(flag_id, user_id),
                        ttl=_EVAL_TTL, swr_ttl=_EVAL_SWR)
        return v if v != '__none__' else None
    except Exception:
        return _load_override_db(flag_id, user_id)


def _load_override_db(flag_id, user_id):
    from .models import FlagOverride
    o = FlagOverride.objects.filter(flag_id=flag_id, user_id=user_id).first()
    if o is None:
        return '__none__'  # cache the absence to avoid repeated SELECTs
    return o.value


# ─── Exposure recording ───────────────────────────────────────────────────

def _record_exposure(flag_name, user, anon_token, variant, source='rollout'):
    """Fire-and-forget exposure log. Failure here must NOT break the caller."""
    try:
        from .models import ExperimentExposure
        ExperimentExposure.objects.create(
            flag_name=flag_name,
            user_id=user.id if user and getattr(user, 'is_authenticated', False) else None,
            anon_token=(anon_token or '')[:64],
            variant=str(variant)[:80],
            context={'source': source},
        )
    except Exception as e:
        log.debug('exposure log failed for %s: %s', flag_name, e)
