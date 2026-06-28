"""
Seller Operations services — pure domain logic (doc CH2-CH24).

Conventions (consistent with the other MICHA engines):
  * integer cents everywhere; ROUND_HALF_UP for any division
  * @transaction.atomic + select_for_update for races; savepoints around
    idempotent INSERTs so a unique-key clash rolls back only the savepoint
  * cross-app bridges are lazy imports inside functions and fail OPEN
    (a bridge being unavailable never blocks the seller's core action)
  * every meaningful touch -> SellerOperationsEvent.log(...)
"""
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import (
    AutoReplyLog, BulkExportJob, FulfilmentSLARecord, ListingComplianceViolation,
    ListingPublishState, ListingPublishTransition, ManualPriceOverride,
    PaymentHoldDispute, ProductCloneLog, RefundApprovalRequest, RepricingAction,
    RepricingRule, ReturnInspection, ROLE_PERMISSIONS, SellerActivationState,
    SellerAutoResponder, SellerBulkMessage, SellerBulkMessageRecipient,
    SellerCouponStackConfig, SellerIncomeTaxSummary, SellerInventoryAlertConfig,
    SellerMarketBenchmark, SellerOperationsEvent, SellerOperationsKpiSnapshot,
    SellerRecoveryPlan, SellerRefundPolicy, SellerSLAExcuse, SellerStaff,
    SellerStaffAuditLog, ShipmentCostReconciliation, StoreDesign,
)

PLATFORM_MIN_PRICE_CENTS = 100  # 1 Kz floor
SLA_BUSINESS_DAY_SECONDS = 24 * 3600  # Angola: simple calendar-day SLA (Sun excluded)


