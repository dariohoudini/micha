"""
Buyer experience services.

Chapter → function map:
  CH2   set_gift_options / gift_packing_slip_data
  CH3   create_subscription / process_due_subscriptions / pause / skip /
        change_frequency / cancel
  CH4   record_price_change / price_history / validate_original_price
        (anti-fake-discount — the "make it better")
  CH7   ask_question / answer_question / expire_questions
  CH8   create_bulk_inquiry / quote_inquiry / accept_quote
  CH10  save_comparison
  CH12  reorder_check
  CH14  watch_price / check_price_drops
  CH18  verify_age / requires_age_gate / is_age_cleared
  CH23  account_summary
  CH24  snapshot_kpis
"""
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import (
    AgeVerification, BulkInquiry, BuyerExperienceEvent,
    BuyerExperienceKpiSnapshot, OrderGiftOptions, PrePurchaseQuestion,
    ProductPriceHistory, ProductSubscription, RestrictedCategory,
    SavedComparison, WishlistPriceWatch,
)

GIFT_WRAP_FEES = {'none': 0, 'basic': 50_000, 'premium': 150_000}  # cents
ORIGINAL_PRICE_WINDOW_DAYS = 30
QUESTION_EXPIRY_DAYS = 7
QUESTION_ESCALATION_HOURS = 48
BULK_QUOTE_TTL_HOURS = 48
MAX_SAVED_COMPARISON_PRODUCTS = 4
AGE_GATE_CACHE_DAYS = 30
SUBSCRIPTION_MAX_FAILURES = 1   # pause after first payment failure (doc CH3)


# ──────────────────────────────────────────────────────────────────────
# CH2 — Gift options
# ──────────────────────────────────────────────────────────────────────

def set_gift_options(buyer, *, order_id, is_gift, gift_message='',
                     hide_price=True, gift_wrap='none'):
    fee = GIFT_WRAP_FEES.get(gift_wrap, 0) if is_gift else 0
    opts, _ = OrderGiftOptions.objects.update_or_create(
        order_id=order_id,
        defaults={'buyer': buyer, 'is_gift': is_gift,
                  'gift_message': gift_message[:300],
                  'hide_price': hide_price if is_gift else False,
                  'gift_wrap': gift_wrap if is_gift else 'none',
                  'gift_wrap_fee_cents': fee})
    BuyerExperienceEvent.log('gift_options_set', actor=buyer, order_id=order_id,
                             is_gift=is_gift, wrap=gift_wrap)
    return opts


def gift_packing_slip_data(order_id):
    """Packing-slip data with prices replaced by '---' when hide_price."""
    opts = OrderGiftOptions.objects.filter(order_id=order_id).first()
    hide = bool(opts and opts.is_gift and opts.hide_price)
    return {'hide_price': hide,
            'gift_message': opts.gift_message if opts else '',
            'price_placeholder': '---' if hide else None,
            'footer': 'Comprado em MICHA Express'}


# ──────────────────────────────────────────────────────────────────────
# CH3 — Subscribe & Save
# ──────────────────────────────────────────────────────────────────────

def create_subscription(buyer, *, product_id, sku_id='', seller=None,
                        quantity=1, frequency_days=30, discount_pct=8,
                        payment_method='wallet', delivery_address_id=''):
    if payment_method == 'cod':
        raise ValueError('subscriptions require prepaid (wallet/card), not COD')
    sub = ProductSubscription.objects.create(
        buyer=buyer, product_id=product_id, sku_id=sku_id, seller=seller,
        quantity=quantity, frequency_days=frequency_days,
        discount_pct=Decimal(str(discount_pct)),
        next_order_date=timezone.now().date() + timedelta(days=frequency_days),
        payment_method=payment_method, delivery_address_id=delivery_address_id)
    BuyerExperienceEvent.log('subscription_created', actor=buyer,
                             product_id=product_id, frequency=frequency_days)
    return sub


