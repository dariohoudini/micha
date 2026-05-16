"""
apps/data_rights/saga_defs.py

Two sagas, one per data-subject right:

  * data_export   — gather everything we hold about this user into a
                    structured JSON manifest. Read-only; no compensations
                    needed (we just don't keep the manifest if a step fails).

  * data_erase    — anonymise PII across all tables that hold it. Each step
                    has a compensation that restores the original values
                    (from the request payload's "before" snapshot) if a
                    later step fails. NEVER deletes financial / audit rows —
                    just severs them from identifying information.

Auto-discovered by the sagas app on Django startup.
"""
from __future__ import annotations
import hashlib
import logging
from django.utils import timezone

from apps.sagas.registry import SagaDef, SagaStep, register

log = logging.getLogger(__name__)


# ─── EXPORT ────────────────────────────────────────────────────────────────

def _export_collect_profile(payload, saga):
    """Collect User + Profile fields."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u = User.objects.filter(pk=payload['user_id']).first()
    if not u:
        payload.setdefault('manifest', {})['profile'] = {'error': 'user_not_found'}
        return
    profile = {
        'id': u.id,
        'email': u.email,
        'phone': str(u.phone) if u.phone else None,
        'date_joined': u.date_joined.isoformat() if getattr(u, 'date_joined', None) else None,
        'last_login': u.last_login.isoformat() if u.last_login else None,
        'is_email_verified': u.is_email_verified,
        'is_phone_verified': u.is_phone_verified,
        'loyalty_points': u.loyalty_points,
        'store_credit': str(u.store_credit),
        'referral_code': u.referral_code,
    }
    try:
        p = u.profile
        profile['profile'] = {
            'full_name': getattr(p, 'full_name', ''),
            'bio': getattr(p, 'bio', ''),
            'avatar': str(p.avatar) if getattr(p, 'avatar', None) else None,
        }
    except Exception:
        pass
    payload.setdefault('manifest', {})['profile'] = profile


def _export_collect_orders(payload, saga):
    from apps.orders.models import Order
    orders = list(
        Order.objects.filter(buyer_id=payload['user_id'])
        .values('id', 'status', 'payment_status', 'subtotal',
                'shipping_cost', 'discount', 'total', 'created_at',
                'shipping_name', 'shipping_phone', 'shipping_address',
                'shipping_city', 'shipping_province', 'shipping_country')[:5000]
    )
    payload['manifest']['orders'] = [
        {**o,
         'id': str(o['id']),
         'subtotal': str(o['subtotal']),
         'shipping_cost': str(o['shipping_cost']),
         'discount': str(o['discount']),
         'total': str(o['total']),
         'created_at': o['created_at'].isoformat() if o.get('created_at') else None,
         'shipping_phone': str(o['shipping_phone']) if o['shipping_phone'] else '',
         'shipping_address': str(o['shipping_address']) if o['shipping_address'] else '',
         }
        for o in orders
    ]


def _export_collect_addresses(payload, saga):
    try:
        from apps.shipping.models import ShippingAddress
    except Exception:
        payload['manifest']['addresses'] = []
        return
    rows = list(
        ShippingAddress.objects.filter(user_id=payload['user_id'])
        .values('label', 'full_name', 'phone', 'address_line', 'city',
                'province', 'postal_code', 'country', 'created_at')
    )
    payload['manifest']['addresses'] = [
        {**r,
         'phone': str(r['phone']) if r.get('phone') else '',
         'address_line': str(r['address_line']) if r.get('address_line') else '',
         'created_at': r['created_at'].isoformat() if r.get('created_at') else None,
         }
        for r in rows
    ]


def _export_collect_search_history(payload, saga):
    try:
        from apps.search.models import SearchHistory
    except Exception:
        payload['manifest']['search_history'] = []
        return
    rows = list(
        SearchHistory.objects.filter(user_id=payload['user_id'])
        .values('query', 'result_count', 'searched_at')[:1000]
    )
    payload['manifest']['search_history'] = [
        {**r, 'searched_at': r['searched_at'].isoformat() if r.get('searched_at') else None}
        for r in rows
    ]


def _export_finalise(payload, saga):
    """Persist the manifest summary on the DataSubjectRequest row."""
    from .models import DataSubjectRequest, RequestStatus
    rid = payload['request_id']
    manifest = payload.get('manifest', {})
    sizes = {k: (len(v) if isinstance(v, list) else 1) for k, v in manifest.items()}
    DataSubjectRequest.objects.filter(pk=rid).update(
        payload={'manifest': manifest, 'summary': sizes},
        status=RequestStatus.COMPLETED,
        completed_at=timezone.now(),
    )


register(SagaDef(
    name='data_export',
    max_lifetime_seconds=60 * 60 * 24,  # 24h — best effort
    steps=[
        SagaStep('collect_profile',         _export_collect_profile,         None),
        SagaStep('collect_orders',          _export_collect_orders,          None),
        SagaStep('collect_addresses',       _export_collect_addresses,       None),
        SagaStep('collect_search_history',  _export_collect_search_history,  None),
        SagaStep('finalise',                _export_finalise,                None),
    ],
))


# ─── ERASE ─────────────────────────────────────────────────────────────────
# Anonymisation strategy: PII fields → "erased:<hash>" placeholder. Hash is
# derived from user_id + a salt so the anonymised value is deterministic
# (helps audit reconciliation) but non-reversible. Financial / audit rows
# (Order, LedgerEntry, ReturnEvent) are NEVER deleted — only their PII
# columns get replaced. That preserves the books while honouring erasure.

def _anon_hash(user_id) -> str:
    """Deterministic non-reversible placeholder. Used so e.g. an order's
    shipping_name and a paired address point to the same anonymised value."""
    salt = 'micha-erasure-v1'
    return hashlib.sha256(f'{salt}:{user_id}'.encode()).hexdigest()[:16]


def _erase_capture_originals(payload, saga):
    """Snapshot the original PII values for use by compensations. Must run
    FIRST so the saga can roll back if a later step fails."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u = User.objects.filter(pk=payload['user_id']).only(
        'email', 'phone', 'fcm_token', 'google_id', 'facebook_id', 'apple_id',
    ).first()
    if u is None:
        # Nothing to erase — caller will see this as a no-op completion.
        payload['skip'] = True
        return
    payload['originals'] = {
        'user': {
            'email': u.email,
            'phone': str(u.phone) if u.phone else None,
            'fcm_token': u.fcm_token,
            'google_id': u.google_id,
            'facebook_id': u.facebook_id,
            'apple_id': u.apple_id,
        },
    }