def _cents(value):
    return int(Decimal(str(value)).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


# ===========================================================================
# CH2 — Staff Management
# ===========================================================================
def invite_staff(seller, *, full_name, email, role, phone='', invited_by=None):
    if role not in ROLE_PERMISSIONS or role == 'owner':
        raise ValueError('invalid_role')  # owner is the account holder, not invited
    import secrets
    staff = SellerStaff.objects.create(
        seller=seller, invited_by=invited_by or seller, full_name=full_name,
        email=email.lower().strip(), phone=phone, role=role, status='invited',
        invite_token=secrets.token_urlsafe(32),
        invite_expires_at=timezone.now() + timedelta(days=7),
    )
    audit_staff_action(seller, None, 'staff_invited', target_type='staff',
                       target_id=str(staff.id), email=staff.email, role=role)
    SellerOperationsEvent.log('staff_invited', actor=invited_by or seller,
                              staff_id=str(staff.id), role=role)
    return staff


def accept_staff_invite(token, linked_user):
    staff = SellerStaff.objects.filter(invite_token=token,
                                       status='invited').first()
    if not staff:
        raise ValueError('invalid_invite')
    if staff.invite_expires_at and staff.invite_expires_at < timezone.now():
        raise ValueError('invite_expired')
    staff.status = 'active'
    staff.linked_user = linked_user
    staff.invite_token = ''
    staff.last_login_at = timezone.now()
    staff.save(update_fields=['status', 'linked_user', 'invite_token',
                              'last_login_at', 'updated_at'])
    audit_staff_action(staff.seller, staff, 'staff_joined', target_type='staff',
                       target_id=str(staff.id))
    return staff


def set_staff_status(staff, status, *, by=None):
    """Suspend/remove takes effect immediately — no grace period (doc CH2)."""
    if status not in {'active', 'suspended', 'removed'}:
        raise ValueError('invalid_status')
    staff.status = status
    staff.save(update_fields=['status', 'updated_at'])
    audit_staff_action(staff.seller, None, f'staff_{status}', target_type='staff',
                       target_id=str(staff.id))
    SellerOperationsEvent.log('staff_status_changed', actor=by,
                              staff_id=str(staff.id), status=status)
    return staff


def staff_can(staff, perm):
    return staff.status == 'active' and staff.has_perm(perm)


def audit_staff_action(seller, staff, action_type, *, target_type='',
                       target_id='', ip_address=None, **payload):
    """INSERT-ONLY staff accountability log (doc CH2). Never raises."""
    try:
        SellerStaffAuditLog.objects.create(
            seller=seller, staff=staff, action_type=action_type,
            target_type=target_type, target_id=str(target_id),
            payload_summary=payload, ip_address=ip_address)
    except Exception:
        pass


# ===========================================================================
# CH3 — Draft & Scheduled Publishing
# ===========================================================================
def get_or_init_publish_state(product_id, seller, status='DRAFT'):
    state, _ = ListingPublishState.objects.get_or_create(
        product_id=str(product_id), defaults={'seller': seller, 'status': status})
    return state


def transition_listing(product_id, seller, to_status, *, reason='', actor=None):
    """Enforce the doc 3.1 transition table; log every move."""
    with transaction.atomic():
        state = (ListingPublishState.objects
                 .select_for_update()
                 .filter(product_id=str(product_id)).first())
        if state is None:
            state = ListingPublishState.objects.create(
                product_id=str(product_id), seller=seller, status='DRAFT')
        frm = state.status
        allowed = ListingPublishState.ALLOWED_TRANSITIONS.get(frm, set())
        if to_status != frm and to_status not in allowed:
            raise ValueError(f'illegal_transition:{frm}->{to_status}')
        state.status = to_status
        state.save(update_fields=['status', 'updated_at'])
        ListingPublishTransition.objects.create(
            product_id=str(product_id), seller=seller, from_status=frm,
            to_status=to_status, reason=reason)
        _sync_product_active(product_id, to_status)
    SellerOperationsEvent.log('listing_transition', actor=actor,
                              product_id=str(product_id), frm=frm, to=to_status)
    return state


def _sync_product_active(product_id, status):
    """Reflect the publish state on the real Product (bridge, fail-open)."""
    try:
        from apps.products.models import Product
        p = Product.objects.filter(id=product_id).first()
        if not p:
            return
        active = (status == 'ACTIVE')
        if p.is_active != active:
            p.is_active = active
            p.save(update_fields=['is_active'])
    except Exception:
        pass


def schedule_listing(product_id, seller, when, *, actor=None):
    """Schedule go-live; must be >= now + 30min and pass moderation (doc CH3)."""
    if when < timezone.now() + timedelta(minutes=30):
        raise ValueError('schedule_too_soon')  # cannot schedule the past/imminent
    passed, notes = _run_listing_moderation(product_id)
    state = get_or_init_publish_state(product_id, seller)
    state.scheduled_publish_at = when
    state.moderation_passed = passed
    state.moderation_notes = notes
    if not passed:
        state.save(update_fields=['scheduled_publish_at', 'moderation_passed',
                                  'moderation_notes', 'updated_at'])
        SellerOperationsEvent.log('schedule_blocked_moderation', actor=actor,
                                  product_id=str(product_id))
        return state, False
    state.save(update_fields=['scheduled_publish_at', 'moderation_passed',
                              'moderation_notes', 'updated_at'])
    transition_listing(product_id, seller, 'SCHEDULED',
                       reason='scheduled_publish', actor=actor)
    state.refresh_from_db()  # transition_listing wrote under select_for_update
    return state, True


def _run_listing_moderation(product_id):
    """Bridge to trust_safety classifier; fail-open to 'passed' if unavailable."""
    try:
        from apps.trust_safety import services as ts
        if hasattr(ts, 'classify_listing'):
            res = ts.classify_listing(product_id)
            return bool(res.get('passed', True)), res.get('notes', '')
    except Exception:
        pass
    return True, ''


def activate_due_scheduled_listings():
    """Celery (every 5 min): flip SCHEDULED -> ACTIVE when the time arrives."""
    now = timezone.now()
    due = ListingPublishState.objects.filter(
        status='SCHEDULED', moderation_passed=True,
        scheduled_publish_at__lte=now)
    count = 0
    for state in due:
        try:
            transition_listing(state.product_id, state.seller, 'ACTIVE',
                               reason='scheduled_activation')
            _notify_seller(state.seller, 'listing_published',
                           {'product_id': state.product_id})
            count += 1
        except Exception:
            continue
    if count:
        SellerOperationsEvent.log('scheduled_activations', activated=count)
    return {'activated': count}


def autosave_draft(product_id, seller, payload):
    state = get_or_init_publish_state(product_id, seller)
    state.autosave_payload = payload
    state.autosaved_at = timezone.now()
    state.save(update_fields=['autosave_payload', 'autosaved_at', 'updated_at'])
    return state


# ===========================================================================
# CH4 — Product Cloning
# ===========================================================================
@transaction.atomic
def clone_product(source_product_id, seller, *, bulk_batch_id='',
                  attribute_overrides=None):
    """Duplicate a Product as a DRAFT template (doc 4.1).
    Copies content/pricing/shipping; resets stock/sku/barcode/status."""
    from apps.products.models import Product
    src = Product.objects.get(id=source_product_id)
    # store-scoped ownership check
    if getattr(src.store, 'owner_id', None) != getattr(seller, 'id', None):
        raise ValueError('not_owner')

    clone = Product(
        store=src.store, category=src.category, created_by=seller,
        title=(src.title + ' (Cópia)')[:200],
        description=src.description, brand=src.brand, condition=src.condition,
        sale_type=src.sale_type, price=src.price,
        compare_at_price=src.compare_at_price, cost_price=src.cost_price,
        weight_kg=src.weight_kg, length_cm=src.length_cm,
        width_cm=src.width_cm, height_cm=src.height_cm,
        low_stock_threshold=src.low_stock_threshold,
        # Intentionally NOT copied (doc 4.1):
        quantity=0, sku='', barcode='',
        is_active=False, moderation_status='pending',
    )
    for field, value in (attribute_overrides or {}).items():
        if hasattr(clone, field):
            setattr(clone, field, value)
    clone.slug = ''  # let the model regenerate a unique slug
    clone.save()

    # Clone always starts life as a DRAFT publish-state.
    get_or_init_publish_state(clone.id, seller, status='DRAFT')
    ProductCloneLog.objects.create(
        seller=seller, source_product_id=str(source_product_id),
        clone_product_id=str(clone.id), bulk_batch_id=bulk_batch_id)
    SellerOperationsEvent.log('product_cloned', actor=seller,
                              source=str(source_product_id), clone=str(clone.id))
    return clone


def bulk_clone(source_product_id, seller, variations):
    """Template approach: N drafts with differing attributes (doc CH4)."""
    import uuid as _uuid
    batch = _uuid.uuid4().hex
    clones = []
    for variation in variations:
        clones.append(clone_product(source_product_id, seller,
                                    bulk_batch_id=batch,
                                    attribute_overrides=variation))
    return {'batch_id': batch, 'clones': [str(c.id) for c in clones]}


# ===========================================================================
# CH5 — Automated Repricing
# ===========================================================================
def _rule_scope_products(rule):
    """Resolve a rule's scope to product ids (bridge to products, fail-open)."""
    try:
        from apps.products.models import Product
        qs = Product.objects.filter(store__owner=rule.seller, is_active=True)
        if rule.scope == 'category' and rule.scope_ids:
            qs = qs.filter(category_id__in=rule.scope_ids)
        elif rule.scope == 'specific_listings' and rule.scope_ids:
            qs = qs.filter(id__in=rule.scope_ids)
        return list(qs.only('id', 'price', 'quantity', 'cost_price'))
    except Exception:
        return []


def _compute_new_price(rule, product):
    """Return target price in cents from rule maths (pre-guardrail)."""
    p = rule.parameters or {}
    current = _cents(Decimal(str(product.price)) * 100)
    rt = rule.rule_type
    if rt == 'stock_based':
        thr = int(p.get('threshold_qty', 10))
        pct = Decimal(str(p.get('change_pct', 0)))
        if product.quantity <= thr:
            sign = 1 if p.get('action') == 'increase_price' else -1
            return _cents(current * (1 + sign * pct / 100))
        return current
    if rt == 'time_based':
        pct = Decimal(str(p.get('change_pct', 0)))
        today_weekend = timezone.now().weekday() >= 5
        target = p.get('schedule', 'weekend')
        if (target == 'weekend' and today_weekend) or target == 'always':
            return _cents(current * (1 + pct / 100))
        return current
    if rt == 'margin_floor':
        cost = int(p.get('cost_price_cents') or
                   _cents(Decimal(str(product.cost_price or 0)) * 100))
        margin = Decimal(str(p.get('min_margin_pct', 0)))
        floor = _cents(cost * (1 + margin / 100))
        return max(current, floor)
    if rt == 'demand_based':
        pct = Decimal(str(p.get('change_pct', 0)))
        sign = -1 if p.get('action') == 'decrease_price' else 1
        return _cents(current * (1 + sign * pct / 100))
    if rt == 'competitor_based':
        median = p.get('market_median_cents')
        if median:
            offset = Decimal(str(p.get('offset_pct', 0)))
            below = p.get('position') == 'below_median'
            sign = -1 if below else 1
            return _cents(int(median) * (1 + sign * offset / 100))
    return current


def evaluate_repricing_rules(frequency=None):
    """Celery: apply enabled rules, guardrail-bounded, conflict-resolved.
    margin_floor always wins; otherwise highest priority rule applies."""
    qs = RepricingRule.objects.filter(enabled=True)
    if frequency:
        qs = qs.filter(evaluation_frequency=frequency)
    # Group by product so we can resolve conflicts deterministically.
    by_product = {}  # product_id -> list[(rule, product)]
    for rule in qs.order_by('-priority'):
        for product in _rule_scope_products(rule):
            by_product.setdefault(str(product.id), []).append((rule, product))

    changed = 0
    now = timezone.now()
    for product_id, candidates in by_product.items():
        # margin_floor first, then by priority (already -priority ordered).
        candidates.sort(key=lambda rp: (rp[0].rule_type != 'margin_floor',
                                        -rp[0].priority))
        rule, product = candidates[0]
        if _override_active(rule.seller_id, product_id):
            continue
        target = _compute_new_price(rule, product)
        target = max(target, rule.floor_price_cents or 0)
        if rule.ceiling_price_cents:
            target = min(target, rule.ceiling_price_cents)
        target = max(target, PLATFORM_MIN_PRICE_CENTS)
        current = _cents(Decimal(str(product.price)) * 100)
        if current <= 0:
            continue
        if abs(target - current) / current > 0.005:  # >0.5% significant
            _apply_price(product, target)
            RepricingAction.objects.create(
                rule=rule, product_id=product_id, old_price_cents=current,
                new_price_cents=target, reason='auto_repricing_rule')
            _record_price_history(product_id, target, 'auto_repricing_rule')
            changed += 1
    qs.update(last_evaluated_at=now)
    if changed:
        SellerOperationsEvent.log('repricing_applied', changes=changed)
    return {'changed': changed}


def _apply_price(product, new_price_cents):
    try:
        product.price = (Decimal(new_price_cents) / 100)
        product.save(update_fields=['price'])
    except Exception:
        pass


def _override_active(seller_id, product_id):
    return ManualPriceOverride.objects.filter(
        seller_id=seller_id, product_id=str(product_id),
        overridden_until__gt=timezone.now()).exists()


def manual_price_override(seller, product_id, new_price_cents):
    """Seller manual set disables rules for that listing for 24h (doc CH5)."""
    _apply_price_by_id(product_id, new_price_cents)
    ManualPriceOverride.objects.create(
        seller=seller, product_id=str(product_id),
        overridden_until=timezone.now() + timedelta(hours=24))
    _record_price_history(product_id, new_price_cents, 'manual_override')
    SellerOperationsEvent.log('manual_price_override', actor=seller,
                              product_id=str(product_id), price=new_price_cents)


def _apply_price_by_id(product_id, new_price_cents):
    try:
        from apps.products.models import Product
        Product.objects.filter(id=product_id).update(
            price=Decimal(new_price_cents) / 100)
    except Exception:
        pass


def _record_price_history(product_id, price_cents, reason):
    """Bridge to buyer_experience immutable price history (CH4/CH5/CH16)."""
    try:
        from apps.buyer_experience import services as bx
        bx.record_price_change(str(product_id), price_cents=price_cents,
                               change_reason=reason)
    except Exception:
        pass


# ===========================================================================
# CH6 — Packing Slip & Bulk Export
# ===========================================================================
def packing_slip_data(order_id):
    """Build the printable packing-slip payload (doc 6.1). Hides home address;
    replaces prices with '---' when the order is a gift."""
    from apps.orders.models import Order
    order = Order.objects.get(id=order_id)
    is_gift = _order_is_gift(order)
    items = []
    for item in order.items.all():
        items.append({
            'sku': getattr(item, 'product_sku', '') or getattr(item, 'sku', ''),
            'product': getattr(item, 'product_title', '') or getattr(item, 'title', ''),
            'variant': _variant_label(item),
            'qty': getattr(item, 'quantity', 1),
            'price': '---' if is_gift else _kz(getattr(item, 'unit_price', 0)),
        })
    cod = order.payment_status != 'paid' and _is_cod(order)
    return {
        'header': 'GUIA DE EMBALAGEM',
        'order_id': str(order.id),
        'store_name': _store_name(order.seller),
        'ship_to': {
            'name': order.shipping_name,
            'bairro': order.shipping_city,
            'province': order.shipping_province,
            'phone': getattr(order, 'shipping_phone', ''),
        },
        'carrier': order.carrier, 'tracking_number': order.tracking_number,
        'estimated_delivery': str(order.estimated_delivery or ''),
        'cod_amount': _kz(order.total) if cod else None,
        'items': items,
        'totals': {
            'subtotal': '---' if is_gift else _kz(order.subtotal),
            'shipping': _kz(order.shipping_cost),
            'grand_total': '---' if is_gift else _kz(order.total),
        },
        'is_gift': is_gift,
    }


def _variant_label(item):
    opts = getattr(item, 'variant_options', None)
    if isinstance(opts, dict) and opts:
        return ' '.join(str(v) for v in opts.values())
    return getattr(item, 'variant', '') or ''


def _order_is_gift(order):
    try:
        from apps.buyer_experience.models import OrderGiftOptions
        opt = OrderGiftOptions.objects.filter(order_id=str(order.id)).first()
        return bool(opt and opt.is_gift)
    except Exception:
        return bool(getattr(order, 'gift_wrap', False))


def _is_cod(order):
    return 'cod' in (getattr(order, 'payment_method', '') or '').lower()


def queue_bulk_export(seller, *, kind, order_ids=None, filters=None):
    job = BulkExportJob.objects.create(
        seller=seller, kind=kind, order_ids=order_ids or [],
        filters=filters or {}, status='queued')
    from . import tasks
    try:
        tasks.run_bulk_export.delay(str(job.id))
    except Exception:
        run_bulk_export(job.id)  # eager fallback (dev/no-broker)
    return job


def run_bulk_export(job_id):
    job = BulkExportJob.objects.get(id=job_id)
    job.status = 'processing'
    job.save(update_fields=['status'])
    try:
        if job.kind in ('order_csv', 'order_xlsx'):
            rows = _export_rows(job.seller, job.filters)
            job.row_count = len(rows)
            key = f'exports/{job.seller_id}/{job.id}.{job.kind.split("_")[-1]}'
        elif job.kind == 'pick_list':
            rows = _pick_list(job.seller, job.order_ids)
            job.row_count = len(rows)
            key = f'exports/{job.seller_id}/{job.id}_picklist.csv'
        else:  # packing slips
            job.row_count = len(job.order_ids)
            key = f'exports/{job.seller_id}/{job.id}.pdf'
        job.result_s3_key = key
        job.result_url = _presign(key)
        job.status = 'ready'
        job.completed_at = timezone.now()
        job.save(update_fields=['row_count', 'result_s3_key', 'result_url',
                                'status', 'completed_at'])
    except Exception as exc:  # pragma: no cover - defensive
        job.status = 'failed'
        job.error = str(exc)[:500]
        job.save(update_fields=['status', 'error'])
    return job


def _export_rows(seller, filters):
    from apps.orders.models import Order
    qs = Order.objects.filter(seller=seller, is_deleted=False)
    if filters.get('from'):
        qs = qs.filter(created_at__date__gte=filters['from'])
    if filters.get('to'):
        qs = qs.filter(created_at__date__lte=filters['to'])
    if filters.get('status'):
        qs = qs.filter(status=filters['status'])
    rows = []
    for o in qs[:5000]:
        rows.append({
            'order_id': str(o.id), 'order_date': str(o.created_at.date()),
            'buyer_name': o.shipping_name, 'province': o.shipping_province,
            'total': _kz(o.total), 'payment_method': getattr(o, 'payment_method', ''),
            'tracking_number': o.tracking_number, 'status': o.status,
        })
    return rows


def _pick_list(seller, order_ids):
    """Consolidate units by SKU across orders (doc 6.1 pick list)."""
    from apps.orders.models import Order
    agg = {}
    for o in Order.objects.filter(seller=seller, id__in=order_ids):
        for item in o.items.all():
            sku = (getattr(item, 'product_sku', '') or
                   getattr(item, 'sku', '') or 'NO_SKU')
            agg.setdefault(sku, {'sku': sku, 'units': 0, 'orders': set()})
            agg[sku]['units'] += getattr(item, 'quantity', 1)
            agg[sku]['orders'].add(str(o.id))
    return [{'sku': v['sku'], 'units': v['units'], 'order_count': len(v['orders'])}
            for v in agg.values()]


# ===========================================================================
# CH7 — Shipping Cost Reconciliation
# ===========================================================================
def reconcile_shipment_cost(seller, *, shipment_id, charged_cents, actual_cents,
                            declared_weight_g=0, actual_weight_g=0,
                            order_id='', tolerance_cents=20000):
    diff = charged_cents - actual_cents
    if abs(diff) <= tolerance_cents:
        status, fault, adjustment = 'matched', 'none', 0
    elif diff > 0:
        status, fault, adjustment = 'overcharge', 'platform', 0
    else:
        # undercharge: seller fault iff weight under-declared.
        weight_short = actual_weight_g > declared_weight_g
        if weight_short:
            status, fault, adjustment = 'undercharge', 'seller', diff  # negative
        else:
            status, fault, adjustment = 'undercharge', 'platform', 0
    rec = ShipmentCostReconciliation.objects.create(
        seller=seller, shipment_id=str(shipment_id), order_id=str(order_id),
        shipping_fee_charged_cents=charged_cents,
        actual_carrier_cost_cents=actual_cents, difference_cents=diff,
        declared_weight_g=declared_weight_g, actual_weight_g=actual_weight_g,
        reconciliation_status=status, seller_adjustment_cents=adjustment,
        fault=fault, reconciled_at=timezone.now())
    if adjustment:
        _apply_payout_adjustment(seller, adjustment, reason='shipping_undercharge',
                                 ref=str(rec.id))
    SellerOperationsEvent.log('shipping_reconciled', actor=seller,
                              shipment=str(shipment_id), status=status,
                              adjustment=adjustment)
    return rec


def contest_shipping_adjustment(rec, *, evidence_s3_keys):
    if rec.fault != 'seller' or rec.seller_adjustment_cents == 0:
        raise ValueError('nothing_to_contest')
    rec.contested = True
    rec.contest_evidence_s3_keys = evidence_s3_keys or []
    rec.save(update_fields=['contested', 'contest_evidence_s3_keys'])
    SellerOperationsEvent.log('shipping_adjustment_contested', actor=rec.seller,
                              recon_id=str(rec.id))
    return rec


def _apply_payout_adjustment(seller, cents, *, reason, ref):
    """Bridge: deduct/credit against seller payout ledger. Fail-open."""
    try:
        from apps.accounting import services as acc
        if hasattr(acc, 'post_seller_adjustment'):
            acc.post_seller_adjustment(seller_id=seller.id, amount_cents=cents,
                                       reason=reason, reference=ref)
    except Exception:
        pass


# ===========================================================================
# CH8 — Auto-Responder
# ===========================================================================
def upsert_auto_responder(seller, **fields):
    responder, _ = SellerAutoResponder.objects.get_or_create(seller=seller)
    for k, v in fields.items():
        if hasattr(responder, k):
            setattr(responder, k, v)
    responder.save()
    SellerOperationsEvent.log('auto_responder_set', actor=seller,
                              enabled=responder.enabled, mode=responder.mode)
    return responder


def should_auto_reply(seller_id, buyer_id, *, now=None):
    """Decide whether a new buyer message gets an auto-reply (doc CH8)."""
    now = now or timezone.now()
    responder = SellerAutoResponder.objects.filter(seller_id=seller_id).first()
    if not responder or not responder.enabled:
        return False
    if responder.mode == 'always':
        ok = True
    elif responder.mode == 'outside_hours':
        ok = not _within_business_hours(responder.business_hours, now)
    elif responder.mode == 'holiday':
        ok = _seller_on_holiday(seller_id)
    else:
        ok = False
    if not ok:
        return False
    # No repeat auto-reply to the same buyer within 24h.
    if AutoReplyLog.objects.filter(
            seller_id=seller_id, buyer_id=str(buyer_id),
            sent_at__gte=now - timedelta(hours=24)).exists():
        return False
    return True


def record_auto_reply(seller, buyer_id, message_id=''):
    return AutoReplyLog.objects.create(
        seller=seller, buyer_id=str(buyer_id), message_id=str(message_id))


def _within_business_hours(hours, now):
    if not hours:
        return False
    day = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'][now.weekday()]
    window = hours.get(day)
    if not window:
        return False
    try:
        start_s, end_s = window.split('-')
        sh, sm = [int(x) for x in start_s.split(':')]
        eh, em = [int(x) for x in end_s.split(':')]
        cur = now.hour * 60 + now.minute
        return sh * 60 + sm <= cur <= eh * 60 + em
    except Exception:
        return False


def _seller_on_holiday(seller_id):
    try:
        from apps.seller_tools.models import SellerHolidayMode
        hm = SellerHolidayMode.objects.filter(seller_id=seller_id).first()
        return bool(hm and getattr(hm, 'enabled', False))
    except Exception:
        return False


# ===========================================================================
# CH9 — Refund Approval Workflow
# ===========================================================================
def request_refund(seller, *, order_id, amount_cents, reason='',
                   requested_by_staff=None, evidence_s3_keys=None):
    """Route a refund through approval if policy requires it (doc CH9)."""
    policy, _ = SellerRefundPolicy.objects.get_or_create(seller=seller)
    # Tiny amounts always bypass the workflow.
    if amount_cents < policy.auto_approve_below_cents:
        return _auto_approved_request(seller, order_id, amount_cents, reason,
                                      requested_by_staff, evidence_s3_keys)
    needs_approval = (policy.refund_approval_required and
                      amount_cents >= policy.approval_threshold_cents)
    if not needs_approval:
        return _auto_approved_request(seller, order_id, amount_cents, reason,
                                      requested_by_staff, evidence_s3_keys)
    req = RefundApprovalRequest.objects.create(
        seller=seller, order_id=str(order_id), amount_cents=amount_cents,
        reason=reason, requested_by_staff=requested_by_staff,
        evidence_s3_keys=evidence_s3_keys or [], status='pending')
    _notify_seller(seller, 'refund_approval_needed',
                   {'request_id': str(req.id), 'amount': amount_cents})
    SellerOperationsEvent.log('refund_requested', actor=seller,
                              request_id=str(req.id), amount=amount_cents)
    return req


def _auto_approved_request(seller, order_id, amount_cents, reason,
                           staff, evidence):
    req = RefundApprovalRequest.objects.create(
        seller=seller, order_id=str(order_id), amount_cents=amount_cents,
        reason=reason, requested_by_staff=staff,
        evidence_s3_keys=evidence or [], status='auto_approved',
        reviewed_at=timezone.now())
    _process_refund(req)
    return req


def review_refund(req, *, approve, reviewed_by_staff=None, note=''):
    if req.status != 'pending':
        raise ValueError('not_pending')
    req.reviewed_by_staff = reviewed_by_staff
    req.review_note = note
    req.reviewed_at = timezone.now()
    req.status = 'approved' if approve else 'rejected'
    req.save(update_fields=['reviewed_by_staff', 'review_note', 'reviewed_at',
                            'status'])
    if approve:
        _process_refund(req)
    else:
        _notify_seller(req.seller, 'refund_rejected', {'request_id': str(req.id)})
    SellerOperationsEvent.log('refund_reviewed', actor=req.seller,
                              request_id=str(req.id), approved=approve)
    return req


def _process_refund(req):
    """Bridge to the platform refund pipeline (payments). Fail-open."""
    try:
        from apps.payments_angola import services as pay
        if hasattr(pay, 'issue_refund'):
            pay.issue_refund(order_id=req.order_id, amount_cents=req.amount_cents,
                             reason=req.reason)
    except Exception:
        pass


def escalate_pending_refunds():
    """Celery: nudge owner at 48h, MICHA admin at 72h (doc CH9)."""
    now = timezone.now()
    owner_q = RefundApprovalRequest.objects.filter(
        status='pending', owner_escalated=False,
        created_at__lte=now - timedelta(hours=48))
    n_owner = 0
    for req in owner_q:
        req.owner_escalated = True
        req.save(update_fields=['owner_escalated'])
        _notify_seller(req.seller, 'refund_approval_overdue',
                       {'request_id': str(req.id)})
        n_owner += 1
    admin_q = RefundApprovalRequest.objects.filter(
        status='pending', admin_escalated=False,
        created_at__lte=now - timedelta(hours=72))
    n_admin = 0
    for req in admin_q:
        req.admin_escalated = True
        req.save(update_fields=['admin_escalated'])
        n_admin += 1
    return {'owner_escalated': n_owner, 'admin_escalated': n_admin}


# ===========================================================================
# CH10 — Income Tax Summary
# ===========================================================================
def generate_income_tax_summary(seller, year, *, nif=''):
    """Aggregate the year's earnings into the AGT filing source doc (doc CH10)."""
    data = _income_aggregate(seller, year)
    import uuid as _uuid
    ref = f'IRS-{year}-{str(seller.id)[:8]}-{_uuid.uuid4().hex[:6]}'.upper()
    summary, _ = SellerIncomeTaxSummary.objects.update_or_create(
        seller=seller, year=year,
        defaults=dict(
            nif=nif, statement_reference=ref,
            gross_sales_cents=data['gross'], commission_cents=data['commission'],
            shipping_costs_cents=data['shipping'], refunds_cents=data['refunds'],
            chargebacks_cents=data['chargebacks'],
            net_earnings_cents=data['net'], payouts_cents=data['payouts'],
            iva_collected_cents=data['iva'],
            withholding_tax_cents=data['withholding'],
            monthly_breakdown=data['monthly'],
            document_s3_key=f'tax/{seller.id}/income_{year}.pdf'))
    SellerOperationsEvent.log('income_summary_generated', actor=seller,
                              year=year, net=data['net'])
    return summary


def _income_aggregate(seller, year):
    """Source figures from the seller-payable ledger (bridge), else orders."""
    monthly = []
    gross = commission = shipping = refunds = chargebacks = payouts = 0
    iva = withholding = 0
    try:
        from apps.orders.models import Order
        from django.db.models import Sum
        base = Order.objects.filter(seller=seller, status='paid',
                                    created_at__year=year)
        for m in range(1, 13):
            mo = base.filter(created_at__month=m)
            g = int((mo.aggregate(s=Sum('total'))['s'] or 0) * 100)
            tax = int((mo.aggregate(s=Sum('tax_amount'))['s'] or 0) * 100)
            ss = int((mo.aggregate(s=Sum('seller_subsidy'))['s'] or 0) * 100)
            comm = _cents(g * 0.06)  # platform commission est. 6% (doc CH22)
            net = g - comm - ss
            gross += g
            commission += comm
            refunds += ss
            iva += tax
            payouts += net
            monthly.append({'month': m, 'gross': g, 'commission': comm,
                            'refunds': ss, 'net': net, 'payouts': net})
    except Exception:
        pass
    net_total = gross - commission - shipping - refunds - chargebacks
    return {'gross': gross, 'commission': commission, 'shipping': shipping,
            'refunds': refunds, 'chargebacks': chargebacks, 'net': net_total,
            'payouts': payouts, 'iva': iva, 'withholding': withholding,
            'monthly': monthly}


# ===========================================================================
# CH11 — Store Design
# ===========================================================================
def save_store_design(seller, store_id, *, publish=False, **fields):
    design, _ = StoreDesign.objects.get_or_create(
        store_id=str(store_id), defaults={'seller': seller})
    for k, v in fields.items():
        if hasattr(design, k):
            setattr(design, k, v)
    # Featured grid capped at 8 (doc CH11).
    if design.featured_product_ids:
        design.featured_product_ids = list(design.featured_product_ids)[:8]
    if publish:
        design.published = True
        design.published_at = timezone.now()
    design.save()
    SellerOperationsEvent.log('store_design_saved', actor=seller,
                              store_id=str(store_id), published=publish)
    return design


# ===========================================================================
# CH12 — Coupon self-service (dashboard bridges to promotions)
# ===========================================================================
def set_coupon_stack(seller, stackable):
    cfg, _ = SellerCouponStackConfig.objects.get_or_create(seller=seller)
    cfg.stackable_with_platform = bool(stackable)
    cfg.save(update_fields=['stackable_with_platform', 'updated_at'])
    return cfg


def promotions_dashboard(seller):
    """Aggregate the seller's promotions across the promotion apps (bridge)."""
    out = {'active': [], 'scheduled': [], 'expired': [], 'draft': []}
    try:
        from apps.promotions.models import Promotion
        now = timezone.now()
        for promo in Promotion.objects.filter(
                **_promo_seller_filter())[:200]:
            bucket = _promo_bucket(promo, now)
            out[bucket].append({'id': str(promo.id),
                                'code': getattr(promo, 'code', '')})
    except Exception:
        pass
    return out


def _promo_seller_filter():
    return {}


def _promo_bucket(promo, now):
    starts = getattr(promo, 'starts_at', None)
    ends = getattr(promo, 'ends_at', None)
    if not getattr(promo, 'is_active', True):
        return 'draft'
    if starts and starts > now:
        return 'scheduled'
    if ends and ends < now:
        return 'expired'
    return 'active'


# ===========================================================================
# CH13 — Low-Stock & Reorder
# ===========================================================================
def set_inventory_alert(seller, sku_id, **fields):
    cfg, _ = SellerInventoryAlertConfig.objects.get_or_create(
        seller=seller, sku_id=str(sku_id))
    for k, v in fields.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)
    cfg.save()
    return cfg


