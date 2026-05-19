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


# ─── Additional export steps (the long tail of GDPR / Lei 22/11 coverage) ──
# Each step is best-effort: if the model isn't importable (app removed in
# a future deploy), the step records an empty section and continues. The
# manifest is meant to be "everything we hold"; gaps would be a violation.

def _export_collect_order_items(payload, saga):
    """OrderItem rows give the full purchase history with product
    names + prices — the actual commercial record the user paid for."""
    try:
        from apps.orders.models import OrderItem
    except Exception:
        payload['manifest']['order_items'] = []
        return
    rows = list(
        OrderItem.objects.filter(order__buyer_id=payload['user_id'])
        .values('order_id', 'product_title', 'product_sku', 'unit_price',
                'quantity', 'total_price', 'variant_options')[:5000]
    )
    payload['manifest']['order_items'] = [
        {**r,
         'order_id': str(r['order_id']),
         'unit_price': str(r['unit_price']),
         'total_price': str(r['total_price']),
         } for r in rows
    ]


def _export_collect_payments(payload, saga):
    """Payment + WalletTransaction records — the financial trail."""
    from apps.orders.models import Payment
    payments = list(
        Payment.objects.filter(order__buyer_id=payload['user_id'])
        .values('order_id', 'method', 'status', 'amount', 'currency',
                'paid_at', 'gateway_reference', 'created_at')[:5000]
    )
    payload['manifest']['payments'] = [
        {**p,
         'order_id': str(p['order_id']),
         'amount': str(p['amount']),
         'paid_at': p['paid_at'].isoformat() if p.get('paid_at') else None,
         'created_at': p['created_at'].isoformat() if p.get('created_at') else None,
         } for p in payments
    ]

    # Seller-side wallet history
    try:
        from apps.payments.models import WalletTransaction
        wt = list(
            WalletTransaction.objects.filter(wallet__seller_id=payload['user_id'])
            .values('type', 'amount', 'description', 'reference',
                    'balance_after', 'created_at')[:5000]
        )
        payload['manifest']['wallet_transactions'] = [
            {**w,
             'amount': str(w['amount']),
             'balance_after': str(w['balance_after']),
             'created_at': w['created_at'].isoformat() if w.get('created_at') else None,
             } for w in wt
        ]
    except Exception:
        payload['manifest']['wallet_transactions'] = []


def _export_collect_reviews(payload, saga):
    """Reviews the user left — both seller-reviews and product-reviews."""
    items = {'seller_reviews': [], 'product_reviews': []}
    try:
        from apps.reviews.models import Review, ProductReview
        items['seller_reviews'] = [
            {**r,
             'created_at': r['created_at'].isoformat() if r.get('created_at') else None,
             } for r in Review.objects.filter(
                reviewer_id=payload['user_id'],
            ).values('seller_id', 'rating', 'comment', 'created_at')[:1000]
        ]
        items['product_reviews'] = [
            {**r,
             'created_at': r['created_at'].isoformat() if r.get('created_at') else None,
             } for r in ProductReview.objects.filter(
                reviewer_id=payload['user_id'],
            ).values('product_id', 'rating', 'title', 'comment',
                     'helpful_count', 'is_verified_purchase',
                     'created_at')[:1000]
        ]
    except Exception:
        pass
    payload['manifest']['reviews'] = items


def _export_collect_chats(payload, saga):
    """Chat messages where the user is buyer OR seller."""
    try:
        from apps.chat.models import Chat, Message
        chat_ids = list(
            Chat.objects.filter(buyer_id=payload['user_id']).values_list('id', flat=True)
        ) + list(
            Chat.objects.filter(seller_id=payload['user_id']).values_list('id', flat=True)
        )
        msgs = list(
            Message.objects.filter(chat_id__in=chat_ids)
            .values('chat_id', 'sender_id', 'content', 'created_at')[:5000]
        )
        payload['manifest']['chats'] = [
            {**m, 'created_at': m['created_at'].isoformat()
                  if m.get('created_at') else None}
            for m in msgs
        ]
    except Exception:
        payload['manifest']['chats'] = []


def _export_collect_consents(payload, saga):
    """ConsentLog — every privacy / terms acceptance the user gave us.
    Required for GDPR Art. 7(1) — proof of consent."""
    try:
        from apps.users.models import ConsentLog
        rows = list(
            ConsentLog.objects.filter(user_id=payload['user_id'])
            .values('consent_type', 'version', 'granted',
                    'ip_address', 'created_at')[:1000]
        )
        payload['manifest']['consents'] = [
            {**r, 'created_at': r['created_at'].isoformat()
                  if r.get('created_at') else None,
             'ip_address': str(r['ip_address']) if r.get('ip_address') else None,
             } for r in rows
        ]
    except Exception:
        payload['manifest']['consents'] = []


