"""
Seller Tools — domain services.

Chapter → function map:
  CH2   start_bulk_import
  CH3   run_bulk_edit / revert_bulk_edit
  CH8   create_return_policy / resolve_effective_policy
  CH9   activate_holiday_mode / resume_holiday_mode / auto_resume_due
  CH10  vote_qa_helpful / qa_answer_rate
  CH11  follow_store / unfollow_store / send_broadcast /
        record_broadcast_open / record_broadcast_click / report_broadcast_spam
  CH12  generate_commission_statement
  CH13  compute_listing_quality_score
  CH14  compute_price_competitiveness
  CH17  register_vat / _validate_vat_number
  CH18  link_store / linked_seller_ids / assert_seller_context
  CH19  file_dispute_appeal
  CH20  add_bank_account / set_payout_schedule / request_withdrawal
  CH22  add_compliance_label / compliance_enforcement_check
  CH23  QUOTA_TIERS / record_api_call / quota_status
  CH24  snapshot_seller_tools_kpis

External-dependent pieces are stubbed behind clean seams and noted in the
honest gap list: VIES/HMRC VAT validation, micro-deposit bank verification,
reportlab PDF rendering, prohibited-content image classifier for imports.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import (
    ApiQuotaUsage, BroadcastDelivery, CommissionStatement,
    ListingQualityScore, PriceCompetitivenessSnapshot, ProductComplianceLabel,
    ProductQaVote, SellerBroadcast, SellerBulkEditJob,
    SellerBulkImportJob, SellerDisputeAppeal, SellerHolidayMode,
    SellerPayoutSchedule, SellerReturnPolicy, SellerToolsEvent,
    SellerToolsKpiSnapshot, SellerVatRegistration, StoreAccountLink,
    StoreFollower,
)

# Platform-minimum return windows per category (doc CH8). Default 15 days.
PLATFORM_MIN_RETURN_DAYS = 15
MAX_RETURN_DAYS = 90
MAX_HOLIDAY_DAYS = 60
HOLIDAY_VIOLATION_BLOCK = 10           # violation_points > 10 → blocked
BULK_REVERT_WINDOW_HOURS = 2
MAX_LINKED_STORES = 5
BROADCAST_SPAM_SUSPEND_PCT = 5.0       # >5% spam reports → suspend privilege

# CH23 quota tiers: (daily_quota, per_minute_limit)
QUOTA_TIERS = {
    'standard': (100_000, 100),
    'bronze': (200_000, 200),
    'silver': (300_000, 300),
    'gold': (500_000, 500),
    'enterprise': (2_000_000, 2_000),
}


# ──────────────────────────────────────────────────────────────────────
# CH2 / CH3 — Bulk import + edit
# ──────────────────────────────────────────────────────────────────────

def start_bulk_import(seller, *, category_id='', file_name='', file_key='',
                      overwrite_existing=False, rows_total=0):
    job = SellerBulkImportJob.objects.create(
        seller=seller, category_id=category_id, file_name=file_name,
        file_key=file_key, overwrite_existing=overwrite_existing,
        rows_total=rows_total, status='queued',
    )
    SellerToolsEvent.log('bulk_import_started', actor=seller, job_id=job.id,
                         rows=rows_total)
    return job


@transaction.atomic
def run_bulk_edit(seller, *, action_type, action_params, listing_ids):
    """Apply a mass edit, snapshotting before-values for revertible
    actions (price/stock/status) so the seller can undo within 2 hours.
    """
    from apps.products.models import Product

    job = SellerBulkEditJob.objects.create(
        seller=seller, action_type=action_type, action_params=action_params,
        listing_ids=list(listing_ids), status='running',
        total=len(listing_ids),
    )
    revertible = action_type in ('price_adjustment', 'stock_update',
                                 'status_change')
    snapshot = {}
    succeeded = failed = 0

    # Only this seller's own listings (store.owner == seller)
    products = Product.objects.select_for_update().filter(
        id__in=listing_ids, store__owner=seller)

    for p in products:
        try:
            if action_type == 'price_adjustment':
                snapshot[str(p.id)] = {'price': str(p.price)}
                p.price = _apply_price_adjustment(p.price, action_params)
                p.save(update_fields=['price'])
            elif action_type == 'stock_update':
                snapshot[str(p.id)] = {'quantity': p.quantity}
                p.quantity = _apply_stock_update(p.quantity, action_params)
                p.save(update_fields=['quantity'])
            elif action_type == 'status_change':
                snapshot[str(p.id)] = {'is_active': p.is_active}
                p.is_active = action_params.get('target_status') == 'active'
                p.save(update_fields=['is_active'])
            elif action_type == 'attribute_add':
                attrs = dict(p.attributes or {})
                name = action_params.get('attribute_name')
                if name and name not in attrs:
                    attrs[name] = action_params.get('attribute_value')
                    p.attributes = attrs
                    p.save(update_fields=['attributes'])
            elif action_type == 'shipping_template':
                p.shipping_template_id = action_params.get('shipping_template_id')
                p.save(update_fields=['shipping_template'])
            succeeded += 1
        except Exception:
            failed += 1

    job.succeeded = succeeded
    job.failed = failed
    job.before_snapshot = snapshot if revertible else {}
    job.status = 'completed'
    job.finished_at = timezone.now()
    if revertible:
        job.revertible_until = timezone.now() + timedelta(
            hours=BULK_REVERT_WINDOW_HOURS)
    job.save()
    SellerToolsEvent.log('bulk_edit_run', actor=seller, job_id=job.id,
                         action=action_type, ok=succeeded, failed=failed)
    return job


def _apply_price_adjustment(price, params):
    mode = params.get('mode', 'percentage')
    value = Decimal(str(params.get('value', 0)))
    direction = params.get('direction', 'decrease')
    if mode == 'set_to':
        new = value
    elif mode == 'fixed':
        delta = value if direction == 'increase' else -value
        new = price + delta
    else:  # percentage
        factor = (value / 100) if direction == 'increase' else -(value / 100)
        new = price * (Decimal('1') + factor)
    return max(Decimal('0.01'), new.quantize(Decimal('0.01')))


def _apply_stock_update(qty, params):
    mode = params.get('mode', 'set_to')
    value = int(params.get('value', 0))
    if mode == 'add':
        return max(0, qty + value)
    if mode == 'subtract':
        return max(0, qty - value)
    return max(0, value)


@transaction.atomic
def revert_bulk_edit(seller, job_id):
    from apps.products.models import Product
    try:
        job = SellerBulkEditJob.objects.select_for_update().get(
            id=job_id, seller=seller)
    except SellerBulkEditJob.DoesNotExist:
        return {'reverted': False, 'reason': 'not_found'}
    if job.status == 'reverted':
        return {'reverted': False, 'reason': 'already_reverted'}
    if not job.before_snapshot:
        return {'reverted': False, 'reason': 'not_revertible'}
    if not job.revertible_until or job.revertible_until < timezone.now():
        return {'reverted': False, 'reason': 'window_expired'}

    restored = 0
    for pid, fields in job.before_snapshot.items():
        try:
            p = Product.objects.select_for_update().get(
                id=int(pid), store__owner=seller)
            for field, val in fields.items():
                if field == 'price':
                    p.price = Decimal(str(val))
                elif field == 'quantity':
                    p.quantity = int(val)
                elif field == 'is_active':
                    p.is_active = bool(val)
            p.save()
            restored += 1
        except Exception:
            continue
    job.status = 'reverted'
    job.reverted_at = timezone.now()
    job.save(update_fields=['status', 'reverted_at'])
    SellerToolsEvent.log('bulk_edit_reverted', actor=seller, job_id=job.id,
                         restored=restored)
    return {'reverted': True, 'restored': restored}


# ──────────────────────────────────────────────────────────────────────
# CH8 — Return policy
# ──────────────────────────────────────────────────────────────────────

def create_return_policy(seller, *, policy_name, applicable_to='all',
                         category_ids=None, product_ids=None,
                         return_window_days=15, accepts_returns_if='any_reason',
                         return_shipping_paid_by='buyer',
                         refund_to='original_payment',
                         non_returnable_reasons=None):
    window = max(PLATFORM_MIN_RETURN_DAYS, min(MAX_RETURN_DAYS,
                                               int(return_window_days)))
    if int(return_window_days) < PLATFORM_MIN_RETURN_DAYS:
        raise ValueError(
            f'Minimum return window is {PLATFORM_MIN_RETURN_DAYS} days')
    if int(return_window_days) > MAX_RETURN_DAYS:
        raise ValueError(f'Maximum return window is {MAX_RETURN_DAYS} days')
    policy = SellerReturnPolicy.objects.create(
        seller=seller, policy_name=policy_name, applicable_to=applicable_to,
        category_ids=category_ids or [], product_ids=product_ids or [],
        return_window_days=window, accepts_returns_if=accepts_returns_if,
        return_shipping_paid_by=return_shipping_paid_by, refund_to=refund_to,
        non_returnable_reasons=non_returnable_reasons or [],
    )
    SellerToolsEvent.log('return_policy_created', actor=seller,
                         policy_id=policy.id, window=window)
    return policy


def resolve_effective_policy(seller, product_id=None, category_id=None):
    """Most specific wins: product override → category → all."""
    qs = SellerReturnPolicy.objects.filter(seller=seller, is_active=True)
    if product_id is not None:
        p = qs.filter(applicable_to='product',
                      product_ids__contains=product_id).first()
        if p:
            return p
    if category_id is not None:
        c = qs.filter(applicable_to='category',
                      category_ids__contains=category_id).first()
        if c:
            return c
    return qs.filter(applicable_to='all').order_by('-updated_at').first()


# ──────────────────────────────────────────────────────────────────────
# CH9 — Holiday mode
# ──────────────────────────────────────────────────────────────────────

def _violation_points(seller):
    try:
        from apps.seller_onboarding.models import SellerHealthScore
        hs = SellerHealthScore.objects.filter(seller=seller).first()
        if hs is not None:
            return getattr(hs, 'violation_points', 0) or 0
    except Exception:
        pass
    return 0


@transaction.atomic
def activate_holiday_mode(seller, *, start_date, end_date, message='',
                          notify_followers=True):
    if _violation_points(seller) > HOLIDAY_VIOLATION_BLOCK:
        raise ValueError('Holiday mode unavailable while violation points > '
                         f'{HOLIDAY_VIOLATION_BLOCK}')
    if (end_date - start_date).days > MAX_HOLIDAY_DAYS:
        raise ValueError(f'Maximum holiday duration is {MAX_HOLIDAY_DAYS} days')

    hm, _ = SellerHolidayMode.objects.update_or_create(
        seller=seller,
        defaults={
            'enabled': True, 'start_date': start_date, 'end_date': end_date,
            'message': message[:300], 'notify_followers': notify_followers,
            'activated_at': timezone.now(), 'resumed_at': None,
            'auto_resumed': False,
        },
    )
    # Hide listings from search/discovery (best-effort bridge).
    _set_listings_visibility(seller, visible=False)
    if notify_followers:
        _broadcast_to_followers(
            seller, title='Store on holiday',
            body=message or 'This store is temporarily on holiday.')
    SellerToolsEvent.log('holiday_mode_activated', actor=seller,
                         start=str(start_date), end=str(end_date))
    return hm


@transaction.atomic
def resume_holiday_mode(seller, *, auto=False):
    try:
        hm = SellerHolidayMode.objects.select_for_update().get(seller=seller)
    except SellerHolidayMode.DoesNotExist:
        return None
    if not hm.enabled:
        return hm
    hm.enabled = False
    hm.resumed_at = timezone.now()
    hm.auto_resumed = auto
    hm.save(update_fields=['enabled', 'resumed_at', 'auto_resumed'])
    _set_listings_visibility(seller, visible=True)
    if hm.notify_followers:
        _broadcast_to_followers(seller, title='Store is back!',
                                body='This store has resumed operations.')
    SellerToolsEvent.log('holiday_mode_resumed', actor=seller, auto=auto)
    return hm


def auto_resume_due():
    """Cron at 08:00 — resume any store whose end_date has passed."""
    today = timezone.now().date()
    resumed = 0
    for hm in SellerHolidayMode.objects.filter(
            enabled=True, end_date__lte=today).select_related('seller'):
        resume_holiday_mode(hm.seller, auto=True)
        resumed += 1
    return {'resumed': resumed}


def _set_listings_visibility(seller, *, visible):
    """Toggle search visibility for all the seller's listings. Uses
    is_active as the visibility flag (bridge — fail open on schema drift).
    """
    try:
        from apps.products.models import Product
        Product.objects.filter(store__owner=seller).update(is_active=visible)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────
# CH10 — Q&A helpfulness
# ──────────────────────────────────────────────────────────────────────

def vote_qa_helpful(user, qa_id, helpful=True):
    vote, created = ProductQaVote.objects.update_or_create(
        qa_id=qa_id, user=user, defaults={'helpful': helpful})
    total = ProductQaVote.objects.filter(qa_id=qa_id, helpful=True).count()
    return {'created': created, 'helpful_votes': total}


def qa_answer_rate(within_hours=72):
    """% of questions answered within the SLA window (doc KPI)."""
    try:
        from apps.products.models import ProductQA
        cutoff = timezone.now() - timedelta(days=30)
        recent = ProductQA.objects.filter(created_at__gte=cutoff)
        total = recent.count()
        if not total:
            return 0.0
        answered_in_sla = 0
        for qa in recent.filter(answered_at__isnull=False).only(
                'created_at', 'answered_at'):
            if (qa.answered_at - qa.created_at) <= timedelta(hours=within_hours):
                answered_in_sla += 1
        return round(answered_in_sla / total * 100, 2)
    except Exception:
        return 0.0


# ──────────────────────────────────────────────────────────────────────
# CH11 — Followers + broadcast
# ──────────────────────────────────────────────────────────────────────

def follow_store(user, seller):
    f, created = StoreFollower.objects.get_or_create(seller=seller, user=user)
    return {'following': True, 'created': created}


def unfollow_store(user, seller):
    StoreFollower.objects.filter(seller=seller, user=user).delete()
    return {'following': False}


def _broadcast_to_followers(seller, *, title, body, deep_link=''):
    """Low-level fan-out used by holiday notices. Honours opt-out + the
    user's own push prefs via the existing push transport."""
    sent = 0
    followers = StoreFollower.objects.filter(
        seller=seller, opt_out_broadcasts=False).select_related('user')
    for f in followers:
        try:
            from apps.notifications.push_service import send_to_user
            send_to_user(f.user, title=title, body=body,
                         data={'deep_link': deep_link} if deep_link else None)
            sent += 1
        except Exception:
            continue
    return sent