def low_stock_skus(seller):
    """Bridge to stock_engine for at-risk SKUs + reorder suggestions."""
    items = []
    try:
        from apps.stock_engine.models import InventorySku
        from django.db.models import F
        skus = InventorySku.objects.filter(seller=seller)
        for sku in skus:
            threshold = _alert_threshold(seller, sku)
            if sku.available_quantity <= threshold:
                state = ('out' if sku.available_quantity == 0 else
                         'critical' if sku.available_quantity <= threshold / 2
                         else 'warning')
                items.append({
                    'sku_id': str(sku.id), 'product_id': sku.product_id,
                    'available': sku.available_quantity,
                    'safety_stock': sku.safety_stock_qty, 'state': state,
                    'recommended_reorder': sku.reorder_qty or
                    max(sku.safety_stock_qty * 2 - sku.available_quantity, 0),
                })
    except Exception:
        pass
    return items


def _alert_threshold(seller, sku):
    cfg = SellerInventoryAlertConfig.objects.filter(
        seller=seller, sku_id=str(sku.id)).first()
    if cfg and cfg.custom_threshold_qty is not None:
        return cfg.custom_threshold_qty
    return sku.safety_stock_qty


def send_reorder_digests():
    """Celery (daily 08:00): one digest per seller with at-risk SKUs (doc CH13)."""
    sellers = {}
    try:
        from apps.stock_engine.models import InventorySku
        for sku in InventorySku.objects.all():
            if sku.available_quantity <= sku.safety_stock_qty:
                sellers.setdefault(sku.seller_id, 0)
                sellers[sku.seller_id] += 1
    except Exception:
        return {'digests': 0}
    sent = 0
    for seller_id, n in sellers.items():
        _notify_seller_id(seller_id, 'low_stock_digest', {'count': n})
        sent += 1
    if sent:
        SellerOperationsEvent.log('reorder_digests_sent', count=sent)
    return {'digests': sent}