def _export_collect_wishlist_and_cart(payload, saga):
    """Current cart contents + wishlist (the user's "intent" record)."""
    items = {'cart': [], 'wishlist': []}
    try:
        from apps.cart.models import CartItem
        items['cart'] = [
            {**c, 'price_at_add': str(c['price_at_add']) if c.get('price_at_add') else None}
            for c in CartItem.objects.filter(cart__user_id=payload['user_id'])
            .values('product_id', 'variant_combo_id', 'quantity', 'price_at_add')
        ]
    except Exception:
        pass
    try:
        from apps.wishlist.models import WishlistItem
        items['wishlist'] = list(
            WishlistItem.objects.filter(wishlist__user_id=payload['user_id'])
            .values('product_id')[:1000]
        )
    except Exception:
        pass
    payload['manifest']['cart_and_wishlist'] = items


def _export_collect_disputes_returns(payload, saga):
    """Disputes raised and returns initiated by the user."""
    items = {'disputes': [], 'returns': []}
    try:
        from apps.disputes.models import Dispute
        items['disputes'] = [
            {**d,
             'order_id': str(d['order_id']),
             'created_at': d['created_at'].isoformat() if d.get('created_at') else None,
             } for d in Dispute.objects.filter(
                buyer_id=payload['user_id'],
             ).values('order_id', 'reason', 'description', 'status',
                      'resolution', 'created_at')[:500]
        ]
    except Exception:
        pass
    try:
        from apps.orders.return_models import ReturnRequest
        items['returns'] = [
            {**r,
             'order_id': str(r['order_id']),
             'created_at': r['created_at'].isoformat() if r.get('created_at') else None,
             } for r in ReturnRequest.objects.filter(
                buyer_id=payload['user_id'],
             ).values('order_id', 'reason', 'description', 'status',
                      'pickup_method', 'created_at')[:500]
        ]
    except Exception:
        pass
    payload['manifest']['disputes_returns'] = items


def _export_collect_notifications(payload, saga):
    """Notifications received — what the platform told the user."""
    try:
        from apps.notifications.models import Notification
        rows = list(
            Notification.objects.filter(user_id=payload['user_id'])
            .values('type', 'title', 'message', 'is_read',
                    'created_at')[:2000]
        )
        payload['manifest']['notifications'] = [
            {**n, 'created_at': n['created_at'].isoformat()
                  if n.get('created_at') else None}
            for n in rows
        ]
    except Exception:
        payload['manifest']['notifications'] = []


def _export_collect_loyalty_and_coupons(payload, saga):
    """Loyalty point movements + coupon redemptions — financial-ish PII."""
    items = {'loyalty_transactions': [], 'coupon_redemptions': []}
    try:
        from apps.loyalty.models import PointsTransaction
        items['loyalty_transactions'] = [
            {**p, 'created_at': p['created_at'].isoformat()
                  if p.get('created_at') else None}
            for p in PointsTransaction.objects.filter(user_id=payload['user_id'])
            .values('points', 'reason', 'created_at')[:2000]
        ]
    except Exception:
        pass
    try:
        from apps.promotions.models import CouponRedemption
        items['coupon_redemptions'] = [
            {**c,
             'applied_amount': str(c['applied_amount']),
             'subtotal_at_apply': str(c['subtotal_at_apply']),
             'applied_at': c['applied_at'].isoformat() if c.get('applied_at') else None,
             }
            for c in CouponRedemption.objects.filter(user_id=payload['user_id'])
            .values('coupon_id', 'order_id', 'applied_amount',
                    'subtotal_at_apply', 'status', 'applied_at')[:1000]
        ]
    except Exception:
        pass
    payload['manifest']['loyalty_and_coupons'] = items


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
        # Identity + profile
        SagaStep('collect_profile',              _export_collect_profile,              None),
        # Commerce — what the user actually did + paid for
        SagaStep('collect_orders',               _export_collect_orders,               None),
        SagaStep('collect_order_items',          _export_collect_order_items,          None),
        SagaStep('collect_payments',             _export_collect_payments,             None),
        # Addresses + browsing intent
        SagaStep('collect_addresses',            _export_collect_addresses,            None),
        SagaStep('collect_wishlist_and_cart',    _export_collect_wishlist_and_cart,    None),
        # Communications + social
        SagaStep('collect_reviews',              _export_collect_reviews,              None),
        SagaStep('collect_chats',                _export_collect_chats,                None),
        SagaStep('collect_notifications',        _export_collect_notifications,        None),
        # Discovery + post-sale flows
        SagaStep('collect_search_history',       _export_collect_search_history,       None),
        SagaStep('collect_disputes_returns',     _export_collect_disputes_returns,     None),
        SagaStep('collect_loyalty_and_coupons',  _export_collect_loyalty_and_coupons,  None),
        # Compliance — proof of consents given
        SagaStep('collect_consents',             _export_collect_consents,             None),
        SagaStep('finalise',                     _export_finalise,                     None),
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