def process_due_subscriptions(run_date=None):
    """Daily job (doc CH3): place orders for subscriptions due today."""
    run_date = run_date or timezone.now().date()
    placed = oos = failed = 0
    for sub in ProductSubscription.objects.filter(
            status='active', next_order_date=run_date):
        ok, reason = _place_subscription_order(sub)
        if ok:
            placed += 1
        elif reason == 'oos':
            oos += 1
            sub.next_order_date = run_date + timedelta(days=3)  # retry in 3d
            sub.save(update_fields=['next_order_date'])
        else:
            failed += 1
            sub.consecutive_failures += 1
            if sub.consecutive_failures >= SUBSCRIPTION_MAX_FAILURES:
                sub.status = 'paused'   # pause, never cancel (doc CH3)
            sub.save(update_fields=['consecutive_failures', 'status'])
    return {'placed': placed, 'oos': oos, 'failed': failed}


@transaction.atomic
def _place_subscription_order(sub):
    # Stock check (bridge to stock_engine).
    try:
        from apps.stock_engine.models import InventorySku
        if sub.sku_id:
            sku = InventorySku.objects.filter(id=sub.sku_id).first()
            if sku and sku.available_quantity < sub.quantity:
                return False, 'oos'
    except Exception:
        pass
    # Current price (bridge); apply subscription discount.
    base = _current_price_cents(sub.product_id, sub.sku_id)
    discounted = int(base * (1 - sub.discount_pct / 100)) * sub.quantity
    # Charge (bridge to wallet); on failure → caller pauses.
    try:
        from apps.payments_angola import services as pa
        if sub.payment_method == 'wallet':
            pa.wallet_debit(sub.buyer, amount_cents=discounted,
                            reference_type='order_payment',
                            reference_id=str(sub.id),
                            idempotency_key=f'sub:{sub.id}:{sub.next_order_date}')
    except Exception:
        return False, 'payment_failed'
    sub.next_order_date = sub.next_order_date + timedelta(days=sub.frequency_days)
    sub.total_orders += 1
    sub.total_spent_cents += discounted
    sub.consecutive_failures = 0
    sub.save(update_fields=['next_order_date', 'total_orders',
                            'total_spent_cents', 'consecutive_failures'])
    BuyerExperienceEvent.log('subscription_order_placed', actor=sub.buyer,
                             subscription_id=str(sub.id), amount=discounted)
    return True, 'placed'


def _current_price_cents(product_id, sku_id=''):
    try:
        from apps.products.models import Product
        p = Product.objects.filter(id=product_id).first()
        if p:
            return int(Decimal(str(p.price)) * 100)
    except Exception:
        pass
    return 0


def pause_subscription(sub):
    sub.status = 'paused'
    sub.save(update_fields=['status'])
    return sub


def resume_subscription(sub):
    sub.status = 'active'
    if sub.next_order_date < timezone.now().date():
        sub.next_order_date = timezone.now().date() + timedelta(
            days=sub.frequency_days)
    sub.save(update_fields=['status', 'next_order_date'])
    return sub


def skip_next(sub):
    sub.next_order_date = sub.next_order_date + timedelta(
        days=sub.frequency_days)
    sub.save(update_fields=['next_order_date'])
    return sub


def change_frequency(sub, frequency_days):
    sub.frequency_days = frequency_days
    sub.next_order_date = timezone.now().date() + timedelta(days=frequency_days)
    sub.save(update_fields=['frequency_days', 'next_order_date'])
    return sub


def cancel_subscription(sub):
    sub.status = 'cancelled'
    sub.save(update_fields=['status'])
    return sub


# ──────────────────────────────────────────────────────────────────────
# CH4 — Price history + anti-fake-discount
# ──────────────────────────────────────────────────────────────────────

def record_price_change(product_id, *, price_cents, sku_id='',
                        reason='seller_update'):
    """Immutable insert on every price change (doc CH4)."""
    return ProductPriceHistory.objects.create(
        product_id=str(product_id), sku_id=str(sku_id), price_cents=price_cents,
        change_reason=reason)


def price_history(product_id, *, days=90, sku_id=''):
    cutoff = timezone.now() - timedelta(days=days)
    qs = ProductPriceHistory.objects.filter(
        product_id=str(product_id), recorded_at__gte=cutoff)
    if sku_id:
        qs = qs.filter(sku_id=str(sku_id))
    # One point per day (charting efficiency, doc CH4).
    seen = {}
    for h in qs.order_by('recorded_at'):
        seen[h.recorded_at.date()] = {
            'date': h.recorded_at.date().isoformat(),
            'price_cents': h.price_cents,
            'is_promotion': h.change_reason in ('promotion', 'flash_sale')}
    points = list(seen.values())
    prices = [p['price_cents'] for p in points]
    return {'points': points,
            'min_cents': min(prices) if prices else None,
            'max_cents': max(prices) if prices else None}