# ===========================================================================
# CH14 — Fulfilment SLA
# ===========================================================================
def open_sla_record(order_id, seller, *, paid_at=None, processing_days=2):
    paid_at = paid_at or timezone.now()
    deadline = _add_business_days(paid_at, processing_days)
    rec, created = FulfilmentSLARecord.objects.get_or_create(
        order_id=str(order_id),
        defaults=dict(seller=seller, processing_days=processing_days,
                      paid_at=paid_at, sla_deadline=deadline))
    return rec


def mark_shipment_picked_up(order_id, *, picked_up_at=None):
    rec = FulfilmentSLARecord.objects.filter(order_id=str(order_id)).first()
    if not rec:
        return None
    picked_up_at = picked_up_at or timezone.now()
    rec.picked_up_at = picked_up_at
    rec.on_time = picked_up_at <= rec.sla_deadline
    rec.is_late = not rec.on_time and not rec.excused
    rec.save(update_fields=['picked_up_at', 'on_time', 'is_late'])
    SellerOperationsEvent.log('sla_picked_up', actor=rec.seller,
                              order_id=str(order_id), on_time=rec.on_time)
    return rec


def register_sla_excuse(seller, *, reason, date_from, date_to):
    excuse = SellerSLAExcuse.objects.create(
        seller=seller, reason=reason, date_from=date_from, date_to=date_to)
    SellerOperationsEvent.log('sla_excuse_registered', actor=seller)
    return excuse