def _erase_user(payload, saga):
    if payload.get('skip'):
        return
    from django.contrib.auth import get_user_model
    User = get_user_model()
    uid = payload['user_id']
    placeholder = _anon_hash(uid)
    User.objects.filter(pk=uid).update(
        email=f'erased+{placeholder}@erased.micha',
        phone=None,
        fcm_token=None,
        google_id=None,
        facebook_id=None,
        apple_id=None,
        is_active=False,
        is_deleted=True,
    )


def _erase_user_compensation(payload, saga):
    if payload.get('skip'):
        return
    from django.contrib.auth import get_user_model
    User = get_user_model()
    o = payload.get('originals', {}).get('user', {})
    if not o:
        return  # nothing snapshotted; can't restore
    User.objects.filter(pk=payload['user_id']).update(
        email=o.get('email'),
        phone=o.get('phone'),
        fcm_token=o.get('fcm_token'),
        google_id=o.get('google_id'),
        facebook_id=o.get('facebook_id'),
        apple_id=o.get('apple_id'),
        is_active=True,
        is_deleted=False,
    )


def _erase_capture_order_originals(payload, saga):
    if payload.get('skip'):
        return
    from apps.orders.models import Order
    rows = list(
        Order.objects.filter(buyer_id=payload['user_id']).values(
            'id', 'shipping_name', 'shipping_phone', 'shipping_address',
        )
    )
    # Stringify encrypted fields so they survive JSON serialisation
    payload['originals']['orders'] = [
        {
            'id': str(r['id']),
            'shipping_name': r['shipping_name'],
            'shipping_phone': str(r['shipping_phone']) if r['shipping_phone'] else '',
            'shipping_address': str(r['shipping_address']) if r['shipping_address'] else '',
        }
        for r in rows
    ]