def validate_original_price(product_id, *, original_price_cents, sku_id=''):
    """Anti-fake-discount (doc CH4): the strikethrough 'original' price may
    only be shown if it was the ACTUAL price within the last 30 days.
    Returns True if genuine; logs a prevention event otherwise.
    """
    cutoff = timezone.now() - timedelta(days=ORIGINAL_PRICE_WINDOW_DAYS)
    was_real = ProductPriceHistory.objects.filter(
        product_id=str(product_id), price_cents=original_price_cents,
        recorded_at__gte=cutoff).exists()
    if sku_id:
        was_real = was_real or ProductPriceHistory.objects.filter(
            product_id=str(product_id), sku_id=str(sku_id),
            price_cents=original_price_cents, recorded_at__gte=cutoff).exists()
    if not was_real:
        BuyerExperienceEvent.log('fake_discount_prevented',
                                 product_id=str(product_id),
                                 claimed_original=original_price_cents)
    return was_real


# ──────────────────────────────────────────────────────────────────────
# CH7 — Pre-purchase question
# ──────────────────────────────────────────────────────────────────────

def ask_question(buyer, *, product_id, seller, question_text,
                 attachment_key=''):
    flag = _moderate(question_text)
    q = PrePurchaseQuestion.objects.create(
        buyer=buyer, product_id=product_id, seller=seller,
        question_text=question_text, attachment_key=attachment_key,
        status='held' if flag else 'pending', moderation_flag=flag,
        expires_at=timezone.now() + timedelta(days=QUESTION_EXPIRY_DAYS))
    if not flag:
        _notify(seller, 'Nova pergunta sobre um produto')
    BuyerExperienceEvent.log('question_asked', actor=buyer,
                             product_id=product_id, held=bool(flag))
    return q


def answer_question(question, *, answer_text):
    question.answer_text = answer_text
    question.status = 'answered'
    question.answered_at = timezone.now()
    question.save(update_fields=['answer_text', 'status', 'answered_at'])
    _notify(question.buyer, 'O vendedor respondeu à sua pergunta')
    return question


def expire_questions():
    now = timezone.now()
    n = PrePurchaseQuestion.objects.filter(
        status__in=('pending', 'held'), expires_at__lt=now).update(
        status='expired')
    return {'expired': n}


def _moderate(text):
    """Bridge to content safety; fail open. Returns a flag string or ''."""
    try:
        from apps.content_safety.services import scan_text
        r = scan_text(text)
        if getattr(r, 'blocked', False):
            return 'prohibited_content'
    except Exception:
        pass
    # cheap PII heuristic
    import re
    if re.search(r'\+?244\s?9\d{2}', text) or re.search(
            r'[\w.]+@[\w.]+', text):
        return 'pii_detected'
    return ''


# ──────────────────────────────────────────────────────────────────────
# CH8 — Bulk inquiry
# ──────────────────────────────────────────────────────────────────────

def create_bulk_inquiry(buyer, *, seller, product_id, quantity, sku_id='',
                        delivery_province='', purpose='resale',
                        buyer_message='', company_name='', nif='',
                        required_by_date=None):
    inq = BulkInquiry.objects.create(
        buyer=buyer, seller=seller, product_id=product_id, sku_id=sku_id,
        quantity=quantity, delivery_province=delivery_province,
        purpose=purpose, buyer_message=buyer_message,
        company_name=company_name, nif=nif, required_by_date=required_by_date)
    _notify(seller, 'Novo pedido de orçamento em massa')
    return inq


def quote_inquiry(inquiry, *, price_per_unit_cents, message=''):
    inquiry.seller_quote_cents = price_per_unit_cents
    inquiry.seller_message = message
    inquiry.status = 'quoted'
    inquiry.expires_at = timezone.now() + timedelta(hours=BULK_QUOTE_TTL_HOURS)
    inquiry.save(update_fields=['seller_quote_cents', 'seller_message',
                                'status', 'expires_at'])
    _notify(inquiry.buyer, 'O vendedor respondeu ao seu pedido de orçamento')
    return inquiry


