"""
apps/users/bulk_handlers.py

Bulk admin operations on User rows. Auto-discovered by the bulk_ops app.
"""
from apps.bulk_ops.registry import register, BulkHandler


def _bulk_suspend_user(item_ref, params, request_user):
    """Suspend one user. Returns dict on success; idempotent (already-
    suspended users skip cleanly so a retry doesn't error)."""
    from django.contrib.auth import get_user_model
    User = get_user_model()

    u = User.objects.filter(pk=item_ref).first()
    if u is None:
        raise ValueError(f'user {item_ref} not found')

    if not u.is_active:
        return {'skipped': True, 'reason': 'already_suspended'}

    u.is_active = False
    u.save(update_fields=['is_active'])
    return {'suspended': True, 'email': u.email}


def _bulk_activate_user(item_ref, params, request_user):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u = User.objects.filter(pk=item_ref).first()
    if u is None:
        raise ValueError(f'user {item_ref} not found')
    if u.is_active:
        return {'skipped': True, 'reason': 'already_active'}
    u.is_active = True
    u.save(update_fields=['is_active'])
    return {'activated': True, 'email': u.email}


register(BulkHandler(
    name='users.bulk_suspend',
    fn=_bulk_suspend_user,
    audit_action='suspend_user',
    description='Suspend (is_active=False) a list of users. Idempotent.',
))

register(BulkHandler(
    name='users.bulk_activate',
    fn=_bulk_activate_user,
    audit_action='activate_user',
    description='Reactivate (is_active=True) a list of users. Idempotent.',
))