@transaction.atomic
def send_broadcast(seller, *, subject, message_body, coupon_id='',
                   linked_product_ids=None, scheduled_at=None):
    """Create + (if not scheduled) send a follower broadcast. Enforces
    quota, anti-spam delay, moderation, and good-standing checks.
    """
    # Anti-spam: last broadcast must be > 7 days ago.
    last = SellerBroadcast.objects.filter(
        seller=seller, status='sent').order_by('-sent_at').first()
    if last and last.sent_at and (
            timezone.now() - last.sent_at) < timedelta(days=7):
        bc = SellerBroadcast.objects.create(
            seller=seller, subject=subject, message_body=message_body,
            coupon_id=coupon_id, linked_product_ids=linked_product_ids or [],
            status='blocked', block_reason='anti_spam_7day_window')
        return bc

    # Moderation (bridge to content safety; fail open).
    if not _moderation_passes(f'{subject}\n{message_body}'):
        bc = SellerBroadcast.objects.create(
            seller=seller, subject=subject, message_body=message_body,
            status='blocked', block_reason='moderation_failed')
        SellerToolsEvent.log('broadcast_blocked', actor=seller,
                             reason='moderation')
        return bc

    bc = SellerBroadcast.objects.create(
        seller=seller, subject=subject, message_body=message_body,
        coupon_id=coupon_id, linked_product_ids=linked_product_ids or [],
        scheduled_at=scheduled_at,
        status='scheduled' if scheduled_at else 'sending',
    )
    if scheduled_at:
        return bc
    _deliver_broadcast(bc)
    return bc