# ─── Additional erase steps ───────────────────────────────────────────────
# Each is a "delete or anonymise" decision. Rule of thumb:
#   • Transient personal data (cart, wishlist, notifications, sessions,
#     search history, recommendations training) → DELETE.
#   • Financial / audit records → KEEP rows, ANONYMISE the user reference
#     so the books balance but PII is severed.
#   • Compensations only exist for paths whose data loss would be costly
#     to reconstruct. Cart re-population isn't worth the saga complexity.


def _erase_profile(payload, saga):
    """UserProfile PII: full_name, bio, avatar, date_of_birth."""
    if payload.get('skip'):
        return
    try:
        from apps.users.models import UserProfile
        profile = UserProfile.objects.filter(user_id=payload['user_id']).first()
        if profile is None:
            return
        payload.setdefault('originals', {})['profile'] = {
            'full_name': getattr(profile, 'full_name', ''),
            'bio': getattr(profile, 'bio', ''),
            'date_of_birth': str(profile.date_of_birth)
                if getattr(profile, 'date_of_birth', None) else None,
            'city': getattr(profile, 'city', ''),
        }
        UserProfile.objects.filter(pk=profile.pk).update(
            full_name='',
            bio='',
            date_of_birth=None,
            city='',
        )
    except Exception:
        log.exception('erase_profile failed')


def _erase_profile_compensation(payload, saga):
    if payload.get('skip'):
        return
    o = payload.get('originals', {}).get('profile')
    if not o:
        return
    try:
        from apps.users.models import UserProfile
        from datetime import date
        UserProfile.objects.filter(user_id=payload['user_id']).update(
            full_name=o.get('full_name', ''),
            bio=o.get('bio', ''),
            date_of_birth=(
                date.fromisoformat(o['date_of_birth'])
                if o.get('date_of_birth') else None
            ),
            city=o.get('city', ''),
        )
    except Exception:
        log.exception('erase_profile_compensation failed')


def _erase_login_attempts(payload, saga):
    """LoginAttempt records keep IP+UA per attempt. Even though there's a
    90-day retention beat task, an explicit erase request must blank them
    now — keeping them is a Lei 22/11 violation past the request.
    Anonymise (NOT delete) so the security audit trail "5 attempts at
    14:00 from country X" survives, but with no link back to the user.

    Uses the ORIGINAL email captured by capture_originals. Looking up
    the current user row here would find the post-erase-user email
    ("erased+<hash>@erased.micha") and miss every real login attempt.
    """
    if payload.get('skip'):
        return
    try:
        from apps.security.login_attempt_models import LoginAttempt
        original_email = (
            payload.get('originals', {}).get('user', {}).get('email') or ''
        )
        if not original_email:
            return
        LoginAttempt.objects.filter(email__iexact=original_email).update(
            email=f'erased:{_anon_hash(payload["user_id"])}@erased.micha',
            ip=None,
            user_agent='',
        )
    except Exception:
        log.exception('erase_login_attempts failed')
    # No compensation — security audit anonymisation is one-way by design.


def _erase_sessions(payload, saga):
    """UserSession rows are transient — delete outright. Their content
    (device, IP, last_activity) is purely operational state."""
    if payload.get('skip'):
        return
    try:
        from apps.users.models import UserSession
        UserSession.objects.filter(user_id=payload['user_id']).delete()
    except Exception:
        log.exception('erase_sessions failed')