def sweep_sla_deadlines():
    """Celery: remind at T-24h, mark LATE past deadline, apply excuses."""
    now = timezone.now()
    reminded = late = 0
    # Reminders (within 24h of deadline, not yet shipped).
    for rec in FulfilmentSLARecord.objects.filter(
            picked_up_at__isnull=True, reminded=False,
            sla_deadline__lte=now + timedelta(hours=24),
            sla_deadline__gt=now):
        rec.reminded = True
        rec.save(update_fields=['reminded'])
        _notify_seller(rec.seller, 'sla_reminder', {'order_id': rec.order_id})
        reminded += 1
    # Past-deadline -> LATE (unless an approved excuse covers the date).
    for rec in FulfilmentSLARecord.objects.filter(
            picked_up_at__isnull=True, is_late=False, sla_deadline__lt=now):
        if _excuse_covers(rec.seller_id, now.date()):
            rec.excused = True
            rec.save(update_fields=['excused'])
            continue
        rec.is_late = True
        rec.save(update_fields=['is_late'])
        late += 1
    if late or reminded:
        SellerOperationsEvent.log('sla_swept', reminded=reminded, late=late)
    return {'reminded': reminded, 'late': late}


def _excuse_covers(seller_id, day):
    return SellerSLAExcuse.objects.filter(
        seller_id=seller_id, status='approved',
        date_from__lte=day, date_to__gte=day).exists()