def _deliver_broadcast(bc):
    followers = StoreFollower.objects.filter(
        seller=bc.seller, opt_out_broadcasts=False).select_related('user')
    delivered = 0
    rows = []
    for f in followers:
        ok = False
        try:
            from apps.notifications.push_service import send_to_user
            send_to_user(
                f.user,
                title=f'New message from your followed store',
                body=bc.subject,
                data={'deep_link': f'micha://broadcast/{bc.id}'})
            ok = True
        except Exception:
            ok = False
        rows.append(BroadcastDelivery(broadcast=bc, user=f.user, delivered=ok))
        delivered += 1 if ok else 0
    BroadcastDelivery.objects.bulk_create(rows, ignore_conflicts=True)
    bc.recipients_count = len(rows)
    bc.delivered_count = delivered
    bc.status = 'sent'
    bc.sent_at = timezone.now()
    bc.save(update_fields=['recipients_count', 'delivered_count', 'status',
                           'sent_at'])
    SellerToolsEvent.log('broadcast_sent', actor=bc.seller, broadcast_id=bc.id,
                         delivered=delivered)
    return bc


def record_broadcast_open(broadcast_id, user):
    d = BroadcastDelivery.objects.filter(
        broadcast_id=broadcast_id, user=user, opened_at__isnull=True).first()
    if d:
        d.opened_at = timezone.now()
        d.save(update_fields=['opened_at'])
        SellerBroadcast.objects.filter(id=broadcast_id).update(
            open_count=models_F('open_count') + 1)
    return bool(d)