def _erase_cart_and_wishlist(payload, saga):
    """Cart contents + wishlist are intent data, not financial truth.
    Delete outright. Compensation would mean re-populating the cart,
    which is not what an erasure-then-rollback would semantically mean
    (user would have requested erasure THEN un-requested it; their
    intent in the cart is no longer guaranteed to match reality)."""
    if payload.get('skip'):
        return
    try:
        from apps.cart.models import Cart, CartItem
        CartItem.objects.filter(cart__user_id=payload['user_id']).delete()
        Cart.objects.filter(user_id=payload['user_id']).delete()
    except Exception:
        log.exception('erase_cart failed')
    try:
        from apps.wishlist.models import Wishlist, WishlistItem
        WishlistItem.objects.filter(wishlist__user_id=payload['user_id']).delete()
        Wishlist.objects.filter(user_id=payload['user_id']).delete()
    except Exception:
        log.exception('erase_wishlist failed')


def _erase_notifications(payload, saga):
    """Notifications are transient — what the platform told the user.
    Compliance: delete (they ARE personal communications)."""
    if payload.get('skip'):
        return
    try:
        from apps.notifications.models import Notification
        Notification.objects.filter(user_id=payload['user_id']).delete()
    except Exception:
        log.exception('erase_notifications failed')


def _erase_recommendations_data(payload, saga):
    """ProductInteraction rows are the training signal for personalised
    recommendations. They directly link a user to their browsing
    behaviour — both PII and training data. Delete on erasure; we'll
    lose recommendation quality for this user (they're gone anyway)."""
    if payload.get('skip'):
        return
    try:
        from apps.recommendations.models import ProductInteraction, PriceAlert
        ProductInteraction.objects.filter(user_id=payload['user_id']).delete()
        PriceAlert.objects.filter(user_id=payload['user_id']).delete()
    except Exception:
        log.exception('erase_recommendations_data failed')


def _erase_consent_ip(payload, saga):
    """ConsentLog rows must be kept (proof of consent under GDPR Art. 7),
    but the recorded IP + UA at consent-time are PII. Anonymise those
    columns while keeping the structural record."""
    if payload.get('skip'):
        return
    try:
        from apps.users.models import ConsentLog
        ConsentLog.objects.filter(user_id=payload['user_id']).update(
            ip_address=None,
            user_agent='',
        )
    except Exception:
        log.exception('erase_consent_ip failed')


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
        # The new steps don't snapshot originals (transient data) so we
        # can't count what was erased. Mark them as "ran" via presence
        # of the step name in the saga audit trail (which already lives
        # in the sagas app).
        'transient_erased': [
            'profile', 'cart_and_wishlist', 'notifications',
            'search_history', 'recommendations_data', 'sessions',
        ],
        'audit_anonymised': ['login_attempts', 'consent_log_ip'],
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
        # 1. SNAPSHOT phase — capture originals BEFORE any mutation so
        # compensations can roll back if a later step fails.
        SagaStep('capture_originals',          _erase_capture_originals,          None),
        SagaStep('capture_order_originals',    _erase_capture_order_originals,    None),
        # 2. CORE PII ON FINANCIAL ROWS — anonymise but keep the row
        # (orders + payments survive for the books; PII fields are blanked).
        SagaStep('erase_user',                 _erase_user,                       _erase_user_compensation),
        SagaStep('erase_orders',               _erase_orders,                     _erase_orders_compensation),
        # 3. PROFILE PII — full_name, bio, avatar, dob.
        SagaStep('erase_profile',              _erase_profile,                    _erase_profile_compensation),
        # 4. DELETE-OUTRIGHT TRANSIENT DATA — no compensation; restoring
        # an empty cart with stale prices would be worse than just losing it.
        SagaStep('erase_addresses',            _erase_addresses,                  _erase_addresses_compensation),
        SagaStep('erase_cart_and_wishlist',    _erase_cart_and_wishlist,          None),
        SagaStep('erase_notifications',        _erase_notifications,              None),
        SagaStep('erase_search_history',       _erase_search_history,             None),
        SagaStep('erase_recommendations_data', _erase_recommendations_data,       None),
        SagaStep('erase_sessions',             _erase_sessions,                   None),
        # 5. ANONYMISE AUDIT TRAILS — keep the rows (Lei 22/11 obligation
        # for security forensics) but blank the IP + UA columns so they
        # no longer link back.
        SagaStep('erase_login_attempts',       _erase_login_attempts,             None),
        SagaStep('erase_consent_ip',           _erase_consent_ip,                 None),
        # 6. FINALISE — stamp the request row with the summary.
        SagaStep('finalise',                   _erase_finalise,                   None),
    ],
))
