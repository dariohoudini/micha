"""
Trust & Safety — domain services.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date as date_cls
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models as django_models
from django.db import transaction
from django.utils import timezone

from .models import (
    AccountTakeoverCase, AgeGateChallenge, AgeGatedCategory,
    AppealDecision, AppealRequest, BanEvasionSignal,
    BlacklistCheck, BrandKeywordWatch, BuyerFraudRing,
    BuyerFraudRingMember, BuyerTrustScore, CounterfeitCase,
    CounterfeitSignal, CoordinatedBuyingRing, CsamHashEntry,
    CsamIncident, DmcaCounterNotice, DmcaNotice,
    EnhancedDueDiligenceReview, ExportControlListing,
    HateSpeechDetection, HateSpeechEnforcement, ImpersonationCheck,
    IpComplaint, IpComplaintResponse, IpRightsHolder,
    LawEnforcementRequest, LegalHold, ManipulationFlag,
    PriceGougingFlag, ProductRecall, ProhibitedItemDetection,
    ProhibitedItemRule, RecallNotification, RefundFarmingCase,
    ReviewAuthenticitySignal, ReviewFraudRing, SellerBlacklistEntry,
    SerialDisputerSignal, TrustSafetyEvent, TrustSafetyKpiSnapshot,
    TsDecision, TsModel, UserBlock, UserReport,
)

User = get_user_model()
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# CH1 — Decision recorder
# ═══════════════════════════════════════════════════════════════════

def record_decision(*, model_code: str, surface: str,
                      subject_kind: str, subject_id: str,
                      confidence: float, outcome: str,
                      features: dict = None,
                      matched_rules: list = None) -> TsDecision:
    """Append-only decision log. Every model-fired ruling lands here
    so the bias audit + replay can run later."""
    model = (
        TsModel.objects.filter(code=model_code).first()
        or TsModel.objects.create(
            code=model_code[:40], name=model_code, kind='rule_engine',
            version='v0', is_active=True,
        )
    )
    return TsDecision.objects.create(
        model=model, surface=surface[:24],
        subject_kind=subject_kind, subject_id=subject_id[:64],
        confidence=confidence, outcome=outcome,
        features=features or {}, matched_rules=matched_rules or [],
    )


# ═══════════════════════════════════════════════════════════════════
# CH2 — Prohibited items
# ═══════════════════════════════════════════════════════════════════

_DEF_TOKEN_RE = re.compile(r'[a-z0-9]+')


def _tokenise(text: str) -> set[str]:
    return set(_DEF_TOKEN_RE.findall((text or '').lower()))


def scan_listing_text(*, listing_id: str, text: str,
                        seller=None, country: str = '') -> list[ProhibitedItemDetection]:
    """Scan listing text against active prohibited-item rules.
    Returns the detections written + emits a `record_decision` row per."""
    tokens = _tokenise(text)
    out = []
    rules = ProhibitedItemRule.objects.filter(is_active=True)
    for rule in rules:
        if rule.country_scope and country.upper() not in [
            c.upper() for c in rule.country_scope
        ]:
            continue
        rule_terms = {str(k).lower() for k in rule.keywords or []}
        matched = rule_terms & tokens
        if not matched:
            continue
        det = ProhibitedItemDetection.objects.create(
            rule=rule, listing_id=listing_id[:64], seller=seller,
            matched_kind='text', matched_terms=list(matched),
            action_taken=rule.enforcement,
        )
        record_decision(
            model_code='prohibited_text_v0', surface='listing',
            subject_kind='listing', subject_id=listing_id,
            confidence=0.85, outcome=rule.enforcement,
            features={'matched_terms': list(matched),
                       'category': rule.category},
            matched_rules=[rule.code],
        )
        TrustSafetyEvent.log(
            kind='prohibited.text_match', subject_kind='listing',
            subject_id=listing_id, user=seller,
            payload={'rule': rule.code, 'category': rule.category,
                     'terms': list(matched)},
        )
        out.append(det)
    return out


def scan_listing_image(*, listing_id: str, image_hash: str,
                         seller=None) -> ProhibitedItemDetection | None:
    """Match the image perceptual hash against rule prefixes."""
    rules = ProhibitedItemRule.objects.filter(
        is_active=True, image_hash_prefixes__len__gt=0,
    )
    for rule in rules:
        for prefix in (rule.image_hash_prefixes or []):
            if image_hash.startswith(prefix):
                det = ProhibitedItemDetection.objects.create(
                    rule=rule, listing_id=listing_id[:64], seller=seller,
                    matched_kind='image',
                    matched_image_hash=image_hash[:64],
                    action_taken=rule.enforcement,
                )
                record_decision(
                    model_code='prohibited_image_v0', surface='listing',
                    subject_kind='image', subject_id=image_hash,
                    confidence=0.9, outcome=rule.enforcement,
                    features={'prefix': prefix},
                    matched_rules=[rule.code],
                )
                return det
    return None


# ═══════════════════════════════════════════════════════════════════
# CH3 — Counterfeit decision tree
# ═══════════════════════════════════════════════════════════════════

def record_counterfeit_signal(*, listing_id: str, brand: str,
                                 kind: str, confidence: float,
                                 evidence: dict = None) -> CounterfeitSignal:
    return CounterfeitSignal.objects.create(
        listing_id=listing_id[:64], brand=brand[:120],
        kind=kind, confidence=confidence,
        evidence=evidence or {},
    )


@transaction.atomic
def resolve_counterfeit_case(*, listing_id: str, seller=None,
                                brand: str = '') -> CounterfeitCase:
    """CH3.3 — aggregate signals on a listing and walk the
    enforcement ladder. Idempotent on (listing_id)."""
    signals = list(CounterfeitSignal.objects.filter(listing_id=listing_id))
    composite = 0.0
    if signals:
        composite = max(s.confidence for s in signals)
        # Boost confidence if multiple signal kinds.
        if len(set(s.kind for s in signals)) >= 2:
            composite = min(0.99, composite + 0.05)

    case, _ = CounterfeitCase.objects.get_or_create(
        listing_id=listing_id[:64],
        defaults={'seller': seller, 'brand': brand[:120]},
    )
    case.signal_count = len(signals)
    case.composite_confidence = composite

    # Repeat offence count from history.
    if seller:
        case.repeat_offence_count = CounterfeitCase.objects.filter(
            seller=seller, status__in=('listing_removed', 'seller_banned'),
        ).exclude(pk=case.pk).count()

    # Enforcement ladder.
    if composite >= 0.95:
        case.status = ('seller_banned' if case.repeat_offence_count >= 2
                       else 'listing_removed')
    elif composite >= 0.85:
        case.status = 'seller_warned'
    else:
        case.status = 'open'

    case.decided_at = timezone.now() if case.status != 'open' else None
    case.save()
    TrustSafetyEvent.log(
        kind=f'counterfeit.{case.status}',
        subject_kind='listing', subject_id=listing_id,
        payload={'confidence': composite,
                 'repeat_offences': case.repeat_offence_count},
    )
    return case


# ═══════════════════════════════════════════════════════════════════
# CH4 — CSAM
# ═══════════════════════════════════════════════════════════════════

def check_csam_hash(image_hash: str) -> CsamHashEntry | None:
    return CsamHashEntry.objects.filter(hash_value=image_hash[:64]).first()


@transaction.atomic
def quarantine_csam(*, upload_reference: str, image_hash: str,
                      uploader_user=None, surface: str = 'listing',
                      surface_id: str = '') -> CsamIncident:
    """CH4.2 — immediate response protocol. Quarantines the upload,
    bans the user (if known), and queues an NCMEC report. The function
    deliberately captures the minimum PII needed."""
    inc = CsamIncident.objects.create(
        upload_reference=upload_reference[:120],
        matched_hash=image_hash[:64],
        uploader_user=uploader_user,
        surface=surface[:24], surface_id=surface_id[:64],
    )
    # Auto-ban uploader if linked.
    if uploader_user and hasattr(uploader_user, 'is_active'):
        uploader_user.is_active = False
        uploader_user.save(update_fields=['is_active'])
    TrustSafetyEvent.log(
        kind='csam.detected', subject_kind=surface,
        subject_id=surface_id or upload_reference,
        user=uploader_user,
        payload={'incident_id': str(inc.id)},
    )
    return inc


def report_csam_to_ncmec(incident: CsamIncident, *,
                            ncmec_report_id: str) -> CsamIncident:
    incident.status = 'reported_ncmec'
    incident.ncmec_report_id = ncmec_report_id[:120]
    incident.reported_at = timezone.now()
    incident.save(update_fields=['status', 'ncmec_report_id', 'reported_at'])
    return incident


# ═══════════════════════════════════════════════════════════════════
# CH5 — Hate speech
# ═══════════════════════════════════════════════════════════════════

# Very small dev-time keyword list. Production swaps in a fine-tuned
# classifier; we keep the interface the same.
_HATE_SEEDS = {
    'hate_race':          ('racial slur', 'nigg', 'wetb'),
    'hate_religion':      ('jew sho', 'kill muslim', 'crusade christian'),
    'hate_sexual_orient': ('faggot', 'kill gay'),
    'hate_gender':        ('tranny',),
    'extremism_violent':  ('bomb the', 'shoot up', 'genocide'),
    'threat_specific':    ('kill you', 'will hurt'),
    'harassment':         ('idiot', 'loser', 'stupid'),
}


def detect_hate_speech(*, surface: str, surface_id: str,
                          text: str, author=None) -> HateSpeechDetection | None:
    t = (text or '').lower()
    for kind, seeds in _HATE_SEEDS.items():
        for seed in seeds:
            if seed in t:
                # Harassment is lower confidence than violent extremism.
                conf = 0.7 if kind == 'harassment' else 0.92
                det = HateSpeechDetection.objects.create(
                    surface=surface[:24], surface_id=surface_id[:64],
                    author=author, text_excerpt=text[:2000],
                    kind=kind, confidence=conf,
                )
                record_decision(
                    model_code='hate_speech_v0', surface=surface,
                    subject_kind=surface,
                    subject_id=surface_id, confidence=conf,
                    outcome='auto_remove' if conf > 0.9 else 'flag_for_review',
                    features={'kind': kind, 'matched_seed': seed},
                )
                return det
    return None


def enforce_hate_speech(detection: HateSpeechDetection,
                          *, action: str,
                          suspension_days: int = 0,
                          actor=None) -> HateSpeechEnforcement:
    return HateSpeechEnforcement.objects.create(
        detection=detection, action=action,
        suspension_days=suspension_days,
        actor=actor,
        actor_kind='reviewer' if actor else 'auto',
    )


# ═══════════════════════════════════════════════════════════════════
# CH6 — IP complaints
# ═══════════════════════════════════════════════════════════════════

def register_rights_holder(*, legal_name: str, country: str,
                              contact_email: str,
                              protected_brands: list = None,
                              protected_trademarks: list = None,
                              contact_phone: str = '') -> IpRightsHolder:
    return IpRightsHolder.objects.create(
        legal_name=legal_name[:200], country=country[:2],
        contact_email=contact_email, contact_phone=contact_phone[:30],
        protected_brands=protected_brands or [],
        protected_trademarks=protected_trademarks or [],
    )


def verify_rights_holder(rh: IpRightsHolder, *,
                            doc_key: str = '') -> IpRightsHolder:
    rh.verified = True
    rh.verification_doc_key = doc_key[:255]
    rh.verified_at = timezone.now()
    rh.save(update_fields=['verified', 'verification_doc_key', 'verified_at'])
    return rh


def file_ip_complaint(*, rights_holder: IpRightsHolder,
                        listing_id: str, kind: str,
                        description: str,
                        evidence: list = None,
                        seller=None,
                        response_window_days: int = 5,
                        decision_window_days: int = 10) -> IpComplaint:
    now = timezone.now()
    cmp = IpComplaint.objects.create(
        rights_holder=rights_holder, listing_id=listing_id[:64],
        seller=seller, kind=kind,
        description=description[:10000],
        supporting_evidence=evidence or [],
        status='seller_notified',
        seller_response_due_at=now + timedelta(days=response_window_days),
        decision_due_at=now + timedelta(days=decision_window_days),
    )
    TrustSafetyEvent.log(
        kind='ip.complaint_filed', subject_kind='listing',
        subject_id=listing_id, user=seller,
        payload={'complaint_id': str(cmp.id), 'kind': kind,
                 'rights_holder': str(rights_holder.id)},
    )
    return cmp


def respond_to_ip_complaint(complaint: IpComplaint, *,
                                response_kind: str, response_text: str,
                                evidence_keys: list = None) -> IpComplaintResponse:
    resp = IpComplaintResponse.objects.create(
        complaint=complaint, response_kind=response_kind,
        response_text=response_text[:10000],
        evidence_keys=evidence_keys or [],
    )
    complaint.status = 'seller_responded'
    complaint.save(update_fields=['status'])
    return resp


def decide_ip_complaint(complaint: IpComplaint, *,
                          outcome: str, notes: str = '') -> IpComplaint:
    complaint.status = outcome
    complaint.decision_notes = notes[:10000]
    complaint.decided_at = timezone.now()
    complaint.save(update_fields=['status', 'decision_notes', 'decided_at'])
    TrustSafetyEvent.log(
        kind=f'ip.complaint_{outcome}', subject_kind='listing',
        subject_id=complaint.listing_id,
        payload={'complaint_id': str(complaint.id), 'outcome': outcome},
    )
    return complaint


# ═══════════════════════════════════════════════════════════════════
# CH7 — DMCA
# ═══════════════════════════════════════════════════════════════════

# Required elements per 17 USC §512(c)(3).
_DMCA_REQUIRED = (
    'submitter_name', 'submitter_email', 'works_described',
    'allegedly_infringing_urls', 'good_faith_statement',
    'accuracy_statement', 'authorised_signature',
)


def validate_dmca_notice(*, payload: dict) -> dict:
    failures = []
    for key in _DMCA_REQUIRED:
        v = payload.get(key)
        if v is None or v == '' or v == [] or v is False:
            failures.append(key)
    return {'valid': not failures, 'failures': failures}


@transaction.atomic
def file_dmca_notice(*, payload: dict) -> DmcaNotice:
    """Create the notice; mark valid/invalid based on the 6-element
    check. Production also runs a name/email sanity check."""
    validation = validate_dmca_notice(payload=payload)
    notice = DmcaNotice.objects.create(
        notice_number=f'DMCA-{timezone.now().strftime("%Y%m%d")}-' +
                        hashlib.sha256(
                          (str(payload) + str(timezone.now())).encode()
                        ).hexdigest()[:6].upper(),
        submitter_name=(payload.get('submitter_name') or '')[:200],
        submitter_email=payload.get('submitter_email') or '',
        submitter_phone=(payload.get('submitter_phone') or '')[:30],
        works_described=(payload.get('works_described') or '')[:10000],
        allegedly_infringing_urls=payload.get('allegedly_infringing_urls') or [],
        listing_id=(payload.get('listing_id') or '')[:64],
        good_faith_statement=bool(payload.get('good_faith_statement')),
        accuracy_statement=bool(payload.get('accuracy_statement')),
        authorised_signature=(payload.get('authorised_signature') or '')[:200],
        validation_status='valid' if validation['valid'] else 'invalid',
        validation_failures=validation['failures'],
    )
    if validation['valid']:
        notice.validation_status = 'processed'
        notice.listing_removed_at = timezone.now()
        notice.save(update_fields=['validation_status', 'listing_removed_at'])
    return notice


def file_dmca_counter_notice(*, notice: DmcaNotice,
                                payload: dict) -> DmcaCounterNotice:
    """10-14 business day restore window per spec; we use 14
    calendar days for the dev default."""
    cn = DmcaCounterNotice.objects.create(
        notice=notice,
        submitter_name=(payload.get('submitter_name') or '')[:200],
        submitter_email=payload.get('submitter_email') or '',
        perjury_statement=bool(payload.get('perjury_statement')),
        jurisdiction_statement=bool(payload.get('jurisdiction_statement')),
        counter_signature=(payload.get('counter_signature') or '')[:200],
        restore_due_at=timezone.now() + timedelta(days=14),
    )
    notice.validation_status = 'counter_notified'
    notice.save(update_fields=['validation_status'])
    return cn


# ═══════════════════════════════════════════════════════════════════
# CH8 — Price gouging
# ═══════════════════════════════════════════════════════════════════

def detect_price_gouging(*, listing_id: str, baseline_price: Decimal,
                            new_price: Decimal,
                            currency: str = 'AOA',
                            seller=None,
                            is_emergency_period: bool = False,
                            threshold_pct: Decimal = Decimal('40')) -> PriceGougingFlag | None:
    if baseline_price <= 0:
        return None
    spike = ((new_price - baseline_price) / baseline_price * Decimal(100)).quantize(Decimal('0.01'))
    if spike < threshold_pct and not is_emergency_period:
        return None
    flag = PriceGougingFlag.objects.create(
        listing_id=listing_id[:64], seller=seller,
        baseline_price=baseline_price, new_price=new_price,
        currency=currency[:3], spike_pct=spike,
        is_emergency_period=is_emergency_period,
    )
    record_decision(
        model_code='price_gouging_v0', surface='listing',
        subject_kind='listing', subject_id=listing_id,
        confidence=0.9 if is_emergency_period else 0.7,
        outcome='listing_suspended' if is_emergency_period else 'flag_for_review',
        features={'spike_pct': str(spike)},
    )
    return flag


# ═══════════════════════════════════════════════════════════════════
# CH9 — Impersonation + ban evasion
# ═══════════════════════════════════════════════════════════════════

def check_impersonation(*, user, store_name: str) -> ImpersonationCheck | None:
    """Compare candidate store name against registered brand
    keywords. Naive Levenshtein-lite using token overlap."""
    candidate_tokens = _tokenise(store_name)
    if not candidate_tokens:
        return None
    qs = BrandKeywordWatch.objects.filter(is_active=True)
    best_brand = ''
    best_overlap = 0.0
    matched = []
    for w in qs:
        b_tokens = _tokenise(w.brand)
        if not b_tokens:
            continue
        intersect = candidate_tokens & b_tokens
        overlap = len(intersect) / max(len(b_tokens), 1)
        if overlap > best_overlap:
            best_overlap = overlap
            best_brand = w.brand
            matched = list(intersect)
    if best_overlap < 0.5:
        return None
    return ImpersonationCheck.objects.create(
        suspect_user=user, suspect_store_name=store_name[:200],
        legitimate_brand=best_brand[:120],
        similarity_score=best_overlap,
        matched_brand_keywords=matched,
        status='pending',
    )


def record_ban_evasion_signal(*, new_user, banned_user=None,
                                  match_kind: str,
                                  match_score: float,
                                  auto_suspend: bool = False) -> BanEvasionSignal:
    obj = BanEvasionSignal.objects.create(
        new_user=new_user, banned_user=banned_user,
        match_kind=match_kind, match_score=match_score,
        auto_suspended=auto_suspend,
    )
    if auto_suspend and hasattr(new_user, 'is_active') and new_user.is_active:
        new_user.is_active = False
        new_user.save(update_fields=['is_active'])
    TrustSafetyEvent.log(
        kind='ban_evasion.detected', user=new_user,
        payload={'match_kind': match_kind,
                 'match_score': match_score,
                 'auto_suspend': auto_suspend},
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH10 — Coordinated buying / manipulation
# ═══════════════════════════════════════════════════════════════════

def detect_coordinated_buying(*, seller,
                                 suspicious_buyer_ids: list[int],
                                 suspicious_order_count: int = 0,
                                 refund_after_review_count: int = 0,
                                 window_days: int = 14) -> CoordinatedBuyingRing:
    severity = min(100, 30 + suspicious_order_count * 2 + refund_after_review_count * 5)
    return CoordinatedBuyingRing.objects.create(
        seller=seller, member_user_ids=suspicious_buyer_ids,
        suspicious_order_count=suspicious_order_count,
        refund_after_review_count=refund_after_review_count,
        detection_window_days=window_days,
        severity=severity,
    )


def flag_manipulation(*, listing_id: str, kind: str,
                        seller=None, evidence: dict = None) -> ManipulationFlag:
    return ManipulationFlag.objects.create(
        listing_id=listing_id[:64], seller=seller,
        kind=kind, evidence=evidence or {},
    )


# ═══════════════════════════════════════════════════════════════════
# CH11 — Age gates
# ═══════════════════════════════════════════════════════════════════

def check_age_gate(*, user, category_id: str,
                      claimed_dob: date_cls,
                      verification_method: str = 'self_declared') -> dict:
    rule = AgeGatedCategory.objects.filter(
        category_id=category_id[:64], is_active=True,
    ).first()
    if not rule:
        return {'gate_required': False, 'passed': True}
    today = date_cls.today()
    age = (today.year - claimed_dob.year -
           ((today.month, today.day) < (claimed_dob.month, claimed_dob.day)))
    passed = age >= rule.min_age
    AgeGateChallenge.objects.create(
        user=user, category_id=category_id[:64],
        claimed_dob=claimed_dob, passed=passed,
        verification_method=verification_method,
    )
    return {'gate_required': True, 'passed': passed,
            'min_age': rule.min_age, 'computed_age': age,
            'requires_id': rule.requires_id}


# ═══════════════════════════════════════════════════════════════════
# CH12 — Block + report
# ═══════════════════════════════════════════════════════════════════

def create_block(*, blocker, blocked, blocker_kind: str = 'buyer',
                   reason: str = '') -> UserBlock:
    obj, _ = UserBlock.objects.get_or_create(
        blocker=blocker, blocked=blocked,
        defaults={'blocker_kind': blocker_kind,
                  'reason': reason[:120]},
    )
    return obj


def file_user_report(*, reporter, kind: str, description: str,
                       subject_user=None,
                       subject_listing_id: str = '',
                       subject_review_id: str = '',
                       severity: int = 5,
                       evidence: list = None) -> UserReport:
    triage = ('p1' if severity >= 8 else
              'p2' if severity >= 6 else
              'p3' if severity >= 4 else 'p4')
    obj = UserReport.objects.create(
        reporter=reporter, subject_user=subject_user,
        subject_listing_id=subject_listing_id[:64],
        subject_review_id=subject_review_id[:64],
        kind=kind, severity=severity,
        triage_class=triage,
        description=description[:10000],
        evidence=evidence or [],
    )
    TrustSafetyEvent.log(
        kind='user_report.filed', subject_kind='user',
        subject_id=str(subject_user.pk) if subject_user else '',
        actor=reporter,
        payload={'report_id': str(obj.id), 'kind': kind,
                 'triage': triage},
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH13 — Seller blacklist
# ═══════════════════════════════════════════════════════════════════

def _h(value: str) -> str:
    return hashlib.sha256((value or '').strip().lower().encode()).hexdigest()


def add_to_blacklist(*, legal_name: str = '', business_reg: str = '',
                       email: str = '', phone: str = '',
                       ip_subnet: str = '',
                       device_fingerprint: str = '',
                       scope: str = 'global',
                       country_scope: list = None,
                       reason_codes: list = None,
                       added_by=None,
                       expiry: date_cls = None,
                       industry_shared: bool = False) -> SellerBlacklistEntry:
    return SellerBlacklistEntry.objects.create(
        legal_name_hash=_h(legal_name) if legal_name else '',
        business_reg_hash=_h(business_reg) if business_reg else '',
        email_hash=_h(email) if email else '',
        phone_hash=_h(phone) if phone else '',
        ip_subnet=ip_subnet[:64], device_fingerprint=device_fingerprint[:64],
        scope=scope, country_scope=country_scope or [],
        reason_codes=reason_codes or [],
        added_by=added_by, expiry=expiry,
        industry_shared=industry_shared,
    )


def check_blacklist(*, subject_kind: str = 'signup',
                      subject_user=None,
                      legal_name: str = '', business_reg: str = '',
                      email: str = '', phone: str = '',
                      ip_subnet: str = '',
                      device_fingerprint: str = '') -> BlacklistCheck:
    """Walks active blacklist entries; first hash hit produces a
    match. Records the check either way for compliance."""
    now = timezone.now().date()
    qs = SellerBlacklistEntry.objects.filter(
        django_models.Q(expiry__isnull=True) | django_models.Q(expiry__gte=now)
    )
    hashes = {
        'legal_name_hash': _h(legal_name) if legal_name else '',
        'business_reg_hash': _h(business_reg) if business_reg else '',
        'email_hash': _h(email) if email else '',
        'phone_hash': _h(phone) if phone else '',
    }
    match = None
    score = 0.0
    for entry in qs:
        if (hashes['email_hash'] and entry.email_hash == hashes['email_hash']):
            match = entry; score = 0.95; break
        if (hashes['business_reg_hash'] and entry.business_reg_hash == hashes['business_reg_hash']):
            match = entry; score = 0.93; break
        if (hashes['legal_name_hash'] and entry.legal_name_hash == hashes['legal_name_hash']):
            match = entry; score = 0.85; break
        if (hashes['phone_hash'] and entry.phone_hash == hashes['phone_hash']):
            match = entry; score = 0.8; break
        if (device_fingerprint and entry.device_fingerprint == device_fingerprint):
            match = entry; score = 0.75; break
    outcome = 'blocked' if match and score >= 0.85 else ('review' if match else 'allowed')
    return BlacklistCheck.objects.create(
        subject_kind=subject_kind, subject_user=subject_user,
        matched_entry=match, match_score=score, outcome=outcome,
    )


# ═══════════════════════════════════════════════════════════════════
# CH14 — Review fraud
# ═══════════════════════════════════════════════════════════════════

def record_review_signal(*, review_id: str, signal_kind: str,
                            confidence: float,
                            reviewer=None,
                            listing_id: str = '',
                            evidence: dict = None) -> ReviewAuthenticitySignal:
    return ReviewAuthenticitySignal.objects.create(
        review_id=review_id[:64], reviewer=reviewer,
        listing_id=listing_id[:64],
        signal_kind=signal_kind, confidence=confidence,
        evidence=evidence or {},
    )


def declare_review_fraud_ring(*, member_user_ids: list[int],
                                  reviewed_listings: list = None,
                                  signal_count: int = 0,
                                  confidence: float = 0.0) -> ReviewFraudRing:
    return ReviewFraudRing.objects.create(
        member_user_ids=member_user_ids,
        reviewed_listings=reviewed_listings or [],
        signal_count=signal_count,
        confidence=confidence,
    )


# ═══════════════════════════════════════════════════════════════════
# CH15 — Account takeover
# ═══════════════════════════════════════════════════════════════════

def open_ato_case(*, user, detection_signals: list,
                     risk_score: int = 0,
                     quarantine_action: str = 'logout_all') -> AccountTakeoverCase:
    obj = AccountTakeoverCase.objects.create(
        user=user, detection_signals=detection_signals,
        risk_score=risk_score, status='detected',
        quarantine_action=quarantine_action,
    )
    if quarantine_action in ('logout_all', 'block_payouts', 'require_2fa'):
        obj.status = 'quarantined'
        obj.save(update_fields=['status'])
    TrustSafetyEvent.log(
        kind='ato.detected', user=user,
        payload={'risk_score': risk_score,
                 'action': quarantine_action},
    )
    return obj


def resolve_ato_case(case: AccountTakeoverCase, *,
                        status: str, recovery_method: str = '') -> AccountTakeoverCase:
    case.status = status
    case.recovery_method = recovery_method[:24]
    case.resolved_at = timezone.now()
    case.save(update_fields=['status', 'recovery_method', 'resolved_at'])
    return case


# ═══════════════════════════════════════════════════════════════════
# CH16 — Enhanced due diligence
# ═══════════════════════════════════════════════════════════════════

def open_edd_review(*, seller, triggered_by: str,
                      risk_score: int = 50,
                      required_docs: list = None) -> EnhancedDueDiligenceReview:
    return EnhancedDueDiligenceReview.objects.create(
        seller=seller, triggered_by=triggered_by,
        risk_score=risk_score,
        required_docs=required_docs or ['business_registration', 'rep_id', 'bank_statement'],
    )


def submit_edd_documents(review: EnhancedDueDiligenceReview, *,
                            documents: list) -> EnhancedDueDiligenceReview:
    review.documents_received = documents
    review.status = 'docs_received'
    review.save(update_fields=['documents_received', 'status'])
    return review


def decide_edd_review(review: EnhancedDueDiligenceReview, *,
                        outcome: str,
                        investigator,
                        notes: str = '') -> EnhancedDueDiligenceReview:
    review.status = outcome
    review.investigator = investigator
    review.decision_notes = notes[:10000]
    review.decided_at = timezone.now()
    review.save(update_fields=['status', 'investigator',
                                 'decision_notes', 'decided_at'])
    return review


# ═══════════════════════════════════════════════════════════════════
# CH17 — Serial disputer + refund farming
# ═══════════════════════════════════════════════════════════════════

def emit_serial_disputer_signal(*, user, window_days: int = 90,
                                    dispute_count: int = 0,
                                    successful_refund_count: int = 0,
                                    refund_total: Decimal = Decimal('0'),
                                    currency: str = 'AOA') -> SerialDisputerSignal:
    severity = min(100, dispute_count * 5 + successful_refund_count * 8)
    return SerialDisputerSignal.objects.create(
        user=user, detection_window_days=window_days,
        dispute_count=dispute_count,
        successful_refund_count=successful_refund_count,
        refund_total=refund_total, currency=currency[:3],
        severity=severity,
    )


def open_refund_farming_case(*, user, signals: list,
                                total_amount: Decimal,
                                currency: str = 'AOA',
                                confidence: float = 0.0) -> RefundFarmingCase:
    return RefundFarmingCase.objects.create(
        user=user, signals=signals,
        total_refund_amount=total_amount, currency=currency[:3],
        confidence=confidence,
    )


# ═══════════════════════════════════════════════════════════════════
# CH18 — Buyer fraud rings
# ═══════════════════════════════════════════════════════════════════

def declare_buyer_fraud_ring(*, fraud_pattern: str,
                                 member_user_ids: list[int],
                                 total_loss_estimate: Decimal,
                                 currency: str = 'AOA',
                                 confidence: float = 0.0) -> BuyerFraudRing:
    sig = hashlib.sha256(
        ('|'.join(str(m) for m in sorted(member_user_ids))).encode()
    ).hexdigest()[:64]
    ring, created = BuyerFraudRing.objects.get_or_create(
        cluster_signature=sig,
        defaults={
            'fraud_pattern': fraud_pattern,
            'member_count': len(member_user_ids),
            'total_loss_estimate': total_loss_estimate,
            'currency': currency[:3],
            'confidence': confidence,
        },
    )
    if created:
        for uid in member_user_ids:
            BuyerFraudRingMember.objects.update_or_create(
                ring=ring, user_id=uid,
                defaults={'confidence': confidence},
            )
    return ring


# ═══════════════════════════════════════════════════════════════════
# CH19 — Product recall
# ═══════════════════════════════════════════════════════════════════

def initiate_recall(*, product_id: str, severity: str,
                       issue_description: str,
                       recall_source: str,
                       affected_listings: list = None,
                       affected_units_estimate: int = 0) -> ProductRecall:
    return ProductRecall.objects.create(
        recall_reference=f'REC-{timezone.now().strftime("%Y%m%d")}-' +
                            hashlib.sha256(product_id.encode()).hexdigest()[:6].upper(),
        product_id=product_id[:64],
        affected_listings=affected_listings or [],
        severity=severity, issue_description=issue_description,
        recall_source=recall_source,
        affected_units_estimate=affected_units_estimate,
    )


def notify_recall_recipient(recall: ProductRecall, *,
                                affected_user, order_id: str,
                                channel: str = 'email') -> RecallNotification:
    return RecallNotification.objects.create(
        recall=recall, affected_user=affected_user,
        order_id=order_id[:64], channel=channel[:12],
    )


# ═══════════════════════════════════════════════════════════════════
# CH20 — Export control
# ═══════════════════════════════════════════════════════════════════

# Toy sanctioned-country list. Production wires OFAC/EU/UN feeds.
_HARD_BLOCKED_DESTINATIONS = {'KP', 'IR', 'CU', 'SY'}
# Categories that need licence per country.
_LICENCE_REQUIRED = {
    ('encryption', 'RU'), ('encryption', 'CN'),
    ('dual_use', 'RU'),   ('drone', 'RU'),
}


def evaluate_export_control(*, listing_id: str,
                                destination_country: str,
                                category_keyword: str = '',
                                eccn: str = '') -> ExportControlListing:
    dest = (destination_country or '').upper()
    outcome = 'allowed'
    reason = ''
    if dest in _HARD_BLOCKED_DESTINATIONS:
        outcome = 'blocked'
        reason = f'Destination {dest} on sanctions list.'
    elif (category_keyword.lower(), dest) in _LICENCE_REQUIRED:
        outcome = 'licence_required'
        reason = f'Export licence required for {category_keyword} to {dest}.'
    obj, _ = ExportControlListing.objects.update_or_create(
        listing_id=listing_id[:64], destination_country=dest[:2],
        defaults={
            'eccn_classification': eccn[:20],
            'outcome': outcome, 'reason': reason[:255],
        },
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH21 — Buyer trust score
# ═══════════════════════════════════════════════════════════════════

def compute_buyer_trust_score(user) -> BuyerTrustScore:
    """Composite 0-100, in 6 components × ~17 points each, plus
    band. Best-effort pulls from existing apps."""
    # Purchase history component.
    purchase = 0.0
    try:
        from apps.orders.models import Order
        # NOTE: Order's buyer FK is named `buyer`, NOT `user`.
        n_completed = Order.objects.filter(
            buyer=user, status='completed',
        ).count()
        purchase = min(17.0, n_completed * 0.5)
    except Exception:
        purchase = 0.0
    # Payment method component.
    payment = 0.0
    try:
        from apps.payment_ops.models import TokenisedPaymentMethod
        n_methods = TokenisedPaymentMethod.objects.filter(
            user=user, is_active=True,
        ).count()
        payment = min(17.0, n_methods * 5.0)
    except Exception:
        payment = 0.0
    # Dispute history (inverted).
    disputes = 0.0
    try:
        from apps.disputes.models import Dispute
        n_disp = Dispute.objects.filter(buyer=user).count()
        disputes = max(0.0, 17.0 - n_disp * 3.0)
    except Exception:
        disputes = 17.0
    # Review quality.
    review = 14.0
    # Account age.
    if user.date_joined:
        days = (timezone.now() - user.date_joined).days
        account_age = min(17.0, days / 30.0)
    else:
        account_age = 0.0
    # Verification.
    verification = 8.0
    if hasattr(user, 'is_verified') and getattr(user, 'is_verified', False):
        verification = 17.0
    score = round(
        purchase + payment + disputes + review + account_age + verification
    )
    score = max(0, min(100, score))
    if   score >= 90: band = 'trusted_vip'
    elif score >= 75: band = 'trusted'
    elif score >= 50: band = 'neutral'
    elif score >= 25: band = 'cautious'
    else:             band = 'blocked'
    obj, _ = BuyerTrustScore.objects.update_or_create(
        user=user,
        defaults={
            'score': score,
            'purchase_history_component': purchase,
            'payment_method_component': payment,
            'dispute_history_component': disputes,
            'review_quality_component': review,
            'account_age_component': account_age,
            'verification_component': verification,
            'band': band,
        },
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH22 — Appeals
# ═══════════════════════════════════════════════════════════════════

def file_appeal(*, appellant, decision_kind: str,
                  original_decision_reference: str,
                  appeal_text: str,
                  supporting_evidence: list = None,
                  response_window_days: int = 7) -> AppealRequest:
    return AppealRequest.objects.create(
        appellant=appellant, decision_kind=decision_kind,
        original_decision_reference=original_decision_reference[:120],
        appeal_text=appeal_text[:10000],
        supporting_evidence=supporting_evidence or [],
        response_due_at=timezone.now() + timedelta(days=response_window_days),
    )


def decide_appeal(appeal: AppealRequest, *,
                    decision: str,
                    decision_reason: str,
                    reviewer) -> AppealRequest:
    AppealDecision.objects.create(
        appeal=appeal, decision=decision[:24],
        decision_reason=decision_reason[:10000],
        reviewer=reviewer,
    )
    appeal.status = decision
    appeal.resolved_at = timezone.now()
    appeal.save(update_fields=['status', 'resolved_at'])
    return appeal


# ═══════════════════════════════════════════════════════════════════
# CH23 — Law enforcement requests + legal hold
# ═══════════════════════════════════════════════════════════════════

def receive_le_request(*, agency: str, jurisdiction: str,
                          request_kind: str,
                          subject_user=None,
                          requested_data: list = None,
                          case_number: str = '',
                          deadline_days: int = 14,
                          legal_document_key: str = '',
                          user_notified: bool = True) -> LawEnforcementRequest:
    return LawEnforcementRequest.objects.create(
        case_number=case_number[:80], agency=agency[:120],
        jurisdiction=jurisdiction[:2],
        request_kind=request_kind,
        subject_user=subject_user,
        requested_data=requested_data or [],
        deadline_at=timezone.now() + timedelta(days=deadline_days),
        legal_document_key=legal_document_key[:255],
        user_notified=user_notified,
    )


def respond_to_le_request(req: LawEnforcementRequest, *,
                              status: str,
                              response_notes: str = '',
                              handled_by=None) -> LawEnforcementRequest:
    req.status = status
    req.response_notes = response_notes[:10000]
    req.handled_by = handled_by
    req.responded_at = timezone.now()
    req.save(update_fields=['status', 'response_notes',
                              'handled_by', 'responded_at'])
    return req


def start_legal_hold(*, subject_user, description: str,
                       scope: list = None,
                       related_request: LawEnforcementRequest = None) -> LegalHold:
    return LegalHold.objects.create(
        subject_user=subject_user, description=description[:10000],
        scope=scope or [], related_request=related_request,
    )


def release_legal_hold(hold: LegalHold) -> LegalHold:
    hold.released_at = timezone.now()
    hold.save(update_fields=['released_at'])
    return hold


# ═══════════════════════════════════════════════════════════════════
# CH24 — KPI snapshot
# ═══════════════════════════════════════════════════════════════════

def snapshot_ts_kpis(snapshot_date=None) -> TrustSafetyKpiSnapshot:
    if snapshot_date is None:
        snapshot_date = timezone.now().date()
    start = timezone.make_aware(
        timezone.datetime.combine(snapshot_date, timezone.datetime.min.time())
    )
    end = start + timedelta(days=1)

    prohibited = ProhibitedItemDetection.objects.filter(
        detected_at__gte=start, detected_at__lt=end,
    ).count()
    cf_open = CounterfeitCase.objects.filter(
        created_at__gte=start, created_at__lt=end,
    ).count()
    cf_removed = CounterfeitCase.objects.filter(
        status='listing_removed', decided_at__gte=start, decided_at__lt=end,
    ).count()
    csam = CsamIncident.objects.filter(
        detected_at__gte=start, detected_at__lt=end,
    ).count()
    hate = HateSpeechEnforcement.objects.filter(
        enforced_at__gte=start, enforced_at__lt=end,
    ).count()
    ip_filed = IpComplaint.objects.filter(
        filed_at__gte=start, filed_at__lt=end,
    ).count()
    dmca = DmcaNotice.objects.filter(
        filed_at__gte=start, filed_at__lt=end,
    ).count()
    gouging = PriceGougingFlag.objects.filter(
        detected_at__gte=start, detected_at__lt=end,
    ).count()
    bl_hits = BlacklistCheck.objects.filter(
        checked_at__gte=start, checked_at__lt=end, outcome='blocked',
    ).count()
    review_rings = ReviewFraudRing.objects.filter(
        detected_at__gte=start, detected_at__lt=end,
    ).count()
    ato = AccountTakeoverCase.objects.filter(
        detected_at__gte=start, detected_at__lt=end,
    ).count()
    edd_pending = EnhancedDueDiligenceReview.objects.filter(
        status__in=('pending', 'docs_received'),
    ).count()
    serial = SerialDisputerSignal.objects.filter(
        detected_at__gte=start, detected_at__lt=end,
    ).count()
    bfr = BuyerFraudRing.objects.filter(
        detected_at__gte=start, detected_at__lt=end,
    ).count()
    recalls = ProductRecall.objects.exclude(status='completed').count()
    appeals_open = AppealRequest.objects.filter(
        status__in=('submitted', 'under_review'),
    ).count()
    le_received = LawEnforcementRequest.objects.filter(
        received_at__gte=start, received_at__lt=end,
    ).count()
    le_overdue = LawEnforcementRequest.objects.filter(
        deadline_at__lt=timezone.now(),
        status__in=('received', 'validating', 'responding'),
    ).count()

    # Auto-action rate.
    decisions = TsDecision.objects.filter(
        decided_at__gte=start, decided_at__lt=end,
    )
    n_dec = decisions.count() or 1
    auto = decisions.filter(
        outcome__in=('auto_remove', 'auto_warn', 'auto_ban'),
    ).count()
    auto_rate = (auto / n_dec) * 100

    by_category = dict(
        ProhibitedItemDetection.objects.filter(
            detected_at__gte=start, detected_at__lt=end,
        ).values_list('rule__category').annotate(
            c=django_models.Count('id'),
        )
    )
    by_surface = dict(
        TsDecision.objects.filter(
            decided_at__gte=start, decided_at__lt=end,
        ).values_list('surface').annotate(
            c=django_models.Count('id'),
        )
    )

    obj, _ = TrustSafetyKpiSnapshot.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'prohibited_detections': prohibited,
            'counterfeit_cases_opened': cf_open,
            'counterfeit_listings_removed': cf_removed,
            'csam_incidents': csam,
            'hate_speech_actions': hate,
            'ip_complaints_filed': ip_filed,
            'dmca_notices_filed': dmca,
            'price_gouging_flags': gouging,
            'blacklist_hits': bl_hits,
            'review_fraud_rings': review_rings,
            'ato_cases': ato,
            'edd_reviews_pending': edd_pending,
            'serial_disputers_flagged': serial,
            'buyer_fraud_rings': bfr,
            'recalls_active': recalls,
            'appeals_open': appeals_open,
            'le_requests_received': le_received,
            'le_requests_overdue': le_overdue,
            'auto_action_rate': auto_rate,
            'by_category': {k or '': v for k, v in by_category.items()},
            'by_surface': {k or '': v for k, v in by_surface.items()},
        },
    )
    return obj