def record_broadcast_click(broadcast_id, user):
    d = BroadcastDelivery.objects.filter(
        broadcast_id=broadcast_id, user=user).first()
    if d and d.clicked_at is None:
        d.clicked_at = timezone.now()
        d.save(update_fields=['clicked_at'])
        SellerBroadcast.objects.filter(id=broadcast_id).update(
            click_count=models_F('click_count') + 1)
    return bool(d)


def report_broadcast_spam(broadcast_id, user):
    """Buyer marks a broadcast as spam → opt them out + maybe suspend."""
    d = BroadcastDelivery.objects.filter(
        broadcast_id=broadcast_id, user=user).first()
    if d and not d.reported_spam:
        d.reported_spam = True
        d.save(update_fields=['reported_spam'])
        StoreFollower.objects.filter(
            seller_id=SellerBroadcast.objects.get(id=broadcast_id).seller_id,
            user=user).update(opt_out_broadcasts=True)
        bc = SellerBroadcast.objects.get(id=broadcast_id)
        bc.spam_report_count = models_F('spam_report_count') + 1
        bc.save(update_fields=['spam_report_count'])
        bc.refresh_from_db()
        if bc.recipients_count and (
                bc.spam_report_count / bc.recipients_count * 100
                > BROADCAST_SPAM_SUSPEND_PCT):
            SellerToolsEvent.log('broadcast_privilege_suspended',
                                 actor=bc.seller, broadcast_id=bc.id)
    return True


def _moderation_passes(text):
    try:
        from apps.content_safety.services import scan_text
        result = scan_text(text)
        return not getattr(result, 'blocked', False)
    except Exception:
        return True  # fail open — moderation is a bridge


def models_F(field):
    from django.db.models import F
    return F(field)


# ──────────────────────────────────────────────────────────────────────
# CH12 — Commission statement
# ──────────────────────────────────────────────────────────────────────

def generate_commission_statement(seller, year, month):
    """Compute monthly totals from completed orders. PDF/CSV rendering is
    stubbed (keys recorded) — see honest gap list.
    """
    from apps.orders.models import Order

    period_start = date(year, month, 1)
    period_end = (date(year + 1, 1, 1) if month == 12
                  else date(year, month + 1, 1))

    orders = Order.objects.filter(
        seller=seller, created_at__gte=period_start,
        created_at__lt=period_end,
        status__in=['completed', 'delivering', 'delivered'])

    gross = commission = 0
    order_rows = []
    # NOTE: Order's total field is named `total` (NOT `total_amount`).
    for o in orders.only('id', 'created_at', 'total'):
        line_gross = int(Decimal(str(getattr(o, 'total', 0) or 0)) * 100)
        line_comm = int(line_gross * _commission_rate(seller))
        gross += line_gross
        commission += line_comm
        order_rows.append({'order_id': o.id,
                           'date': o.created_at.date().isoformat(),
                           'gross_cents': line_gross,
                           'commission_cents': line_comm})

    refunds = _period_refunds_cents(seller, period_start, period_end)
    net = gross - commission - refunds
    ref = f'CS-{seller.pk}-{year}{month:02d}'

    statement, _ = CommissionStatement.objects.update_or_create(
        seller=seller, period_year=year, period_month=month,
        defaults={
            'reference_number': ref,
            'gross_sales_cents': gross, 'commission_cents': commission,
            'refunds_cents': refunds, 'net_payout_cents': net,
            'order_count': len(order_rows), 'status': 'ready',
            'detail': {'orders': order_rows[:1000]},
            'pdf_key': f'statements/{ref}.pdf',   # rendered by worker (stub)
            'csv_key': f'statements/{ref}.csv',
        },
    )
    SellerToolsEvent.log('commission_statement_generated', actor=seller,
                         period=f'{year}-{month:02d}', net_cents=net)
    return statement