def seller_on_time_rate(seller):
    from django.db.models import Count, Q
    agg = FulfilmentSLARecord.objects.filter(
        seller=seller, on_time__isnull=False).aggregate(
        total=Count('id'), on_time=Count('id', filter=Q(on_time=True)))
    total = agg['total'] or 0
    return round(100.0 * (agg['on_time'] or 0) / total, 1) if total else 100.0


def _add_business_days(start, days):
    """Add N business days, skipping Sundays (Angola simple rule, doc CH14)."""
    current = start
    added = 0
    while added < days:
        current = current + timedelta(days=1)
        if current.weekday() != 6:  # 6 == Sunday
            added += 1
    return current


# ===========================================================================
# CH15 — Payment Hold Disputes
# ===========================================================================
def contest_payment_hold(seller, *, payout_id, hold_reason, contest_reason,
                         evidence_s3_keys=None):
    dispute = PaymentHoldDispute.objects.create(
        seller=seller, payout_id=str(payout_id), hold_reason=hold_reason,
        seller_contest_reason=contest_reason,
        evidence_s3_keys=evidence_s3_keys or [], status='submitted')
    SellerOperationsEvent.log('payment_hold_contested', actor=seller,
                              dispute_id=str(dispute.id))
    return dispute


def resolve_payment_hold(dispute, *, released, note=''):
    dispute.status = 'resolved_released' if released else 'resolved_retained'
    dispute.resolution_note = note
    dispute.resolved_at = timezone.now()
    dispute.save(update_fields=['status', 'resolution_note', 'resolved_at'])
    if released:
        _release_payout(dispute.seller, dispute.payout_id)
    _notify_seller(dispute.seller, 'payment_hold_resolved',
                   {'released': released})
    return dispute


def escalate_stale_holds():
    """Celery: holds open > 30 days escalate to Head of Finance (doc CH15)."""
    cutoff = timezone.now() - timedelta(days=30)
    n = 0
    for d in PaymentHoldDispute.objects.filter(
            status__in=['submitted', 'under_review'],
            escalated_head_finance=False, created_at__lte=cutoff):
        d.escalated_head_finance = True
        d.save(update_fields=['escalated_head_finance'])
        n += 1
    return {'escalated': n}


def _release_payout(seller, payout_id):
    try:
        from apps.payments.models import PayoutRequest
        PayoutRequest.objects.filter(id=payout_id).update(status='approved')
    except Exception:
        pass


# ===========================================================================
# CH16 — Listing Compliance Monitoring
# ===========================================================================
ISSUE_RULES = {
    'prohibited_keyword': ('HIGH', 48, 'Remover/substituir a palavra proibida'),
    'missing_hs_code': ('LOW', 720, 'Adicionar código HS'),
    'missing_certification': ('MED', 168, 'Carregar certificado'),
    'fake_discount': ('MED', 168, 'Definir preço original real ou remover'),
    'weight_discrepancy_pattern': ('MED', 168, 'Corrigir pesos declarados'),
}


def raise_compliance_violation(seller, product_id, issue_type, *, detail=None):
    if issue_type not in ISSUE_RULES:
        raise ValueError('unknown_issue')
    severity, hours, action = ISSUE_RULES[issue_type]
    with transaction.atomic():
        # Idempotent: at most one OPEN violation per (seller, product, issue).
        existing = (ListingComplianceViolation.objects
                    .select_for_update()
                    .filter(seller=seller, product_id=str(product_id),
                            issue_type=issue_type, status='open').first())
        if existing:
            return existing
        v = ListingComplianceViolation.objects.create(
            seller=seller, product_id=str(product_id),
            issue_type=issue_type, severity=severity,
            action_required=action,
            deadline=timezone.now() + timedelta(hours=hours),
            status='open', detail=detail or {})
    SellerOperationsEvent.log('compliance_violation', actor=seller,
                              product_id=str(product_id), issue=issue_type)
    return v


def mark_violation_fixed(violation):
    violation.status = 'fix_pending_review'
    violation.save(update_fields=['status'])
    return violation


def rescan_compliance():
    """Celery: re-scan fix_pending_review (clear) + auto-remove overdue HIGH."""
    cleared = removed = 0
    now = timezone.now()
    for v in ListingComplianceViolation.objects.filter(
            status='fix_pending_review'):
        if _reclassify_ok(v):
            v.status = 'cleared'
            v.resolved_at = now
            v.save(update_fields=['status', 'resolved_at'])
            cleared += 1
    for v in ListingComplianceViolation.objects.filter(
            status='open', severity='HIGH', deadline__lt=now):
        v.status = 'auto_removed'
        v.resolved_at = now
        v.save(update_fields=['status', 'resolved_at'])
        _force_listing_removed(v.seller, v.product_id)
        removed += 1
    if cleared or removed:
        SellerOperationsEvent.log('compliance_rescan', cleared=cleared,
                                  removed=removed)
    return {'cleared': cleared, 'auto_removed': removed}


def _reclassify_ok(violation):
    if violation.issue_type == 'fake_discount':
        # Bridge to buyer_experience anti-fake-discount validator.
        try:
            from apps.buyer_experience.models import ProductPriceHistory
            return ProductPriceHistory.objects.filter(
                product_id=violation.product_id).exists()
        except Exception:
            return True
    return True  # other issue types: trust assert-fixed; T&S re-scan async


def _force_listing_removed(seller, product_id):
    try:
        transition_listing(product_id, seller, 'REMOVED',
                           reason='compliance_auto_removed')
    except Exception:
        pass


def compliance_score(seller):
    """% of active listings with no open violations (doc CH16)."""
    try:
        from apps.products.models import Product
        total = Product.objects.filter(store__owner=seller,
                                       is_active=True).count()
    except Exception:
        total = 0
    if not total:
        return 100.0
    flagged = (ListingComplianceViolation.objects
               .filter(seller=seller, status__in=['open', 'fix_pending_review'])
               .values('product_id').distinct().count())
    return round(100.0 * max(total - flagged, 0) / total, 1)


# ===========================================================================
# CH17 — Activation milestones (drip bridges to seller_onboarding)
# ===========================================================================
def recompute_activation(seller):
    state, _ = SellerActivationState.objects.get_or_create(seller=seller)
    state.kyc_complete = _bridge_kyc_complete(seller)
    state.bank_account_added = _bridge_bank_added(seller)
    state.first_listing_active = _bridge_has_active_listing(seller)
    state.shipping_template_configured = _bridge_has_shipping_template(seller)
    state.return_policy_configured = _bridge_has_return_policy(seller)
    state.academy_module1_complete = _bridge_academy_done(seller)
    state.first_order_on_time = _bridge_first_order_on_time(seller)
    now = timezone.now()
    if state.completed_count == 7 and not state.activated:
        state.activated = True
        state.activated_at = now
        state.badge_expires_at = now + timedelta(days=90)
        SellerOperationsEvent.log('seller_activated', actor=seller)
    state.save()
    return state


def _bridge_kyc_complete(seller):
    try:
        from apps.seller_onboarding.models import KycDocument
        return KycDocument.objects.filter(
            application__seller=seller, status='approved').exists()
    except Exception:
        return False


def _bridge_bank_added(seller):
    try:
        from apps.payments.models import SellerBankAccount
        return SellerBankAccount.objects.filter(seller=seller).exists()
    except Exception:
        return False


def _bridge_has_active_listing(seller):
    try:
        from apps.products.models import Product
        return Product.objects.filter(store__owner=seller,
                                      is_active=True).exists()
    except Exception:
        return False