def _erase_orders(payload, saga):
    """Order rows stay (financial truth) but shipping PII is anonymised."""
    if payload.get('skip'):
        return
    from apps.orders.models import Order
    placeholder = _anon_hash(payload['user_id'])
    Order.objects.filter(buyer_id=payload['user_id']).update(
        shipping_name=f'erased:{placeholder}',
        shipping_phone='',
        shipping_address='',
    )


def _erase_orders_compensation(payload, saga):
    if payload.get('skip'):
        return
    from apps.orders.models import Order
    for r in payload.get('originals', {}).get('orders', []):
        Order.objects.filter(pk=r['id']).update(
            shipping_name=r['shipping_name'] or '',
            shipping_phone=r['shipping_phone'] or '',
            shipping_address=r['shipping_address'] or '',
        )


def _erase_addresses(payload, saga):
    """ShippingAddress rows belong to the user and aren't referenced by orders;
    safe to fully delete after capturing originals."""
    if payload.get('skip'):
        return
    try:
        from apps.shipping.models import ShippingAddress
    except Exception:
        return
    rows = list(
        ShippingAddress.objects.filter(user_id=payload['user_id']).values(
            'id', 'label', 'full_name', 'phone', 'address_line',
            'city', 'province', 'postal_code', 'country', 'is_default',
        )
    )
    payload['originals']['addresses'] = [
        {**r, 'phone': str(r['phone']) if r.get('phone') else '',
         'address_line': str(r['address_line']) if r.get('address_line') else ''}
        for r in rows
    ]
    ShippingAddress.objects.filter(user_id=payload['user_id']).delete()


def _erase_addresses_compensation(payload, saga):
    if payload.get('skip'):
        return
    try:
        from apps.shipping.models import ShippingAddress
    except Exception:
        return
    for r in payload.get('originals', {}).get('addresses', []):
        try:
            ShippingAddress.objects.create(
                user_id=payload['user_id'],
                label=r.get('label', ''),
                full_name=r.get('full_name', ''),
                phone=r.get('phone', ''),
                address_line=r.get('address_line', ''),
                city=r.get('city', ''),
                province=r.get('province', ''),
                postal_code=r.get('postal_code', ''),
                country=r.get('country', ''),
                is_default=r.get('is_default', False),
            )
        except Exception:
            pass


def _erase_search_history(payload, saga):
    if payload.get('skip'):
        return
    try:
        from apps.search.models import SearchHistory
    except Exception:
        return
    SearchHistory.objects.filter(user_id=payload['user_id']).delete()
    # No compensation — search history is non-financial and safe to lose if
    # the saga later flips. (Compensating would mean reinserting rows we
    # already considered ephemeral.)


def _erase_finalise(payload, saga):
    """Stamp the request row with the summary."""
    if payload.get('skip'):
        # Update the request row even on no-op so the caller sees status
        from .models import DataSubjectRequest, RequestStatus
        DataSubjectRequest.objects.filter(pk=payload['request_id']).update(
            status=RequestStatus.COMPLETED,
            completed_at=timezone.now(),
            payload={'note': 'user_not_found'},
        )
        return
    from .models import DataSubjectRequest, RequestStatus
    summary = {
        'placeholder': _anon_hash(payload['user_id']),
        'orders_anonymised': len(payload.get('originals', {}).get('orders', [])),
        'addresses_deleted': len(payload.get('originals', {}).get('addresses', [])),
    }
    DataSubjectRequest.objects.filter(pk=payload['request_id']).update(
        status=RequestStatus.COMPLETED,
        completed_at=timezone.now(),
        payload={'summary': summary},
    )


register(SagaDef(
    name='data_erase',
    max_lifetime_seconds=60 * 60 * 24,  # 24h to actually run; SLA window of 30d is separate
    steps=[
        SagaStep('capture_originals',       _erase_capture_originals,       None),
        SagaStep('capture_order_originals', _erase_capture_order_originals, None),
        SagaStep('erase_user',              _erase_user,                    _erase_user_compensation),
        SagaStep('erase_orders',            _erase_orders,                  _erase_orders_compensation),
        SagaStep('erase_addresses',         _erase_addresses,               _erase_addresses_compensation),
        SagaStep('erase_search_history',    _erase_search_history,          None),
        SagaStep('finalise',                _erase_finalise,                None),
    ],
))