def accept_quote(inquiry, *, order_id):
    if inquiry.status != 'quoted':
        return {'ok': False, 'reason': f'status_{inquiry.status}'}
    if inquiry.expires_at and inquiry.expires_at < timezone.now():
        inquiry.status = 'expired'
        inquiry.save(update_fields=['status'])
        return {'ok': False, 'reason': 'quote_expired'}
    inquiry.status = 'accepted'
    inquiry.order_id = order_id
    inquiry.save(update_fields=['status', 'order_id'])
    return {'ok': True, 'total_cents': inquiry.seller_quote_cents
            * inquiry.quantity}


# ──────────────────────────────────────────────────────────────────────
# CH10 — Saved comparison
# ──────────────────────────────────────────────────────────────────────

def save_comparison(buyer, *, product_ids, name=''):
    import secrets
    pids = list(dict.fromkeys(product_ids))[:MAX_SAVED_COMPARISON_PRODUCTS]
    return SavedComparison.objects.create(
        buyer=buyer, product_ids=pids, name=name,
        share_code=secrets.token_urlsafe(8))


# ──────────────────────────────────────────────────────────────────────
# CH12 — Quick reorder
# ──────────────────────────────────────────────────────────────────────

def reorder_check(buyer, order_id):
    """Validate a past order's items for reorder (doc CH12): listing active,
    in stock (clamp to available), price changed.
    """
    from apps.orders.models import Order
    order = Order.objects.filter(id=order_id, buyer=buyer).first()
    if order is None:
        return {'reorderable': [], 'issues': [{'issue': 'order_not_found'}]}
    reorderable, issues = [], []
    for item in order.items.all():
        cur_cents = _current_price_cents(str(item.product_id))
        avail = _available_for_product(str(item.product_id), item.product_sku)
        if avail is not None and avail <= 0:
            issues.append({'product': item.product_title,
                           'issue': 'listing_inactive'})
            continue
        qty = item.quantity
        if avail is not None and avail < item.quantity:
            issues.append({'product': item.product_title,
                           'issue': 'insufficient_stock', 'available': avail})
            qty = avail
        orig_cents = int(Decimal(str(item.unit_price)) * 100)
        reorderable.append({
            'product_id': str(item.product_id),
            'title': item.product_title, 'quantity': qty,
            'current_price_cents': cur_cents,
            'price_changed': cur_cents != orig_cents and cur_cents > 0})
    return {'reorderable': reorderable, 'issues': issues}


def _available_for_product(product_id, sku_code=''):
    try:
        from apps.stock_engine.models import InventorySku
        sku = InventorySku.objects.filter(product_id=product_id).first()
        if sku:
            return sku.available_quantity
    except Exception:
        pass
    return None  # unknown — don't block


# ──────────────────────────────────────────────────────────────────────
# CH14 — Wishlist price-drop watch
# ──────────────────────────────────────────────────────────────────────

def watch_price(buyer, *, product_id, sku_id='', threshold_pct=5):
    cur = _current_price_cents(product_id, sku_id)
    watch, _ = WishlistPriceWatch.objects.update_or_create(
        buyer=buyer, product_id=str(product_id), sku_id=str(sku_id),
        defaults={'price_at_add_cents': cur,
                  'threshold_pct': Decimal(str(threshold_pct)),
                  'alert_enabled': True})
    return watch


def check_price_drops():
    """Celery (doc CH14, every 4h). Alerts only on drops, never increases."""
    alerted = 0
    for w in WishlistPriceWatch.objects.filter(alert_enabled=True):
        cur = _current_price_cents(w.product_id, w.sku_id)
        if cur <= 0 or w.price_at_add_cents <= 0:
            continue
        drop_pct = (w.price_at_add_cents - cur) / w.price_at_add_cents * 100
        if drop_pct >= float(w.threshold_pct):
            _notify(w.buyer, 'Preço baixou na sua lista de desejos!')
            w.price_at_add_cents = cur   # reset to avoid repeat alerts
            w.last_alerted_at = timezone.now()
            w.save(update_fields=['price_at_add_cents', 'last_alerted_at'])
            alerted += 1
    return {'alerted': alerted}