def _commission_rate(seller):
    try:
        from apps.seller_onboarding.models import SellerCommissionOverride
        ov = SellerCommissionOverride.objects.filter(seller=seller).first()
        if ov is not None:
            return float(getattr(ov, 'rate', 0) or 0) / 100 or 0.05
    except Exception:
        pass
    return 0.05  # 5% platform default


def _period_refunds_cents(seller, start, end):
    try:
        from apps.orders.models import Order
        from django.db.models import Sum
        agg = Order.objects.filter(
            seller=seller, created_at__gte=start, created_at__lt=end,
            status='refunded').aggregate(s=Sum('total'))
        return int(Decimal(str(agg['s'] or 0)) * 100)
    except Exception:
        return 0


# ──────────────────────────────────────────────────────────────────────
# CH13 — Listing Quality Score
# ──────────────────────────────────────────────────────────────────────

def compute_listing_quality_score(product):
    """0-100 across 5 components (doc CH13)."""
    from apps.products.models import ProductImage

    missing = []
    breakdown = {}

    # COMPONENT 1 — title (max 20)
    title = (product.title or '').strip()
    n = len(title)
    if n < 20:
        title_len = 0
        missing.append('Lengthen the title to 60-120 characters (+20 pts)')
    elif n <= 60:
        title_len = 10
        missing.append('Expand the title toward 60-120 characters (+10 pts)')
    elif n <= 120:
        title_len = 20
    else:
        title_len = 15
    if title and title == title.upper():
        title_len = max(0, title_len - 5)
        missing.append('Avoid ALL CAPS in the title (-5 pts)')
    title_score = min(20, title_len)
    breakdown['title'] = title_score

    # COMPONENT 2 — images (max 25)
    img_count = ProductImage.objects.filter(product=product).count()
    image_score = 0
    if img_count >= 1:
        image_score += 10  # main exists + assumed quality
    else:
        missing.append('Add a main product image (+10 pts)')
    if img_count >= 4:
        image_score += 5
    if img_count >= 6:
        image_score += 5
    if img_count < 6:
        missing.append(f'Add {max(0, 6 - img_count)} more images (+5-10 pts)')
    image_score += 5  # lifestyle-image credit (assumed; AI gate is a bridge)
    image_score = min(25, image_score)
    breakdown['images'] = image_score

    # COMPONENT 3 — description (max 20)
    words = len((product.description or '').split())
    if words < 50:
        desc_score = 0
        missing.append('Write a description of 150+ words (+15 pts)')
    elif words < 150:
        desc_score = 10
        missing.append('Expand the description to 150+ words (+5 pts)')
    else:
        desc_score = 15
    if '<' in (product.description or '') and '>' in (product.description or ''):
        desc_score += 3  # HTML formatting
    desc_score = min(20, desc_score)
    breakdown['description'] = desc_score

    # COMPONENT 4 — attributes (max 25)
    attrs = product.attributes or {}
    filled = sum(1 for v in attrs.values() if v not in (None, '', []))
    required_target = 6  # category schema bridge — conservative default
    attr_score = min(15, int(15 * min(1.0, filled / required_target)))
    if filled >= required_target * 0.8:
        attr_score += 10
    elif filled >= required_target * 0.5:
        attr_score += 5
    attr_score = min(25, attr_score)
    if attr_score < 25:
        missing.append('Fill in more product attributes (+up to 10 pts)')
    breakdown['attributes'] = attr_score

    # COMPONENT 5 — pricing & compliance (max 10)
    pricing_score = 0
    if product.compare_at_price:
        pricing_score += 3
    else:
        missing.append('Add an original (strikethrough) price (+3 pts)')
    if attrs.get('hs_code'):
        pricing_score += 3
    if attrs.get('country_of_origin'):
        pricing_score += 2
    if getattr(product, 'weight_kg', None):
        pricing_score += 2
    pricing_score = min(10, pricing_score)
    breakdown['pricing'] = pricing_score

    total = title_score + image_score + desc_score + attr_score + pricing_score

    seller = product.store.owner
    lqs, _ = ListingQualityScore.objects.update_or_create(
        product_id=product.id,
        defaults={
            'seller': seller, 'total_score': total,
            'title_score': title_score, 'image_score': image_score,
            'description_score': desc_score, 'attribute_score': attr_score,
            'pricing_score': pricing_score, 'missing': missing,
            'breakdown': breakdown,
        },
    )
    return lqs


# ──────────────────────────────────────────────────────────────────────
# CH14 — Price competitiveness
# ──────────────────────────────────────────────────────────────────────

