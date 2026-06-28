"""Seller Operations API — thin views over services (doc CH2-CH24).

Auth model: the seller is request.user (store owner). Staff scoping is enforced
by services.staff_can() at the service layer where a staff context is supplied.
Endpoints are intentionally thin: validate -> call service -> serialise.
"""
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services
from .models import (
    FulfilmentSLARecord, ListingComplianceViolation, PaymentHoldDispute,
    RefundApprovalRequest, RepricingRule, SellerStaff,
)


def _err(msg, code=400):
    return Response({'detail': msg}, status=code)


# ---- CH2 staff -------------------------------------------------------------
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def staff_collection(request):
    if request.method == 'GET':
        rows = SellerStaff.objects.filter(seller=request.user).exclude(
            status='removed')
        return Response([{
            'id': str(s.id), 'full_name': s.full_name, 'email': s.email,
            'role': s.role, 'status': s.status, 'permissions': s.permissions,
        } for s in rows])
    d = request.data
    try:
        staff = services.invite_staff(
            request.user, full_name=d.get('full_name', ''),
            email=d.get('email', ''), role=d.get('role', ''),
            phone=d.get('phone', ''), invited_by=request.user)
    except ValueError as e:
        return _err(str(e))
    return Response({'id': str(staff.id), 'status': staff.status},
                    status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def staff_set_status(request, staff_id):
    staff = SellerStaff.objects.filter(id=staff_id, seller=request.user).first()
    if not staff:
        return _err('not_found', 404)
    try:
        services.set_staff_status(staff, request.data.get('status'),
                                  by=request.user)
    except ValueError as e:
        return _err(str(e))
    return Response({'id': str(staff.id), 'status': staff.status})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def staff_audit(request):
    from .models import SellerStaffAuditLog
    rows = SellerStaffAuditLog.objects.filter(seller=request.user)[:200]
    return Response([{
        'action_type': r.action_type, 'target_type': r.target_type,
        'target_id': r.target_id, 'staff_id': str(r.staff_id) if r.staff_id
        else None, 'created_at': r.created_at,
    } for r in rows])


# ---- CH3 draft/scheduled ---------------------------------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def listing_transition(request, product_id):
    try:
        state = services.transition_listing(
            product_id, request.user, request.data.get('to_status'),
            reason=request.data.get('reason', ''), actor=request.user)
    except ValueError as e:
        return _err(str(e))
    return Response({'product_id': product_id, 'status': state.status})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def listing_schedule(request, product_id):
    from django.utils.dateparse import parse_datetime
    when = parse_datetime(request.data.get('scheduled_publish_at', ''))
    if not when:
        return _err('invalid_datetime')
    try:
        state, ok = services.schedule_listing(product_id, request.user, when,
                                              actor=request.user)
    except ValueError as e:
        return _err(str(e))
    return Response({'product_id': product_id, 'status': state.status,
                     'scheduled': ok})


# ---- CH4 clone -------------------------------------------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def clone_product(request, product_id):
    try:
        if request.data.get('variations'):
            return Response(services.bulk_clone(
                product_id, request.user, request.data['variations']))
        clone = services.clone_product(product_id, request.user)
    except ValueError as e:
        return _err(str(e))
    except Exception as e:  # source not found etc.
        return _err(str(e), 404)
    return Response({'clone_product_id': str(clone.id)},
                    status=status.HTTP_201_CREATED)


# ---- CH5 repricing ---------------------------------------------------------
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def repricing_rules(request):
    if request.method == 'GET':
        rows = RepricingRule.objects.filter(seller=request.user)
        return Response([{
            'id': str(r.id), 'name': r.name, 'rule_type': r.rule_type,
            'enabled': r.enabled, 'priority': r.priority,
            'floor_price_cents': r.floor_price_cents,
            'ceiling_price_cents': r.ceiling_price_cents,
        } for r in rows])
    d = request.data
    rule = RepricingRule.objects.create(
        seller=request.user, name=d.get('name', 'rule'),
        rule_type=d.get('rule_type', 'margin_floor'),
        scope=d.get('scope', 'all_listings'), scope_ids=d.get('scope_ids', []),
        parameters=d.get('parameters', {}), priority=d.get('priority', 100),
        floor_price_cents=d.get('floor_price_cents', 0),
        ceiling_price_cents=d.get('ceiling_price_cents', 0),
        evaluation_frequency=d.get('evaluation_frequency', 'daily'))
    return Response({'id': str(rule.id)}, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def manual_price_override(request, product_id):
    try:
        services.manual_price_override(
            request.user, product_id, int(request.data.get('price_cents')))
    except (TypeError, ValueError):
        return _err('invalid_price')
    return Response({'product_id': product_id, 'overridden': True})


# ---- CH6 packing slip / export --------------------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def packing_slip(request, order_id):
    try:
        return Response(services.packing_slip_data(order_id))
    except Exception:
        return _err('not_found', 404)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_export(request):
    job = services.queue_bulk_export(
        request.user, kind=request.data.get('kind', 'order_csv'),
        order_ids=request.data.get('order_ids', []),
        filters=request.data.get('filters', {}))
    return Response({'job_id': str(job.id), 'status': job.status},
                    status=status.HTTP_202_ACCEPTED)


# ---- CH7 shipping recon ----------------------------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def shipping_recon(request):
    from .models import ShipmentCostReconciliation
    rows = ShipmentCostReconciliation.objects.filter(seller=request.user)[:200]
    return Response([{
        'id': str(r.id), 'shipment_id': r.shipment_id,
        'charged': r.shipping_fee_charged_cents,
        'actual': r.actual_carrier_cost_cents, 'difference': r.difference_cents,
        'status': r.reconciliation_status,
        'adjustment': r.seller_adjustment_cents, 'fault': r.fault,
        'contested': r.contested,
    } for r in rows])


# ---- CH8 auto-responder ----------------------------------------------------
@api_view(['GET', 'PUT'])
@permission_classes([IsAuthenticated])
def auto_responder(request):
    if request.method == 'PUT':
        r = services.upsert_auto_responder(request.user, **{
            k: v for k, v in request.data.items()
            if k in {'enabled', 'mode', 'business_hours', 'message_pt',
                     'delay_minutes', 'include_faq', 'faq_topics'}})
    else:
        from .models import SellerAutoResponder
        r = SellerAutoResponder.objects.filter(seller=request.user).first()
        if not r:
            return Response({'enabled': False})
    return Response({'enabled': r.enabled, 'mode': r.mode,
                     'message_pt': r.message_pt,
                     'business_hours': r.business_hours,
                     'include_faq': r.include_faq, 'faq_topics': r.faq_topics})


# ---- CH9 refund approval ---------------------------------------------------
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def refund_requests(request):
    if request.method == 'GET':
        rows = RefundApprovalRequest.objects.filter(seller=request.user)[:200]
        return Response([{
            'id': str(r.id), 'order_id': r.order_id,
            'amount_cents': r.amount_cents, 'status': r.status,
            'created_at': r.created_at,
        } for r in rows])
    d = request.data
    req = services.request_refund(
        request.user, order_id=d.get('order_id'),
        amount_cents=int(d.get('amount_cents', 0)),
        reason=d.get('reason', ''),
        evidence_s3_keys=d.get('evidence_s3_keys', []))
    return Response({'id': str(req.id), 'status': req.status},
                    status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def refund_review(request, request_id):
    req = RefundApprovalRequest.objects.filter(
        id=request_id, seller=request.user).first()
    if not req:
        return _err('not_found', 404)
    try:
        services.review_refund(req, approve=bool(request.data.get('approve')),
                               note=request.data.get('note', ''))
    except ValueError as e:
        return _err(str(e))
    return Response({'id': str(req.id), 'status': req.status})


# ---- CH10 income tax summary ----------------------------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def income_summary(request):
    year = int(request.data.get('year'))
    summary = services.generate_income_tax_summary(
        request.user, year, nif=request.data.get('nif', ''))
    return Response({
        'year': summary.year, 'reference': summary.statement_reference,
        'gross_sales_cents': summary.gross_sales_cents,
        'commission_cents': summary.commission_cents,
        'net_earnings_cents': summary.net_earnings_cents,
        'iva_collected_cents': summary.iva_collected_cents,
        'document_url': services._presign(summary.document_s3_key),
    })


# ---- CH11 store design -----------------------------------------------------
@api_view(['PUT'])
@permission_classes([IsAuthenticated])
def store_design(request, store_id):
    fields = {k: v for k, v in request.data.items()
              if k in {'hero_desktop_s3_key', 'hero_mobile_s3_key', 'tagline',
                       'announcement_text', 'logo_s3_key', 'description',
                       'category_focus_tags', 'featured_product_ids',
                       'featured_auto_refresh', 'sections'}}
    design = services.save_store_design(
        request.user, store_id, publish=bool(request.data.get('publish')),
        **fields)
    return Response({'store_id': store_id, 'published': design.published})


# ---- CH13 inventory alerts -------------------------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def low_stock(request):
    return Response(services.low_stock_skus(request.user))


# ---- CH14 SLA --------------------------------------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sla_dashboard(request):
    rows = FulfilmentSLARecord.objects.filter(seller=request.user)[:200]
    return Response({
        'on_time_rate': services.seller_on_time_rate(request.user),
        'orders': [{
            'order_id': r.order_id, 'sla_deadline': r.sla_deadline,
            'picked_up_at': r.picked_up_at, 'on_time': r.on_time,
            'is_late': r.is_late, 'excused': r.excused,
        } for r in rows],
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def sla_excuse(request):
    from django.utils.dateparse import parse_date
    excuse = services.register_sla_excuse(
        request.user, reason=request.data.get('reason', ''),
        date_from=parse_date(request.data.get('date_from')),
        date_to=parse_date(request.data.get('date_to')))
    return Response({'id': excuse.id, 'status': excuse.status},
                    status=status.HTTP_201_CREATED)


# ---- CH15 payment hold dispute --------------------------------------------
@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def payment_holds(request):
    if request.method == 'GET':
        rows = PaymentHoldDispute.objects.filter(seller=request.user)[:200]
        return Response([{
            'id': str(r.id), 'payout_id': r.payout_id,
            'hold_reason': r.hold_reason, 'status': r.status,
            'created_at': r.created_at,
        } for r in rows])
    d = request.data
    dispute = services.contest_payment_hold(
        request.user, payout_id=d.get('payout_id'),
        hold_reason=d.get('hold_reason', ''),
        contest_reason=d.get('contest_reason', ''),
        evidence_s3_keys=d.get('evidence_s3_keys', []))
    return Response({'id': str(dispute.id), 'status': dispute.status},
                    status=status.HTTP_201_CREATED)


# ---- CH16 compliance -------------------------------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def compliance(request):
    rows = ListingComplianceViolation.objects.filter(
        seller=request.user).exclude(status='cleared')[:200]
    return Response({
        'compliance_score': services.compliance_score(request.user),
        'violations': [{
            'id': str(r.id), 'product_id': r.product_id,
            'issue_type': r.issue_type, 'severity': r.severity,
            'action_required': r.action_required, 'deadline': r.deadline,
            'status': r.status,
        } for r in rows],
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def compliance_fix(request, violation_id):
    v = ListingComplianceViolation.objects.filter(
        id=violation_id, seller=request.user).first()
    if not v:
        return _err('not_found', 404)
    services.mark_violation_fixed(v)
    return Response({'id': str(v.id), 'status': v.status})


# ---- CH17 activation -------------------------------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def activation(request):
    state = services.recompute_activation(request.user)
    return Response({
        'completed': state.completed_count, 'total': 7,
        'activated': state.activated,
        'milestones': {f: getattr(state, f)
                       for f in state.MILESTONE_FIELDS},
    })


# ---- CH18 recovery ---------------------------------------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def recovery_submit(request, plan_id):
    from .models import SellerRecoveryPlan
    plan = SellerRecoveryPlan.objects.filter(
        id=plan_id, seller=request.user).first()
    if not plan:
        return _err('not_found', 404)
    try:
        services.submit_reactivation(plan)
    except ValueError as e:
        return _err(str(e))
    return Response({'id': str(plan.id), 'status': plan.status})


# ---- CH19 benchmarks -------------------------------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def benchmarks(request, category_id):
    data = services.seller_benchmark_view(request.user, category_id)
    if not data:
        return _err('no_data', 404)
    return Response(data)


# ---- CH20 returns ----------------------------------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def returns_centre(request):
    return Response(services.returns_dashboard(request.user))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def return_inspect(request):
    d = request.data
    insp = services.inspect_return(
        request.user, order_id=d.get('order_id'),
        condition=d.get('condition'), sku_id=d.get('sku_id', ''),
        quantity=int(d.get('quantity', 1)), return_id=d.get('return_id', ''),
        note=d.get('note', ''))
    return Response({'id': str(insp.id), 'action': insp.action,
                     'restocked': insp.restocked})


# ---- CH21 bulk messaging ---------------------------------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_message(request):
    from django.utils.dateparse import parse_date
    d = request.data
    try:
        bm = services.create_bulk_message(
            request.user, scope=d.get('scope', 'order_date_range'),
            message=d.get('message', ''),
            from_date=parse_date(d['from_date']) if d.get('from_date') else None,
            to_date=parse_date(d['to_date']) if d.get('to_date') else None,
            product_id=d.get('product_id', ''))
    except ValueError as e:
        return _err(str(e))
    return Response({'id': str(bm.id), 'status': bm.status,
                     'recipient_count': bm.recipient_count,
                     'moderation_reason': bm.moderation_reason})


# ---- CH22 financial dashboard ---------------------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def financial(request):
    return Response(services.financial_dashboard(request.user))


# ---- CH24 KPIs -------------------------------------------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def kpis(request):
    from .models import SellerOperationsKpiSnapshot
    snap = SellerOperationsKpiSnapshot.objects.order_by('-snapshot_date').first()
    if not snap:
        return Response({})
    return Response({
        'snapshot_date': snap.snapshot_date,
        'activation_rate_pct': snap.activation_rate_pct,
        'on_time_fulfilment_pct': snap.on_time_fulfilment_pct,
        'auto_responder_adoption_pct': snap.auto_responder_adoption_pct,
        'refund_approval_sla_pct': snap.refund_approval_sla_pct,
        'active_repricing_rules': snap.active_repricing_rules,
        'open_compliance_violations': snap.open_compliance_violations,
        'pending_refund_approvals': snap.pending_refund_approvals,
    })