# ──────────────────────────────────────────────────────────────────────
# CH18 — Age verification
# ──────────────────────────────────────────────────────────────────────

def requires_age_gate(category_id):
    return RestrictedCategory.objects.filter(
        category_id=str(category_id), is_active=True).exists()


def is_age_cleared(buyer):
    av = AgeVerification.objects.filter(buyer=buyer).first()
    if av is None or not av.age_verified:
        return False
    if av.expires_at and av.expires_at < timezone.now():
        return False
    return True


def verify_age(buyer, *, confirmed, method='self_declaration'):
    if not confirmed:
        return {'cleared': False}
    av, _ = AgeVerification.objects.update_or_create(
        buyer=buyer,
        defaults={'age_verified': True, 'method': method,
                  'verified_at': timezone.now(),
                  'expires_at': timezone.now() + timedelta(
                      days=AGE_GATE_CACHE_DAYS)})
    BuyerExperienceEvent.log('age_verified', actor=buyer, method=method)
    return {'cleared': True, 'expires_at': av.expires_at}


# ──────────────────────────────────────────────────────────────────────
# CH23 — Buyer dashboard aggregation
# ──────────────────────────────────────────────────────────────────────

def account_summary(buyer):
    """Aggregate across apps for the buyer dashboard (doc CH23)."""
    summary = {'subscriptions_active': ProductSubscription.objects.filter(
        buyer=buyer, status='active').count(),
        'saved_comparisons': SavedComparison.objects.filter(
            buyer=buyer).count(),
        'price_watches': WishlistPriceWatch.objects.filter(
            buyer=buyer, alert_enabled=True).count()}
    # loyalty (bridge)
    try:
        from apps.loyalty.models import UserTier
        ut = UserTier.objects.filter(user=buyer).first()
        if ut:
            summary['loyalty'] = {
                'tier': getattr(ut.tier, 'code', None) if ut.tier_id else None,
                'points': getattr(ut, 'points_balance', None)}
    except Exception:
        pass
    # orders (bridge)
    try:
        from apps.orders.models import Order
        summary['order_count'] = Order.objects.filter(buyer=buyer).count()
    except Exception:
        pass
    return summary


# ──────────────────────────────────────────────────────────────────────
# CH24 — KPI snapshot
# ──────────────────────────────────────────────────────────────────────

def snapshot_kpis(snapshot_date=None):
    snapshot_date = snapshot_date or timezone.now().date()
    subs = ProductSubscription.objects.all()
    created = subs.count()
    cutoff90 = timezone.now() - timedelta(days=90)
    old_subs = subs.filter(created_at__lt=cutoff90)
    retained = old_subs.filter(status='active').count()
    retention = round(retained / old_subs.count() * 100, 2) \
        if old_subs.count() else 0

    # review rates (bridge)
    review_pct = review_photo_pct = 0
    try:
        from apps.reviews.models import ProductReview, ReviewPhoto
        rtotal = ProductReview.objects.count()
        with_photo = ReviewPhoto.objects.values('review').distinct().count() \
            if rtotal else 0
        review_photo_pct = round(with_photo / rtotal * 100, 2) if rtotal else 0
    except Exception:
        pass

    snap, _ = BuyerExperienceKpiSnapshot.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'subscribe_save_retention_pct': retention,
            'review_photo_pct': review_photo_pct,
            'active_subscriptions': subs.filter(status='active').count(),
            'pending_bulk_inquiries': BulkInquiry.objects.filter(
                status__in=('submitted', 'viewed')).count(),
            'pending_questions': PrePurchaseQuestion.objects.filter(
                status='pending').count(),
        })
    return snap


# ──────────────────────────────────────────────────────────────────────
# Notification bridge
# ──────────────────────────────────────────────────────────────────────

def _notify(user, body):
    try:
        from apps.notifications.push_service import send_to_user
        if getattr(user, 'pk', None):
            send_to_user(user, title='MICHA Express', body=body)
    except Exception:
        pass