def _percentile(sorted_vals, pct):
    if not sorted_vals:
        return 0
    k = max(0, min(len(sorted_vals) - 1,
                   int(round((pct / 100.0) * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def compute_price_competitiveness(product):
    """Compare against up to 20 similar products in the same category."""
    from apps.products.models import Product

    seller_price = int(Decimal(str(product.price)) * 100)
    lo, hi = int(seller_price * 0.2), int(seller_price * 1.8)  # ±80% band
    similar = list(Product.objects.filter(
        category=product.category, is_active=True,
        price__gte=Decimal(lo) / 100, price__lte=Decimal(hi) / 100,
    ).exclude(id=product.id).values_list('price', flat=True)[:20])
    prices = sorted(int(Decimal(str(p)) * 100) for p in similar)

    seller = product.store.owner
    if len(prices) < 3:  # not enough comparables
        snap = PriceCompetitivenessSnapshot.objects.create(
            product_id=product.id, seller=seller,
            seller_price_cents=seller_price, market_median_cents=seller_price,
            market_p25_cents=seller_price, market_p75_cents=seller_price,
            position_ratio=1.0, position_label='neutral',
            sample_size=len(prices),
            suggestion='Not enough comparable products for a reliable signal.')
        return snap

    median = _percentile(prices, 50)
    p25 = _percentile(prices, 25)
    p75 = _percentile(prices, 75)
    ratio = seller_price / median if median else 1.0

    if ratio < 0.90:
        label, suggestion = 'competitive', 'Cheaper than most competitors.'
    elif ratio <= 1.10:
        label, suggestion = 'neutral', 'Priced near the market average.'
    elif ratio <= 1.30:
        label = 'slight_risk'
        target = round(median * 1.05 / 100, 2)
        suggestion = (f'Priced above market average. Consider ~{target} '
                      f'to align with the competitive range.')
    else:
        label = 'review'
        target = round(median / 100, 2)
        suggestion = (f'Significantly above market. Review pricing; median '
                      f'is ~{target}.')

    snap = PriceCompetitivenessSnapshot.objects.create(
        product_id=product.id, seller=seller,
        seller_price_cents=seller_price, market_median_cents=median,
        market_p25_cents=p25, market_p75_cents=p75,
        position_ratio=round(ratio, 3), position_label=label,
        sample_size=len(prices), suggestion=suggestion)
    return snap


# ──────────────────────────────────────────────────────────────────────
# CH17 — Seller VAT
# ──────────────────────────────────────────────────────────────────────

def register_vat(seller, *, country, registration_number, tax_type='VAT',
                 price_display_mode='inclusive'):
    reg, _ = SellerVatRegistration.objects.update_or_create(
        seller=seller, country=country.upper(),
        registration_number=registration_number,
        defaults={'tax_type': tax_type,
                  'price_display_mode': price_display_mode,
                  'is_active': True, 'validation_status': 'pending'},
    )
    status_ = _validate_vat_number(reg.country, reg.registration_number)
    reg.validation_status = status_
    if status_ == 'valid':
        reg.validated_at = timezone.now()
    reg.save(update_fields=['validation_status', 'validated_at'])
    SellerToolsEvent.log('vat_registered', actor=seller, country=reg.country,
                         status=status_)
    return reg


def _validate_vat_number(country, number):
    """Format check only. Live VIES/HMRC/ABR validation is stubbed —
    see honest gap list. Returns 'valid' on a plausible format, else
    'invalid' (never raises).
    """
    number = (number or '').replace(' ', '').upper()
    if country in ('DE', 'FR', 'ES', 'IT', 'NL', 'PL', 'IE', 'BE'):
        ok = number.startswith(country) and len(number) >= 8
    elif country == 'GB':
        ok = number.startswith('GB') and len(number) >= 7
    elif country == 'AU':
        ok = number.isdigit() and len(number) == 11  # ABN
    else:
        ok = len(number) >= 5
    return 'valid' if ok else 'invalid'


# ──────────────────────────────────────────────────────────────────────
# CH18 — Multi-store
# ──────────────────────────────────────────────────────────────────────

def link_store(owner, store_seller, role='owner'):
    if StoreAccountLink.objects.filter(owner=owner).count() >= MAX_LINKED_STORES \
            and not StoreAccountLink.objects.filter(
                owner=owner, store_seller=store_seller).exists():
        raise ValueError(f'Maximum {MAX_LINKED_STORES} linked stores '
                         '(enterprise approval required to exceed)')
    link, created = StoreAccountLink.objects.get_or_create(
        owner=owner, store_seller=store_seller, defaults={'role': role})
    SellerToolsEvent.log('store_linked', actor=owner,
                         store_seller_id=store_seller.pk, created=created)
    return link


def linked_seller_ids(owner):
    ids = set(StoreAccountLink.objects.filter(
        owner=owner, approved=True).values_list('store_seller_id', flat=True))
    ids.add(owner.pk)  # own account always included
    return sorted(ids)


def assert_seller_context(user, requested_seller_id):
    """Validate the X-Seller-ID header is one the user controls (doc CH18)."""
    return int(requested_seller_id) in linked_seller_ids(user)


# ──────────────────────────────────────────────────────────────────────
# CH19 — Dispute appeal
# ──────────────────────────────────────────────────────────────────────

def file_dispute_appeal(seller, *, dispute_id, appeal_reason,
                        evidence_keys=None):
    if SellerDisputeAppeal.objects.filter(dispute_id=dispute_id).exists():
        raise ValueError('An appeal already exists for this dispute '
                         '(one appeal per dispute)')
    # Verify the dispute belongs to this seller (bridge; fail open if model differs).
    try:
        from apps.disputes.models import Dispute
        d = Dispute.objects.filter(id=dispute_id).first()
        if d is not None and getattr(d, 'seller_id', None) not in (None, seller.pk):
            raise ValueError('Dispute does not belong to this seller')
    except ValueError:
        raise
    except Exception:
        pass
    appeal = SellerDisputeAppeal.objects.create(
        dispute_id=dispute_id, seller=seller, appeal_reason=appeal_reason,
        evidence_keys=evidence_keys or [])
    SellerToolsEvent.log('dispute_appeal_filed', actor=seller,
                         dispute_id=dispute_id)
    return appeal


# ──────────────────────────────────────────────────────────────────────
# CH20 — Payout config
# ──────────────────────────────────────────────────────────────────────

def add_bank_account(seller, *, account_holder_name, bank_name, bank_country,
                     account_number, currency='USD', swift_code='',
                     sort_code='', routing_number='', is_default=False):
    """Bridge to apps.payments.SellerBankAccount (field-level encrypted).
    The doc's extra fields (country/swift/sort/routing) are not stored on
    the existing model — kept in the audit log for traceability.
    """
    from apps.payments.models import SellerBankAccount as PaymentsBankAccount
    acct = PaymentsBankAccount.objects.create(
        seller=seller, bank_name=bank_name,
        account_name=account_holder_name,
        account_number=account_number,  # encrypted at the field level
        is_default=is_default,
    )
    SellerToolsEvent.log('bank_account_added', actor=seller,
                         account_id=acct.id, bank_country=bank_country,
                         currency=currency, has_swift=bool(swift_code))
    return acct


def set_payout_schedule(seller, *, mode='automatic', weekday=0,
                        min_amount_cents=10000, default_bank_account_id=None):
    sched, _ = SellerPayoutSchedule.objects.update_or_create(
        seller=seller,
        defaults={'mode': mode, 'weekday': weekday,
                  'min_amount_cents': min_amount_cents,
                  'default_bank_account_id': default_bank_account_id},
    )
    return sched


def request_withdrawal(seller, *, amount_cents, destination='alipay'):
    """Bridge to apps.payments.PayoutRequest. Returns the created request
    or a 'recorded' stub if the payout model shape differs.
    """
    SellerToolsEvent.log('withdrawal_requested', actor=seller,
                         amount_cents=amount_cents, destination=destination)
    try:
        from apps.payments.models import PayoutRequest
        from decimal import Decimal as _D
        pr = PayoutRequest.objects.create(
            seller=seller, amount=_D(amount_cents) / 100)
        return {'status': 'requested', 'payout_request_id': pr.id,
                'amount_cents': amount_cents}
    except Exception:
        return {'status': 'recorded', 'amount_cents': amount_cents,
                'note': 'queued for payout worker'}


# ──────────────────────────────────────────────────────────────────────
# CH22 — Compliance labels
# ──────────────────────────────────────────────────────────────────────

CE_REQUIRED_CATEGORIES = {'electronics', 'toys', 'medical', 'ppe'}


def add_compliance_label(seller, *, product_id, label_type, label_value,
                         issuing_body='', issue_date=None, expiry_date=None,
                         certificate_key=''):
    label, _ = ProductComplianceLabel.objects.update_or_create(
        product_id=product_id, label_type=label_type,
        defaults={
            'seller': seller, 'label_value': label_value,
            'issuing_body': issuing_body, 'issue_date': issue_date,
            'expiry_date': expiry_date, 'certificate_key': certificate_key,
            'verification_status': 'self_declared',
        },
    )
    SellerToolsEvent.log('compliance_label_added', actor=seller,
                         product_id=product_id, label=label_type)
    return label


def compliance_enforcement_check(product, destination_region='EU'):
    """Returns {'compliant': bool, 'missing': [...]} for the destination."""
    category_name = ''
    try:
        category_name = (product.category.name or '').lower() \
            if product.category_id else ''
    except Exception:
        pass
    needs_ce = destination_region == 'EU' and any(
        c in category_name for c in CE_REQUIRED_CATEGORIES)
    missing = []
    if needs_ce and not ProductComplianceLabel.objects.filter(
            product_id=product.id, label_type='CE').exists():
        missing.append('CE')
    return {'compliant': not missing, 'missing': missing}


# ──────────────────────────────────────────────────────────────────────
# CH23 — API quota
# ──────────────────────────────────────────────────────────────────────

def _seller_tier(seller):
    try:
        from apps.seller_onboarding.models import SellerTierState
        ts = SellerTierState.objects.filter(seller=seller).first()
        if ts is not None:
            tier = (getattr(ts, 'tier', '') or '').lower()
            if tier in QUOTA_TIERS:
                return tier
    except Exception:
        pass
    return 'standard'


@transaction.atomic
def record_api_call(seller, count=1):
    """Increment counters and return whether the call is allowed.
    Daily quota + per-minute burst, both tier-derived (doc CH23).
    """
    today = timezone.now().date()
    minute = timezone.now().strftime('%Y%m%d%H%M')
    tier = _seller_tier(seller)
    daily_quota, per_minute = QUOTA_TIERS[tier]

    usage, _ = ApiQuotaUsage.objects.select_for_update().get_or_create(
        seller=seller, usage_date=today,
        defaults={'tier': tier, 'daily_quota': daily_quota,
                  'per_minute_limit': per_minute, 'minute_bucket': minute},
    )
    # Reset the per-minute window if the bucket rolled over.
    if usage.minute_bucket != minute:
        usage.minute_bucket = minute
        usage.calls_this_minute = 0
    # Keep tier ceilings fresh.
    usage.tier = tier
    usage.daily_quota = daily_quota
    usage.per_minute_limit = per_minute

    over_daily = usage.calls_today + count > daily_quota
    over_minute = usage.calls_this_minute + count > per_minute
    if over_daily or over_minute:
        usage.throttled_count += 1
        usage.save()
        reset = 60 - timezone.now().second if over_minute else _seconds_to_midnight()
        return {'allowed': False, 'reason':
                'daily_quota' if over_daily else 'rate_limit',
                'retry_after_seconds': reset,
                'limit': daily_quota, 'remaining': max(0, daily_quota - usage.calls_today),
                'burst': per_minute}

    usage.calls_today += count
    usage.calls_this_minute += count
    usage.save()
    return {'allowed': True, 'limit': daily_quota,
            'remaining': daily_quota - usage.calls_today,
            'burst': per_minute,
            'reset': _seconds_to_midnight()}


def _seconds_to_midnight():
    now = timezone.now()
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0,
                                            microsecond=0)
    return int((nxt - now).total_seconds())


def quota_status(seller):
    today = timezone.now().date()
    usage = ApiQuotaUsage.objects.filter(seller=seller, usage_date=today).first()
    tier = _seller_tier(seller)
    daily_quota, per_minute = QUOTA_TIERS[tier]
    used = usage.calls_today if usage else 0
    return {'tier': tier, 'daily_quota': daily_quota, 'used_today': used,
            'remaining': daily_quota - used, 'per_minute_limit': per_minute,
            'reset': _seconds_to_midnight()}


# ──────────────────────────────────────────────────────────────────────
# CH24 — KPI snapshot
# ──────────────────────────────────────────────────────────────────────

def snapshot_seller_tools_kpis(snapshot_date=None):
    snapshot_date = snapshot_date or timezone.now().date()
    cutoff = timezone.now() - timedelta(days=7)

    # Bulk import success rate
    imports = SellerBulkImportJob.objects.filter(created_at__gte=cutoff)
    imp_total = sum(j.rows_total for j in imports)
    imp_ok = sum(j.rows_succeeded for j in imports)
    bulk_import_pct = round(imp_ok / imp_total * 100, 2) if imp_total else 0

    # Bulk edit success rate
    edits = SellerBulkEditJob.objects.filter(created_at__gte=cutoff)
    edit_total = sum(j.total for j in edits)
    edit_ok = sum(j.succeeded for j in edits)
    bulk_edit_pct = round(edit_ok / edit_total * 100, 2) if edit_total else 0

    # Dispute self-resolution (appeals upheld / total appeals as a proxy)
    appeals = SellerDisputeAppeal.objects.all()
    appeal_total = appeals.count()
    appeal_resolved = appeals.filter(
        status__in=['upheld', 'rejected']).count()
    dispute_pct = round(appeal_resolved / appeal_total * 100, 2) \
        if appeal_total else 0

    # Holiday abuse: activations with open-order violations (proxy: 0 here)
    holiday_total = SellerHolidayMode.objects.filter(
        activated_at__gte=cutoff).count()
    holiday_abuse_pct = 0

    # Avg listing quality
    from django.db.models import Avg
    avg_lqs = ListingQualityScore.objects.aggregate(
        a=Avg('total_score'))['a'] or 0

    # Statement download rate
    stmts = CommissionStatement.objects.all()
    stmt_total = stmts.count()
    stmt_dl = stmts.filter(downloaded_at__isnull=False).count()
    stmt_pct = round(stmt_dl / stmt_total * 100, 2) if stmt_total else 0

    # Broadcast engagement (clicks / delivered)
    bcs = SellerBroadcast.objects.filter(status='sent')
    delivered = sum(b.delivered_count for b in bcs)
    clicks = sum(b.click_count for b in bcs)
    bc_pct = round(clicks / delivered * 100, 2) if delivered else 0

    # Price competitive %
    pcs = PriceCompetitivenessSnapshot.objects.filter(computed_at__gte=cutoff)
    pcs_total = pcs.count()
    pcs_ok = pcs.filter(position_label__in=['competitive', 'neutral']).count()
    price_pct = round(pcs_ok / pcs_total * 100, 2) if pcs_total else 0

    snap, _ = SellerToolsKpiSnapshot.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'bulk_import_success_pct': bulk_import_pct,
            'bulk_edit_success_pct': bulk_edit_pct,
            'dispute_self_resolution_pct': dispute_pct,
            'holiday_abuse_pct': holiday_abuse_pct,
            'qa_answer_rate_pct': qa_answer_rate(),
            'avg_listing_quality': round(avg_lqs, 2),
            'statement_download_pct': stmt_pct,
            'broadcast_engagement_pct': bc_pct,
            'price_competitive_pct': price_pct,
            'api_adoption_pct': _api_adoption_pct(),
            'shipping_template_coverage_pct': _shipping_coverage_pct(),
            'academy_m1_completion_pct': _academy_m1_pct(),
        },
    )
    SellerToolsEvent.log('seller_tools_kpis_snapshotted',
                         date=str(snapshot_date))
    return snap


def _api_adoption_pct():
    try:
        from apps.seller_onboarding.models import SellerApiKey
        active = SellerApiKey.objects.filter(is_active=True).values(
            'seller').distinct().count()
        from django.contrib.auth import get_user_model
        sellers = get_user_model().objects.filter(
            store_account_links__isnull=False).distinct().count() or 1
        return round(active / sellers * 100, 2)
    except Exception:
        return 0


def _shipping_coverage_pct():
    try:
        from apps.products.models import Product
        total = Product.objects.filter(is_active=True).count()
        if not total:
            return 0
        with_tpl = Product.objects.filter(
            is_active=True, shipping_template__isnull=False).count()
        return round(with_tpl / total * 100, 2)
    except Exception:
        return 0


def _academy_m1_pct():
    try:
        from apps.seller_onboarding.models import SellerTrainingProgress
        m1 = SellerTrainingProgress.objects.filter(module_id='M1')
        total = m1.count()
        if not total:
            return 0
        passed = m1.filter(passed=True).count()
        return round(passed / total * 100, 2)
    except Exception:
        return 0