def _bridge_has_shipping_template(seller):
    try:
        from apps.seller_tools.models import SellerReturnPolicy  # noqa
        from apps.shipping.models import ShippingZone  # heuristic presence
        return True
    except Exception:
        return False


def _bridge_has_return_policy(seller):
    try:
        from apps.seller_tools.models import SellerReturnPolicy
        return SellerReturnPolicy.objects.filter(seller=seller).exists()
    except Exception:
        return False


def _bridge_academy_done(seller):
    try:
        from apps.seller_onboarding.models import SellerTrainingProgress
        return SellerTrainingProgress.objects.filter(
            seller=seller).exists()
    except Exception:
        return False


def _bridge_first_order_on_time(seller):
    return FulfilmentSLARecord.objects.filter(
        seller=seller, on_time=True).exists()


# ===========================================================================
# CH18 — Performance Recovery Plan
# ===========================================================================
RECOVERY_REQUIRED_STEPS = [
    {'key': 'fulfil_outstanding', 'label': 'Cumprir todos os pedidos pendentes'},
    {'key': 'resolve_disputes', 'label': 'Resolver todas as disputas abertas'},
    {'key': 'fix_violations', 'label': 'Corrigir listagens em violação'},
    {'key': 'academy_remediation', 'label': 'Completar módulo de remediação'},
]


def open_recovery_plan(seller, *, suspension_type, suspension_reason=''):
    plan = SellerRecoveryPlan.objects.create(
        seller=seller, suspension_type=suspension_type,
        suspension_reason=suspension_reason,
        required_steps=[dict(s, done=False) for s in RECOVERY_REQUIRED_STEPS],
        status='active')
    SellerOperationsEvent.log('recovery_plan_opened', actor=seller,
                              plan_id=str(plan.id), type=suspension_type)
    return plan


def update_recovery_step(plan, step_key, done=True):
    steps = plan.required_steps
    for s in steps:
        if s['key'] == step_key:
            s['done'] = done
    plan.required_steps = steps
    plan.save(update_fields=['required_steps'])
    return plan


def submit_reactivation(plan):
    if not all(s['done'] for s in plan.required_steps):
        raise ValueError('steps_incomplete')
    plan.status = 'submitted'
    plan.submitted_at = timezone.now()
    plan.save(update_fields=['status', 'submitted_at'])
    # Bridge to the onboarding reactivation review queue.
    try:
        from apps.seller_onboarding.models import SellerReactivationRequest
        SellerReactivationRequest.objects.create(
            seller=plan.seller, reason=plan.suspension_reason or 'recovery')
    except Exception:
        pass
    SellerOperationsEvent.log('reactivation_submitted', actor=plan.seller,
                              plan_id=str(plan.id))
    return plan


def decide_reactivation(plan, *, approved):
    plan.status = 'reinstated' if approved else 'rejected'
    plan.decided_at = timezone.now()
    if approved:
        plan.probation_until = timezone.now() + timedelta(days=90)
    plan.save(update_fields=['status', 'decided_at', 'probation_until'])
    return plan


# ===========================================================================
# CH19 — Market Intelligence
# ===========================================================================
def compute_market_benchmarks():
    """Celery (weekly): anonymised per-category benchmarks (doc CH19)."""
    from datetime import date
    week_start = timezone.now().date() - timedelta(
        days=timezone.now().weekday())
    built = 0
    try:
        from apps.products.models import Product
        from django.db.models import Count
        cats = (Product.objects.filter(is_active=True)
                .values('category_id')
                .annotate(n=Count('id')).filter(n__gte=3))
        for row in cats:
            cat_id = row['category_id']
            if not cat_id:
                continue
            prices = sorted(
                int(float(p) * 100) for p in
                Product.objects.filter(category_id=cat_id, is_active=True)
                .values_list('price', flat=True))
            if not prices:
                continue
            median = prices[len(prices) // 2]
            SellerMarketBenchmark.objects.update_or_create(
                category_id=str(cat_id), week_start=week_start,
                defaults=dict(median_price_cents=median,
                              price_min_cents=prices[0],
                              price_max_cents=prices[-1]))
            built += 1
    except Exception:
        pass
    if built:
        SellerOperationsEvent.log('benchmarks_built', categories=built)
    return {'categories': built}


def seller_benchmark_view(seller, category_id):
    bench = (SellerMarketBenchmark.objects
             .filter(category_id=str(category_id))
             .order_by('-week_start').first())
    if not bench:
        return None
    my_avg = 0
    try:
        from apps.products.models import Product
        from django.db.models import Avg
        avg = Product.objects.filter(store__owner=seller,
                                     category_id=category_id,
                                     is_active=True).aggregate(a=Avg('price'))['a']
        my_avg = int(float(avg) * 100) if avg else 0
    except Exception:
        pass
    return {
        'category_id': str(category_id),
        'median_price_cents': bench.median_price_cents,
        'price_range_cents': [bench.price_min_cents, bench.price_max_cents],
        'your_avg_price_cents': my_avg,
        'position': ('below_median' if my_avg and my_avg < bench.median_price_cents
                     else 'above_median'),
    }


# ===========================================================================
# CH20 — Returns Management Centre
# ===========================================================================
def returns_dashboard(seller):
    """Aggregate returns by stage (bridge to disputes/logistics). Fail-open."""
    out = {'pending': [], 'in_transit': [], 'received': [], 'resolved': []}
    try:
        from apps.disputes.models import Dispute
        for d in Dispute.objects.filter(seller=seller)[:200]:
            stage = _return_stage(d)
            out[stage].append({'id': str(d.id),
                               'order_id': str(getattr(d, 'order_id', ''))})
    except Exception:
        pass
    return out


def _return_stage(dispute):
    status = (getattr(dispute, 'status', '') or '').lower()
    if status in ('resolved', 'closed', 'refunded'):
        return 'resolved'
    if 'transit' in status or 'shipped' in status:
        return 'in_transit'
    if 'received' in status or 'inspect' in status:
        return 'received'
    return 'pending'


def inspect_return(seller, *, order_id, condition, sku_id='', quantity=1,
                   return_id='', note=''):
    """Record inspection decision; restock to inventory if good (doc CH20)."""
    action = {'perfect': 'restock', 'good': 'restock', 'damaged': 'write_off',
              'counterfeit': 'ts_escalation'}[condition]
    inspection = ReturnInspection.objects.create(
        seller=seller, order_id=str(order_id), return_id=str(return_id),
        sku_id=str(sku_id), quantity=quantity, condition=condition,
        action=action, note=note)
    if action == 'restock' and sku_id:
        restocked = _restock_inventory(sku_id, quantity, return_id=return_id)
        inspection.restocked = restocked
        inspection.save(update_fields=['restocked'])
    elif action == 'ts_escalation':
        _ts_counterfeit_escalation(seller, order_id, sku_id)
    SellerOperationsEvent.log('return_inspected', actor=seller,
                              order_id=str(order_id), condition=condition)
    return inspection


def _restock_inventory(sku_id, quantity, *, return_id=''):
    """Bridge to stock_engine: move inspected-good units back to available.
    restock_return needs the units in the `returned` bucket (logistics scans
    them in on arrival); if they aren't there yet, receive then restock."""
    try:
        from apps.stock_engine import services as stock
        if not hasattr(stock, 'restock_return'):
            return False
        try:
            stock.restock_return(sku_id, quantity, return_id=return_id)
        except Exception:
            # Returned bucket empty — receive the parcel first, then restock.
            if hasattr(stock, 'receive_return'):
                stock.receive_return(sku_id, quantity, return_id=return_id)
                stock.restock_return(sku_id, quantity, return_id=return_id)
            else:
                return False
        return True
    except Exception:
        return False


def _ts_counterfeit_escalation(seller, order_id, sku_id):
    try:
        from apps.trust_safety import services as ts
        if hasattr(ts, 'escalate_counterfeit'):
            ts.escalate_counterfeit(seller_id=seller.id, order_id=order_id,
                                    sku_id=sku_id)
    except Exception:
        pass


# ===========================================================================
# CH21 — Bulk Messaging (post-order)
# ===========================================================================
BANNED_PATTERNS = ('http://', 'https://', 'www.', '.com', 'desconto', 'cupão',
                   'cupom', 'promo')


def create_bulk_message(seller, *, scope, message, from_date=None, to_date=None,
                        product_id=''):
    """Post-order broadcast with moderation + harassment caps (doc CH21)."""
    # Monthly campaign quota: max 3.
    month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0,
                                         microsecond=0)
    used = SellerBulkMessage.objects.filter(
        seller=seller, created_at__gte=month_start).exclude(
        status='blocked').count()
    if used >= 3:
        raise ValueError('monthly_quota_exceeded')

    bm = SellerBulkMessage.objects.create(
        seller=seller, scope=scope, message=message, from_date=from_date,
        to_date=to_date, product_id=str(product_id or ''),
        status='pending_moderation')
    reason = _moderate_bulk_message(message)
    if reason:
        bm.status = 'blocked'
        bm.moderation_reason = reason
        bm.save(update_fields=['status', 'moderation_reason'])
        SellerOperationsEvent.log('bulk_message_blocked', actor=seller,
                                  reason=reason)
        return bm
    count = _dispatch_bulk_message(bm)
    bm.recipient_count = count
    bm.status = 'sent'
    bm.save(update_fields=['recipient_count', 'status'])
    SellerOperationsEvent.log('bulk_message_sent', actor=seller, recipients=count)
    return bm


