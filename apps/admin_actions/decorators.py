"""
apps/admin_actions/decorators.py

@audit_admin_action — drop on any APIView method that performs a privileged
operation. Logs an AdminActionLog row after the handler returns 2xx; skipped
on non-2xx (we don't audit attempts that were refused by validation).

Resolution rules:
  action       — explicit string passed to the decorator (e.g. 'remove_product')
  target       — by default the URL kwarg matching ``target_kwarg``
                 (e.g. user_id, order_id), looked up via target_lookup if
                 provided. Falls back to the kwarg's raw value.
  note         — pulled from request.data['admin_note'] (or 'note') if present
  metadata     — caller-supplied dict plus the action's HTTP method+path

NEVER raises — audit failure must not break a privileged action. Failures
go to log at WARNING level so they surface but don't break workflows.
"""
from __future__ import annotations
import functools
import logging

from rest_framework.response import Response

log = logging.getLogger(__name__)


def audit_admin_action(action, *, target_kwarg: str = '', target_lookup=None,
                      note_key: str = 'admin_note',
                      extra_metadata: dict | None = None):
    """Decorator factory.

    Args:
      action:        Either a static string identifier, OR a callable
                     (request, kwargs) -> str for endpoints that dispatch
                     multiple action types based on body content
                     (e.g. AdminUserActionView reads request.data['action']
                     to pick suspend|activate|ban).
      target_kwarg:  URL kwarg name to look up the target object by.
      target_lookup: callable(value) -> object for richer target_repr.
      note_key:      key in request.data to pull the human note from.
      extra_metadata: static dict merged into the audit row's metadata.
    """
    def decorator(view_method):
        @functools.wraps(view_method)
        def wrapper(self, request, *args, **kwargs):
            response = view_method(self, request, *args, **kwargs)
            status = getattr(response, 'status_code', 200)
            if not (200 <= status < 300):
                return response

            try:
                resolved = action(request, kwargs) if callable(action) else action
                if not resolved:
                    return response  # caller declined to audit this branch
                _record(request, kwargs, resolved, target_kwarg, target_lookup,
                        note_key, extra_metadata)
            except Exception as e:
                log.warning('audit_admin_action failed: %s', e)
            return response
        return wrapper
    return decorator


def _record(request, kwargs, action, target_kwarg, target_lookup, note_key, extra_metadata):
    from .models import AdminActionLog

    # Resolve target
    target = None
    target_value = kwargs.get(target_kwarg) if target_kwarg else None
    if target_value is not None and target_lookup is not None:
        try:
            target = target_lookup(target_value)
        except Exception:
            target = None
    if target is None:
        # Fallback: synthetic object with .pk so AdminActionLog.log can stringify.
        class _Synthetic:
            def __init__(self, v): self.pk = v
            def __str__(self): return str(self.pk) if self.pk is not None else ''
        target = _Synthetic(target_value)

    note = ''
    try:
        note = (request.data.get(note_key) or '').strip()[:2000]
    except Exception:
        pass

    metadata = dict(extra_metadata or {})
    metadata.update({
        'method': request.method,
        'path': getattr(request, 'path', ''),
    })

    AdminActionLog.log(
        request=request, action=action, target=target,
        note=note, metadata=metadata,
    )
