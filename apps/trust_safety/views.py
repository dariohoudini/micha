"""
Trust & Safety REST surface — thin views over services.py.
"""
from __future__ import annotations

from datetime import date as date_cls
from datetime import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import (
    AccountTakeoverCase, AppealRequest, BuyerFraudRing,
    BuyerTrustScore, CounterfeitCase, CsamIncident,
    DmcaCounterNotice, DmcaNotice, EnhancedDueDiligenceReview,
    HateSpeechDetection, IpComplaint, IpRightsHolder,
    LawEnforcementRequest, LegalHold, PriceGougingFlag,
    ProductRecall, ReviewFraudRing, SellerBlacklistEntry,
    TrustSafetyEvent, TrustSafetyKpiSnapshot, UserBlock,
    UserReport,
)

User = get_user_model()


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        u = getattr(request, 'user', None)
        return bool(u and u.is_authenticated and getattr(u, 'is_staff', False))


# ─── CH2 — Prohibited items ───────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def prohibited_scan_text(request):
    dets = services.scan_listing_text(
        listing_id=request.data.get('listing_id', ''),
        text=request.data.get('text', ''),
        country=request.data.get('country', ''),
    )
    return Response({'detections': [
        {'rule_code': d.rule.code, 'matched_terms': d.matched_terms,
         'action': d.action_taken} for d in dets
    ]})


@api_view(['POST'])
@permission_classes([IsAdmin])
def prohibited_scan_image(request):
    det = services.scan_listing_image(
        listing_id=request.data.get('listing_id', ''),
        image_hash=request.data.get('image_hash', ''),
    )
    if not det:
        return Response({'matched': False})
    return Response({'matched': True, 'rule_code': det.rule.code,
                     'action': det.action_taken})