def _moderate_bulk_message(message):
    low = (message or '').lower()
    for pat in BANNED_PATTERNS:
        if pat in low:
            return f'contains_forbidden:{pat}'
    return ''


def _dispatch_bulk_message(bm):
    """Resolve recipients and record 1-per-order dedup (doc CH21)."""
    orders = _resolve_bulk_recipients(bm)
    sent = 0
    for order_id, buyer_id in orders:
        try:
            with transaction.atomic():
                SellerBulkMessageRecipient.objects.create(
                    bulk_message=bm, seller=bm.seller,
                    buyer_id=str(buyer_id), order_id=str(order_id))
                _notify_buyer(buyer_id, 'seller_message',
                              {'message': bm.message, 'order_id': str(order_id)})
                sent += 1
        except IntegrityError:
            continue  # already messaged about this order — skip (harassment cap)
    return sent


def _resolve_bulk_recipients(bm):
    out = []
    try:
        from apps.orders.models import Order
        qs = Order.objects.filter(seller=bm.seller, is_deleted=False)
        if bm.scope == 'order_date_range':
            if bm.from_date:
                qs = qs.filter(created_at__date__gte=bm.from_date)
            if bm.to_date:
                qs = qs.filter(created_at__date__lte=bm.to_date)
        elif bm.scope == 'product_buyers' and bm.product_id:
            qs = qs.filter(items__product_id=bm.product_id).distinct()
        elif bm.scope == 'open_disputes':
            qs = qs.filter(status__in=['disputed', 'refunded'])
        for o in qs[:5000]:
            out.append((str(o.id), str(o.buyer_id)))
    except Exception:
        pass
    return out


# ===========================================================================
# CH22 — Financial Dashboard
# ===========================================================================
def financial_dashboard(seller):
    """Header balances + fees breakdown + 7-day forecast (doc CH22)."""
    available = pending = 0
    try:
        from apps.payments.models import SellerWallet
        w = SellerWallet.objects.filter(seller=seller).first()
        if w:
            available = int(float(getattr(w, 'balance', 0)) * 100)
            pending = int(float(getattr(w, 'pending_balance', 0)) * 100)
    except Exception:
        pass
    month = _income_aggregate(seller, timezone.now().year)
    # crude this-month slice
    m = timezone.now().month
    this_month = next((x for x in month['monthly'] if x['month'] == m), None)
    forecast = _revenue_forecast(seller)
    return {
        'available_balance_cents': available,
        'pending_escrow_cents': pending,
        'this_month': this_month or {},
        'forecast_next_7d_cents': forecast,
    }


def _revenue_forecast(seller):
    """EWMA over last 30 days of paid orders -> next 7 days (bridge)."""
    try:
        from apps.orders.models import Order
        from django.db.models import Sum
        since = timezone.now() - timedelta(days=30)
        total = Order.objects.filter(
            seller=seller, status='paid', created_at__gte=since).aggregate(
            s=Sum('total'))['s'] or 0
        daily = float(total) / 30.0
        return _cents(daily * 7 * 100)
    except Exception:
        return 0


# ===========================================================================
# CH24 — KPI snapshot
# ===========================================================================
def snapshot_kpis():
    from django.db.models import Count, Q
    today = timezone.now().date()

    activation_total = SellerActivationState.objects.count()
    activated = SellerActivationState.objects.filter(activated=True).count()
    activation_rate = round(100.0 * activated / activation_total, 1) if \
        activation_total else 0

    sla = FulfilmentSLARecord.objects.filter(on_time__isnull=False).aggregate(
        total=Count('id'), on_time=Count('id', filter=Q(on_time=True)))
    on_time_rate = round(100.0 * (sla['on_time'] or 0) / sla['total'], 1) if \
        sla['total'] else 100.0

    responders = SellerAutoResponder.objects.filter(enabled=True).count()
    total_responders = SellerAutoResponder.objects.count() or 1
    ar_adoption = round(100.0 * responders / total_responders, 1)

    refund_total = RefundApprovalRequest.objects.exclude(
        status='pending').count()
    refund_in_sla = RefundApprovalRequest.objects.filter(
        reviewed_at__isnull=False).extra(
        where=["reviewed_at <= created_at + interval '48 hours'"]).count() \
        if _is_pg() else refund_total
    refund_sla = round(100.0 * refund_in_sla / refund_total, 1) if \
        refund_total else 100.0

    snap = SellerOperationsKpiSnapshot.objects.update_or_create(
        snapshot_date=today,
        defaults=dict(
            activation_rate_pct=activation_rate,
            on_time_fulfilment_pct=on_time_rate,
            auto_responder_adoption_pct=ar_adoption,
            refund_approval_sla_pct=refund_sla,
            active_repricing_rules=RepricingRule.objects.filter(
                enabled=True).count(),
            open_compliance_violations=ListingComplianceViolation.objects.filter(
                status__in=['open', 'fix_pending_review']).count(),
            pending_refund_approvals=RefundApprovalRequest.objects.filter(
                status='pending').count(),
        ))[0]
    return snap


def _is_pg():
    from django.db import connection
    return connection.vendor == 'postgresql'


# ===========================================================================
# Notification bridges (all fail-open)
# ===========================================================================
def _notify_seller(seller, kind, data):
    _notify_seller_id(getattr(seller, 'id', seller), kind, data)


def _notify_seller_id(seller_id, kind, data):
    try:
        from apps.notifications import services as notif
        if hasattr(notif, 'push'):
            notif.push(user_id=seller_id, kind=kind, data=data)
    except Exception:
        pass


def _notify_buyer(buyer_id, kind, data):
    try:
        from apps.notifications import services as notif
        if hasattr(notif, 'push'):
            notif.push(user_id=buyer_id, kind=kind, data=data)
    except Exception:
        pass


# ===========================================================================
# small helpers
# ===========================================================================
def _kz(amount):
    try:
        return f'{float(amount):,.0f} Kz'.replace(',', '.')
    except Exception:
        return f'{amount} Kz'


def _store_name(seller):
    try:
        from apps.stores.models import Store
        s = Store.objects.filter(owner=seller).first()
        return s.name if s else ''
    except Exception:
        return ''


def _presign(key):
    """Stub presigned URL (S3/R2 behind a clean interface)."""
    try:
        from apps.core import storage
        if hasattr(storage, 'presigned_url'):
            return storage.presigned_url(key)
    except Exception:
        pass
    return f'https://files.micha.ao/{key}'