# ─── CH3 — Counterfeit ────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def counterfeit_signal_record(request):
    sig = services.record_counterfeit_signal(
        listing_id=request.data.get('listing_id', ''),
        brand=request.data.get('brand', ''),
        kind=request.data.get('kind', ''),
        confidence=float(request.data.get('confidence', 0.0)),
        evidence=request.data.get('evidence') or {},
    )
    return Response({'signal_id': sig.pk}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def counterfeit_case_resolve(request):
    case = services.resolve_counterfeit_case(
        listing_id=request.data.get('listing_id', ''),
        brand=request.data.get('brand', ''),
    )
    return Response({'case_id': str(case.id),
                     'status': case.status,
                     'composite_confidence': case.composite_confidence})


# ─── CH4 — CSAM ───────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def csam_check_hash(request):
    entry = services.check_csam_hash(image_hash=request.data.get('image_hash', ''))
    if not entry:
        return Response({'matched': False})
    return Response({'matched': True, 'source': entry.list_source,
                     'list_version': entry.list_version})


@api_view(['POST'])
@permission_classes([IsAdmin])
def csam_quarantine(request):
    uploader = None
    if request.data.get('uploader_user_id'):
        uploader = User.objects.filter(pk=request.data['uploader_user_id']).first()
    inc = services.quarantine_csam(
        upload_reference=request.data.get('upload_reference', ''),
        image_hash=request.data.get('image_hash', ''),
        uploader_user=uploader,
        surface=request.data.get('surface', 'listing'),
        surface_id=request.data.get('surface_id', ''),
    )
    return Response({'incident_id': str(inc.id),
                     'status': inc.status}, status=201)


# ─── CH5 — Hate speech ────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def hate_speech_detect(request):
    author = None
    if request.data.get('author_id'):
        author = User.objects.filter(pk=request.data['author_id']).first()
    det = services.detect_hate_speech(
        surface=request.data.get('surface', 'review'),
        surface_id=request.data.get('surface_id', ''),
        text=request.data.get('text', ''),
        author=author,
    )
    if not det:
        return Response({'matched': False})
    return Response({'matched': True, 'detection_id': det.pk,
                     'kind': det.kind, 'confidence': det.confidence})


@api_view(['POST'])
@permission_classes([IsAdmin])
def hate_speech_enforce(request):
    det = get_object_or_404(HateSpeechDetection,
                              pk=request.data.get('detection_id'))
    enf = services.enforce_hate_speech(
        det,
        action=request.data.get('action', 'content_removed'),
        suspension_days=int(request.data.get('suspension_days', 0)),
        actor=request.user,
    )
    return Response({'enforcement_id': enf.pk}, status=201)


# ─── CH6 — IP complaints ─────────────────────────────────────

class IpRightsHolderView(generics.ListCreateAPIView):
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return IpRightsHolder.objects.all()

    def list(self, request):
        return Response(list(self.get_queryset().values()))

    def create(self, request):
        rh = services.register_rights_holder(
            legal_name=request.data.get('legal_name', ''),
            country=request.data.get('country', ''),
            contact_email=request.data.get('contact_email', ''),
            protected_brands=request.data.get('protected_brands') or [],
            protected_trademarks=request.data.get('protected_trademarks') or [],
        )
        return Response({'rights_holder_id': str(rh.id)}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def ip_complaint_file(request):
    rh = get_object_or_404(IpRightsHolder,
                              pk=request.data.get('rights_holder_id'))
    cmp = services.file_ip_complaint(
        rights_holder=rh,
        listing_id=request.data.get('listing_id', ''),
        kind=request.data.get('kind', 'trademark'),
        description=request.data.get('description', ''),
        evidence=request.data.get('evidence') or [],
    )
    return Response({'complaint_id': str(cmp.id),
                     'status': cmp.status,
                     'seller_response_due_at': cmp.seller_response_due_at.isoformat()},
                    status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def ip_complaint_respond(request):
    cmp = get_object_or_404(IpComplaint, pk=request.data.get('complaint_id'))
    resp = services.respond_to_ip_complaint(
        cmp,
        response_kind=request.data.get('response_kind', 'other'),
        response_text=request.data.get('response_text', ''),
        evidence_keys=request.data.get('evidence_keys') or [],
    )
    return Response({'response_id': resp.pk,
                     'status': cmp.status}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def ip_complaint_decide(request):
    cmp = get_object_or_404(IpComplaint, pk=request.data.get('complaint_id'))
    services.decide_ip_complaint(
        cmp,
        outcome=request.data.get('outcome', 'rejected'),
        notes=request.data.get('notes', ''),
    )
    return Response({'status': cmp.status})


# ─── CH7 — DMCA ───────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def dmca_file(request):
    notice = services.file_dmca_notice(payload=request.data)
    return Response({'notice_id': str(notice.id),
                     'notice_number': notice.notice_number,
                     'validation_status': notice.validation_status,
                     'failures': notice.validation_failures}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def dmca_counter_file(request):
    notice = get_object_or_404(DmcaNotice, pk=request.data.get('notice_id'))
    cn = services.file_dmca_counter_notice(notice=notice,
                                             payload=request.data)
    return Response({'counter_notice_id': cn.pk,
                     'restore_due_at': cn.restore_due_at.isoformat()},
                    status=201)


# ─── CH8 — Price gouging ─────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def price_gouging_detect(request):
    flag = services.detect_price_gouging(
        listing_id=request.data.get('listing_id', ''),
        baseline_price=Decimal(str(request.data.get('baseline_price', 0))),
        new_price=Decimal(str(request.data.get('new_price', 0))),
        currency=request.data.get('currency', 'AOA'),
        is_emergency_period=bool(request.data.get('is_emergency_period', False)),
    )
    if not flag:
        return Response({'flagged': False})
    return Response({'flagged': True, 'spike_pct': str(flag.spike_pct),
                     'action': flag.action_taken}, status=201)


# ─── CH9 — Impersonation / ban evasion ───────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def impersonation_check(request):
    user = get_object_or_404(User, pk=request.data.get('user_id'))
    chk = services.check_impersonation(
        user=user, store_name=request.data.get('store_name', ''),
    )
    if not chk:
        return Response({'matched': False})
    return Response({'matched': True, 'check_id': chk.pk,
                     'similarity_score': chk.similarity_score,
                     'legitimate_brand': chk.legitimate_brand})


@api_view(['POST'])
@permission_classes([IsAdmin])
def ban_evasion_record(request):
    new_user = get_object_or_404(User, pk=request.data.get('new_user_id'))
    banned = None
    if request.data.get('banned_user_id'):
        banned = User.objects.filter(pk=request.data['banned_user_id']).first()
    obj = services.record_ban_evasion_signal(
        new_user=new_user, banned_user=banned,
        match_kind=request.data.get('match_kind', 'device'),
        match_score=float(request.data.get('match_score', 0)),
        auto_suspend=bool(request.data.get('auto_suspend', False)),
    )
    return Response({'signal_id': obj.pk}, status=201)


# ─── CH10 — Coordinated buying ───────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def coordinated_buying_detect(request):
    seller = get_object_or_404(User, pk=request.data.get('seller_id'))
    ring = services.detect_coordinated_buying(
        seller=seller,
        suspicious_buyer_ids=request.data.get('suspicious_buyer_ids') or [],
        suspicious_order_count=int(request.data.get('suspicious_order_count', 0)),
        refund_after_review_count=int(request.data.get('refund_after_review_count', 0)),
    )
    return Response({'ring_id': str(ring.id),
                     'severity': ring.severity}, status=201)


# ─── CH11 — Age gates ────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def age_gate_check(request):
    try:
        dob = datetime.fromisoformat(request.data.get('claimed_dob', '')).date()
    except Exception:
        return Response({'detail': 'invalid claimed_dob'}, status=400)
    result = services.check_age_gate(
        user=request.user,
        category_id=request.data.get('category_id', ''),
        claimed_dob=dob,
        verification_method=request.data.get('verification_method', 'self_declared'),
    )
    return Response(result)


# ─── CH12 — Block + report ───────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def user_block(request):
    blocked = get_object_or_404(User, pk=request.data.get('blocked_user_id'))
    obj = services.create_block(
        blocker=request.user, blocked=blocked,
        blocker_kind=request.data.get('blocker_kind', 'buyer'),
        reason=request.data.get('reason', ''),
    )
    return Response({'block_id': obj.pk}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def user_report_file(request):
    subject = None
    if request.data.get('subject_user_id'):
        subject = User.objects.filter(pk=request.data['subject_user_id']).first()
    obj = services.file_user_report(
        reporter=request.user, kind=request.data.get('kind', 'other'),
        description=request.data.get('description', ''),
        subject_user=subject,
        subject_listing_id=request.data.get('subject_listing_id', ''),
        subject_review_id=request.data.get('subject_review_id', ''),
        severity=int(request.data.get('severity', 5)),
        evidence=request.data.get('evidence') or [],
    )
    return Response({'report_id': str(obj.id),
                     'triage_class': obj.triage_class}, status=201)


# ─── CH13 — Blacklist ────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def blacklist_add(request):
    entry = services.add_to_blacklist(
        legal_name=request.data.get('legal_name', ''),
        business_reg=request.data.get('business_reg', ''),
        email=request.data.get('email', ''),
        phone=request.data.get('phone', ''),
        ip_subnet=request.data.get('ip_subnet', ''),
        device_fingerprint=request.data.get('device_fingerprint', ''),
        scope=request.data.get('scope', 'global'),
        country_scope=request.data.get('country_scope') or [],
        reason_codes=request.data.get('reason_codes') or [],
        added_by=request.user,
        industry_shared=bool(request.data.get('industry_shared', False)),
    )
    return Response({'entry_id': str(entry.id)}, status=201)


@api_view(['POST'])
@permission_classes([AllowAny])
def blacklist_check(request):
    subj = None
    if request.user.is_authenticated and request.data.get('subject_user_id'):
        subj = User.objects.filter(pk=request.data['subject_user_id']).first()
    chk = services.check_blacklist(
        subject_kind=request.data.get('subject_kind', 'signup'),
        subject_user=subj,
        legal_name=request.data.get('legal_name', ''),
        business_reg=request.data.get('business_reg', ''),
        email=request.data.get('email', ''),
        phone=request.data.get('phone', ''),
        ip_subnet=request.data.get('ip_subnet', ''),
        device_fingerprint=request.data.get('device_fingerprint', ''),
    )
    return Response({'outcome': chk.outcome,
                     'match_score': chk.match_score})


# ─── CH14 — Review fraud ─────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def review_signal_record(request):
    reviewer = None
    if request.data.get('reviewer_id'):
        reviewer = User.objects.filter(pk=request.data['reviewer_id']).first()
    obj = services.record_review_signal(
        review_id=request.data.get('review_id', ''),
        signal_kind=request.data.get('signal_kind', 'reviewer_cluster'),
        confidence=float(request.data.get('confidence', 0.0)),
        reviewer=reviewer,
        listing_id=request.data.get('listing_id', ''),
        evidence=request.data.get('evidence') or {},
    )
    return Response({'signal_id': obj.pk}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def review_fraud_ring_declare(request):
    ring = services.declare_review_fraud_ring(
        member_user_ids=request.data.get('member_user_ids') or [],
        reviewed_listings=request.data.get('reviewed_listings') or [],
        signal_count=int(request.data.get('signal_count', 0)),
        confidence=float(request.data.get('confidence', 0.0)),
    )
    return Response({'ring_id': str(ring.id)}, status=201)


# ─── CH15 — ATO ──────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def ato_open(request):
    user = get_object_or_404(User, pk=request.data.get('user_id'))
    case = services.open_ato_case(
        user=user,
        detection_signals=request.data.get('detection_signals') or [],
        risk_score=int(request.data.get('risk_score', 0)),
        quarantine_action=request.data.get('quarantine_action', 'logout_all'),
    )
    return Response({'case_id': str(case.id),
                     'status': case.status}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def ato_resolve(request):
    case = get_object_or_404(AccountTakeoverCase, pk=request.data.get('case_id'))
    services.resolve_ato_case(
        case,
        status=request.data.get('status', 'recovered'),
        recovery_method=request.data.get('recovery_method', ''),
    )
    return Response({'status': case.status})


# ─── CH16 — EDD ──────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def edd_open(request):
    seller = get_object_or_404(User, pk=request.data.get('seller_id'))
    obj = services.open_edd_review(
        seller=seller,
        triggered_by=request.data.get('triggered_by', 'manual_request'),
        risk_score=int(request.data.get('risk_score', 50)),
        required_docs=request.data.get('required_docs') or [],
    )
    return Response({'review_id': str(obj.id)}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def edd_submit_docs(request):
    review = get_object_or_404(EnhancedDueDiligenceReview,
                                 pk=request.data.get('review_id'))
    services.submit_edd_documents(
        review, documents=request.data.get('documents') or [],
    )
    return Response({'status': review.status})


@api_view(['POST'])
@permission_classes([IsAdmin])
def edd_decide(request):
    review = get_object_or_404(EnhancedDueDiligenceReview,
                                 pk=request.data.get('review_id'))
    services.decide_edd_review(
        review, outcome=request.data.get('outcome', 'approved'),
        investigator=request.user,
        notes=request.data.get('notes', ''),
    )
    return Response({'status': review.status})


# ─── CH17 — Serial disputer + refund farmer ──────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def serial_disputer_signal(request):
    user = get_object_or_404(User, pk=request.data.get('user_id'))
    obj = services.emit_serial_disputer_signal(
        user=user,
        dispute_count=int(request.data.get('dispute_count', 0)),
        successful_refund_count=int(request.data.get('successful_refund_count', 0)),
        refund_total=Decimal(str(request.data.get('refund_total', 0))),
        currency=request.data.get('currency', 'AOA'),
    )
    return Response({'signal_id': obj.pk,
                     'severity': obj.severity}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def refund_farming_open(request):
    user = get_object_or_404(User, pk=request.data.get('user_id'))
    obj = services.open_refund_farming_case(
        user=user, signals=request.data.get('signals') or [],
        total_amount=Decimal(str(request.data.get('total_amount', 0))),
        currency=request.data.get('currency', 'AOA'),
        confidence=float(request.data.get('confidence', 0.0)),
    )
    return Response({'case_id': str(obj.id)}, status=201)


# ─── CH18 — Buyer fraud rings ────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def buyer_fraud_ring_declare(request):
    ring = services.declare_buyer_fraud_ring(
        fraud_pattern=request.data.get('fraud_pattern', 'chargeback_ring'),
        member_user_ids=request.data.get('member_user_ids') or [],
        total_loss_estimate=Decimal(str(request.data.get('total_loss_estimate', 0))),
        currency=request.data.get('currency', 'AOA'),
        confidence=float(request.data.get('confidence', 0.0)),
    )
    return Response({'ring_id': str(ring.id),
                     'member_count': ring.member_count}, status=201)


# ─── CH19 — Recalls ──────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def recall_initiate(request):
    obj = services.initiate_recall(
        product_id=request.data.get('product_id', ''),
        severity=request.data.get('severity', 'class_2'),
        issue_description=request.data.get('issue_description', ''),
        recall_source=request.data.get('recall_source', 'platform_initiated'),
        affected_listings=request.data.get('affected_listings') or [],
        affected_units_estimate=int(request.data.get('affected_units_estimate', 0)),
    )
    return Response({'recall_id': str(obj.id),
                     'recall_reference': obj.recall_reference}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def recall_notify(request):
    recall = get_object_or_404(ProductRecall, pk=request.data.get('recall_id'))
    user = get_object_or_404(User, pk=request.data.get('affected_user_id'))
    obj = services.notify_recall_recipient(
        recall, affected_user=user,
        order_id=request.data.get('order_id', ''),
        channel=request.data.get('channel', 'email'),
    )
    return Response({'notification_id': obj.pk}, status=201)


# ─── CH20 — Export control ───────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def export_control_check(request):
    obj = services.evaluate_export_control(
        listing_id=request.data.get('listing_id', ''),
        destination_country=request.data.get('destination_country', ''),
        category_keyword=request.data.get('category_keyword', ''),
        eccn=request.data.get('eccn', ''),
    )
    return Response({'outcome': obj.outcome, 'reason': obj.reason})


# ─── CH21 — Buyer trust score ────────────────────────────────

class MyTrustScoreView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        obj = services.compute_buyer_trust_score(request.user)
        return Response({
            'score': obj.score, 'band': obj.band,
            'components': {
                'purchase_history': obj.purchase_history_component,
                'payment_method': obj.payment_method_component,
                'dispute_history': obj.dispute_history_component,
                'review_quality': obj.review_quality_component,
                'account_age': obj.account_age_component,
                'verification': obj.verification_component,
            },
            'last_computed_at': obj.last_computed_at.isoformat(),
        })


# ─── CH22 — Appeals ──────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def appeal_file(request):
    obj = services.file_appeal(
        appellant=request.user,
        decision_kind=request.data.get('decision_kind', 'other'),
        original_decision_reference=request.data.get('original_decision_reference', ''),
        appeal_text=request.data.get('appeal_text', ''),
        supporting_evidence=request.data.get('supporting_evidence') or [],
    )
    return Response({'appeal_id': str(obj.id),
                     'response_due_at': obj.response_due_at.isoformat()},
                    status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def appeal_decide(request):
    appeal = get_object_or_404(AppealRequest, pk=request.data.get('appeal_id'))
    services.decide_appeal(
        appeal,
        decision=request.data.get('decision', 'denied'),
        decision_reason=request.data.get('decision_reason', ''),
        reviewer=request.user,
    )
    return Response({'status': appeal.status})


# ─── CH23 — LE requests + legal hold ─────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def le_request_receive(request):
    subj = None
    if request.data.get('subject_user_id'):
        subj = User.objects.filter(pk=request.data['subject_user_id']).first()
    obj = services.receive_le_request(
        agency=request.data.get('agency', ''),
        jurisdiction=request.data.get('jurisdiction', ''),
        request_kind=request.data.get('request_kind', 'subpoena'),
        subject_user=subj,
        requested_data=request.data.get('requested_data') or [],
        case_number=request.data.get('case_number', ''),
        deadline_days=int(request.data.get('deadline_days', 14)),
        legal_document_key=request.data.get('legal_document_key', ''),
        user_notified=bool(request.data.get('user_notified', True)),
    )
    return Response({'request_id': str(obj.id)}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def le_request_respond(request):
    req = get_object_or_404(LawEnforcementRequest,
                              pk=request.data.get('request_id'))
    services.respond_to_le_request(
        req,
        status=request.data.get('status', 'responded'),
        response_notes=request.data.get('response_notes', ''),
        handled_by=request.user,
    )
    return Response({'status': req.status})


@api_view(['POST'])
@permission_classes([IsAdmin])
def legal_hold_start(request):
    user = get_object_or_404(User, pk=request.data.get('subject_user_id'))
    rel = None
    if request.data.get('le_request_id'):
        rel = LawEnforcementRequest.objects.filter(
            pk=request.data['le_request_id']).first()
    hold = services.start_legal_hold(
        subject_user=user,
        description=request.data.get('description', ''),
        scope=request.data.get('scope') or [],
        related_request=rel,
    )
    return Response({'hold_id': str(hold.id)}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def legal_hold_release(request):
    hold = get_object_or_404(LegalHold, pk=request.data.get('hold_id'))
    services.release_legal_hold(hold)
    return Response({'released_at': hold.released_at.isoformat()})


# ─── CH24 — KPI ──────────────────────────────────────────────

class TsKpiView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        d_str = request.query_params.get('date')
        d = date_cls.fromisoformat(d_str) if d_str else timezone.now().date()
        snap = TrustSafetyKpiSnapshot.objects.filter(snapshot_date=d).first()
        if not snap:
            snap = services.snapshot_ts_kpis(snapshot_date=d)
        return Response({
            'date': str(snap.snapshot_date),
            'prohibited_detections': snap.prohibited_detections,
            'counterfeit_cases_opened': snap.counterfeit_cases_opened,
            'counterfeit_listings_removed': snap.counterfeit_listings_removed,
            'csam_incidents': snap.csam_incidents,
            'hate_speech_actions': snap.hate_speech_actions,
            'ip_complaints_filed': snap.ip_complaints_filed,
            'dmca_notices_filed': snap.dmca_notices_filed,
            'price_gouging_flags': snap.price_gouging_flags,
            'blacklist_hits': snap.blacklist_hits,
            'review_fraud_rings': snap.review_fraud_rings,
            'ato_cases': snap.ato_cases,
            'edd_reviews_pending': snap.edd_reviews_pending,
            'serial_disputers_flagged': snap.serial_disputers_flagged,
            'buyer_fraud_rings': snap.buyer_fraud_rings,
            'recalls_active': snap.recalls_active,
            'appeals_open': snap.appeals_open,
            'le_requests_received': snap.le_requests_received,
            'le_requests_overdue': snap.le_requests_overdue,
            'auto_action_rate': snap.auto_action_rate,
            'by_category': snap.by_category,
            'by_surface': snap.by_surface,
        })
