"""
Seller onboarding — domain services
====================================

This is the pure-business-logic layer. Views call into it; Celery
tasks call into it; signal handlers call into it. The doc's
pseudo-code (qualify_lead, check_eligibility, compute_seller_tier,
compute_health_score, apply_welcome_package, etc.) maps 1:1 to a
function here.

Everything is idempotent where it makes sense — calling
`activate_seller(app)` twice doesn't double-issue fee invoices
because we look up existing rows before inserting.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .models import (
    AGREEMENT_STATUS_CHOICES, AgreementTemplate,
    APPLICATION_STATUS_CHOICES, APPLICATION_TRANSITIONS,
    KycDocument, SellerAdCredit, SellerAgreement, SellerApplication,
    SellerBrand, SellerCategoryEnrolment, SellerCertificate,
    SellerCommissionOverride, SellerFeeInvoice, SellerHealthScore,
    SellerHolidayLog, SellerLead, SellerOnboardingEvent,
    SellerTierHistory, SellerTierState, SellerTrainingProgress,
    SellerVisibilityBoost, TIER_ORDER,
)

User = get_user_model()
log = logging.getLogger(__name__)


# ── CH1.3 — Lead qualification ────────────────────────────────────

# Per-doc country tiers, tuned for MICHA's Angola-first market. CN
# stays in T1 (manufacturer-sourced sellers), Angola sits in T1 as
# our home market.
TIER_1_MARKETS = {'AO', 'CN', 'ES', 'FR', 'DE', 'IT', 'TR', 'BR', 'KR', 'PL', 'PT', 'US'}
TIER_2_MARKETS = {
    'GB', 'NL', 'BE', 'SE', 'NO', 'DK', 'FI', 'CH', 'AT', 'CZ',
    'MX', 'ZA', 'NG', 'MA', 'EG', 'AE', 'SA', 'IN', 'TH', 'VN',
    'ID', 'MY', 'PH', 'SG', 'JP', 'IL', 'GR', 'IE', 'RO', 'HU',
}


def qualify_lead(lead: SellerLead) -> dict:
    """CH1.3 — score a lead 0–100 + decide eligibility.

    The doc's algorithm verbatim, with one MICHA tweak: unknown
    countries return `eligible=False` instead of just `score=0`, so
    the form can show a "we don't serve your market yet" message
    rather than dropping the lead silently into the BD review queue.
    """
    score = 0
    breakdown = {}

    country = (lead.country or '').upper()
    if country in TIER_1_MARKETS:
        score += 30; breakdown['country'] = 30
    elif country in TIER_2_MARKETS:
        score += 15; breakdown['country'] = 15
    else:
        return {
            'eligible': False, 'score': 0,
            'reason': 'COUNTRY_NOT_SUPPORTED',
            'breakdown': {'country': 0},
        }

    n = lead.estimated_sku_count or 0
    if n >= 500:   pts = 20
    elif n >= 100: pts = 12
    elif n >= 20:  pts = 6
    else:          pts = 0
    score += pts; breakdown['sku_depth'] = pts

    rev = (lead.annual_revenue_bracket or '').lower()
    if rev == '>5m':            pts = 20
    elif '500k+' in rev:        pts = 14
    elif '50k-500k' in rev:     pts = 8
    else:                       pts = 0
    score += pts; breakdown['revenue'] = pts

    # Category-fit lookup is a stub — production wires this against
    # a `category_demand_gaps` reference table. Default to a neutral
    # 10/20 so leads aren't penalised by missing data.
    cat_pts = 10
    score += cat_pts; breakdown['category_fit'] = cat_pts

    if lead.has_brand:
        score += 10; breakdown['has_brand'] = 10

    return {
        'eligible': score >= 40,
        'score': score,
        'breakdown': breakdown,
        'reason': 'OK' if score >= 40 else 'SCORE_BELOW_THRESHOLD',
    }


def submit_lead(*, lead: SellerLead) -> dict:
    """Persist the qualification result on the lead and route to the
    next status. Below 40 → rejected (the doc's auto-reject band).
    40–69 → qualified (needs BD review).  70+ → fast-track 'qualified'
    too, but the application form will fast-lane downstream."""
    result = qualify_lead(lead)
    lead.qualification_score = result['score']
    lead.qualification_breakdown = result['breakdown']
    if not result['eligible']:
        lead.status = 'rejected'
    else:
        lead.status = 'qualified'
    lead.save(update_fields=['qualification_score', 'qualification_breakdown', 'status'])
    SellerOnboardingEvent.log(
        kind='lead.qualified', payload={
            'lead_id': str(lead.id), 'score': result['score'],
            'eligible': result['eligible'], 'reason': result['reason'],
        })
    return result


# ── CH2.3 — Eligibility gate on application submit ────────────────

SUPPORTED_COUNTRIES = TIER_1_MARKETS | TIER_2_MARKETS


def check_eligibility(app: SellerApplication) -> dict:
    """Run all five gates from CH2.3.  Returns
    {eligible: bool, code: str, detail: dict}.  Persists the result
    on the application so the reviewer can see why a gate failed
    without re-running the checks."""
    detail = {}

    if (app.country or '').upper() not in SUPPORTED_COUNTRIES:
        return _fail(app, 'COUNTRY_NOT_SUPPORTED', detail)

    # Gate 2 — duplicate application by email or registration number.
    dup_qs = SellerApplication.objects.filter(applicant_email__iexact=app.applicant_email).exclude(pk=app.pk)
    if app.business_reg_number:
        dup_qs = dup_qs | SellerApplication.objects.filter(
            business_reg_number=app.business_reg_number,
        ).exclude(pk=app.pk)
    if dup_qs.filter(status__in=('approved', 'submitted', 'kyc_review',
                                  'kyc_approved', 'agreement_sent',
                                  'agreement_signed', 'fee_pending',
                                  'fee_paid')).exists():
        return _fail(app, 'DUPLICATE_APPLICATION', detail)

    # Gate 3 — 90-day cooldown after rejection.
    rejected_recent = SellerApplication.objects.filter(
        applicant_email__iexact=app.applicant_email,
        status='rejected',
        reviewed_at__gte=timezone.now() - timedelta(days=90),
    ).first()
    if rejected_recent:
        eligible_after = rejected_recent.reviewed_at + timedelta(days=90)
        detail['eligible_after'] = eligible_after.isoformat()
        return _fail(app, 'REAPPLICATION_TOO_SOON', detail)

    # Gate 4 + Gate 5 are stubbed — they require a categories table
    # with status + required_docs and a sanctions API integration.
    # We mark them passed but log it so audit knows we skipped.
    SellerOnboardingEvent.log(
        application=app, kind='eligibility.gate_stubbed',
        payload={'gates_skipped': ['category_status', 'sanctions']},
    )

    app.eligibility_passed = True
    app.eligibility_failure_code = ''
    app.save(update_fields=['eligibility_passed', 'eligibility_failure_code'])
    SellerOnboardingEvent.log(
        application=app, kind='eligibility.passed', payload=detail,
    )
    return {'eligible': True, 'code': 'OK', 'detail': detail}


def _fail(app, code, detail):
    app.eligibility_passed = False
    app.eligibility_failure_code = code
    app.save(update_fields=['eligibility_passed', 'eligibility_failure_code'])
    SellerOnboardingEvent.log(
        application=app, kind='eligibility.failed',
        payload={'code': code, **detail},
    )
    return {'eligible': False, 'code': code, 'detail': detail}


# ── CH3 — KYC routing ─────────────────────────────────────────────

def evaluate_kyc(app: SellerApplication) -> dict:
    """Decide if the uploaded document set is auto-approvable. Runs
    the conditions from CH3.2 step 5. If auto-approve criteria are
    not met, the application stays in kyc_review for a human."""
    docs = list(app.kyc_documents.all())
    required = {'business_licence', 'rep_id_front', 'bank_statement'}
    present = {d.document_type for d in docs}
    if not required.issubset(present):
        return {'auto_approve': False, 'reason': 'MISSING_REQUIRED_DOCS',
                'missing': list(required - present)}

    avg_conf = (sum((d.ocr_confidence or 0.0) for d in docs) / len(docs)) if docs else 0
    discrepancies = sum(len(d.discrepancies or []) for d in docs)
    selfie = next((d for d in docs if d.document_type == 'rep_selfie'), None)
    face_match = selfie.face_match_score if selfie else 1.0

    auto = (
        avg_conf > 0.92 and discrepancies == 0 and face_match > 0.92
    )
    return {
        'auto_approve': auto, 'avg_confidence': avg_conf,
        'discrepancies_total': discrepancies, 'face_match': face_match,
    }


# ── CH4 — Agreement generation + signing ──────────────────────────

def generate_agreement_for(app: SellerApplication) -> SellerAgreement:
    """Personalise the current AgreementTemplate for the application.
    Idempotent — if a pending-signature agreement already exists, we
    return it instead of generating a duplicate."""
    existing = app.agreements.filter(
        status='pending_signature', expires_at__gt=timezone.now(),
    ).first()
    if existing:
        return existing

    template = (
        AgreementTemplate.objects.order_by('-effective_date').first()
    )
    if template is None:
        # Bootstrap default template so dev environments don't crash.
        template = AgreementTemplate.objects.create(
            version='1.0.0', country_scope=['*'], category_scope=['*'],
            change_summary='Initial template',
            body=DEFAULT_AGREEMENT_BODY,
            effective_date=timezone.now().date(),
        )

    body = template.body \
        .replace('{{COMPANY_NAME}}', app.company_name) \
        .replace('{{REGISTRATION_NUMBER}}', app.business_reg_number or '') \
        .replace('{{REPRESENTATIVE_NAME}}', app.legal_representative_name or '') \
        .replace('{{COUNTRY}}', app.country) \
        .replace('{{EFFECTIVE_DATE}}', timezone.now().date().isoformat()) \
        .replace('{{AGREEMENT_ID}}', '')

    ag = SellerAgreement.objects.create(
        application=app, template=template, body_personalised=body,
        signing_token=SellerAgreement.generate_token(),
        expires_at=timezone.now() + timedelta(days=30),
    )
    SellerOnboardingEvent.log(
        application=app, kind='agreement.generated',
        payload={'agreement_id': str(ag.id),
                 'template_version': template.version,
                 'expires_at': ag.expires_at.isoformat()},
    )
    # Advance the FSM: kyc_approved → agreement_sent. The next move
    # (→ agreement_signed) happens inside sign_agreement().
    if app.status == 'kyc_approved':
        try: app.apply_transition('agreement_sent', notes='auto after generation')
        except Exception: pass
    return ag


def sign_agreement(*, agreement: SellerAgreement, signature_name: str,
                   ip: str, ua: str, scroll_pct: int,
                   checkbox_confirmed: bool) -> dict:
    """CH4.2 validation + commit. Raises ValueError on each failure
    so the view can map to a 422 response with the exact code."""
    if not checkbox_confirmed:
        raise ValueError('CHECKBOX_NOT_CONFIRMED')
    if (scroll_pct or 0) < 100:
        raise ValueError('AGREEMENT_NOT_FULLY_READ')
    expected = (agreement.application.legal_representative_name or '').strip().lower()
    if expected and signature_name.strip().lower() != expected:
        raise ValueError('SIGNATURE_NAME_MISMATCH')
    if agreement.expires_at < timezone.now():
        raise ValueError('AGREEMENT_EXPIRED')
    if agreement.status != 'pending_signature':
        raise ValueError('AGREEMENT_ALREADY_DECIDED')

    agreement.signed_at = timezone.now()
    agreement.signer_ip = ip or None
    agreement.signer_ua = (ua or '')[:255]
    agreement.signature_name = signature_name
    agreement.scroll_completion_pct = min(int(scroll_pct), 100)
    agreement.signature_hash = agreement.compute_signature_hash()
    agreement.status = 'signed'
    agreement.save(update_fields=[
        'signed_at', 'signer_ip', 'signer_ua', 'signature_name',
        'scroll_completion_pct', 'signature_hash', 'status',
    ])
    SellerOnboardingEvent.log(
        application=agreement.application, kind='agreement.signed',
        payload={'agreement_id': str(agreement.id),
                 'signer_ip': str(ip or ''),
                 'signature_hash': agreement.signature_hash[:16]},
    )
    # Advance the application FSM.
    agreement.application.apply_transition(
        'agreement_signed', actor=None,
        notes=f'agreement {agreement.id} signed',
    )
    return {'agreement_id': str(agreement.id),
            'signature_hash': agreement.signature_hash}


# ── CH5.2 — Fee invoice ──────────────────────────────────────────

# AOA added for the MICHA-Angola market. USD/EUR retained for parity
# with the AliExpress doc so reports compare cleanly.
ANNUAL_FEE_MATRIX = {
    'AO': {'base': '50000.00', 'currency': 'AOA'},
    'CN': {'base':  '1500.00', 'currency': 'USD'},
    'ES': {'base':  '1200.00', 'currency': 'EUR'},
    'US': {'base':     '0.00', 'currency': 'USD'},
    'BR': {'base':  '1500.00', 'currency': 'USD'},
    'TR': {'base':   '800.00', 'currency': 'USD'},
}
DEFAULT_FEE = {'base': '1000.00', 'currency': 'USD'}


def issue_annual_fee_invoice(app: SellerApplication) -> SellerFeeInvoice:
    """Compute the final fee per CH5.2's discount stack, persist the
    invoice, and advance the FSM to fee_pending. Idempotent — if a
    pending invoice already exists we return it."""
    existing = app.fee_invoices.filter(status='pending').first()
    if existing:
        return existing

    entry = ANNUAL_FEE_MATRIX.get((app.country or '').upper(), DEFAULT_FEE)
    base = Decimal(entry['base'])
    discounts = []

    # First-year discount in CH5.2's list of qualifying markets.
    if (app.country or '').upper() in ('US', 'GB', 'DE', 'FR', 'ES', 'AO'):
        discounts.append({'code': 'first_year', 'pct': 50})

    # BD-strategic waiver if the lead source is outbound.
    if app.lead and app.lead.lead_source == 'outbound_bd' \
       and app.lead.qualification_score >= 80:
        discounts.append({'code': 'bd_strategic', 'pct': 100})

    final = base
    for d in discounts:
        final = (final * (Decimal(100) - Decimal(d['pct'])) / Decimal(100))
    final = final.quantize(Decimal('0.01'))

    inv = SellerFeeInvoice.objects.create(
        application=app, base_amount=base, discounts=discounts,
        final_amount=final, currency=entry['currency'],
        due_at=timezone.now() + timedelta(days=30),
    )
    SellerOnboardingEvent.log(
        application=app, kind='fee_invoice.issued',
        payload={'invoice_id': str(inv.id), 'amount': str(final),
                 'currency': inv.currency, 'discounts': discounts},
    )
    try:
        app.apply_transition('fee_pending', notes='auto on agreement signed')
    except Exception:
        pass
    return inv


# ── CH5.3 — Seller activation ────────────────────────────────────

@transaction.atomic
def activate_seller(app: SellerApplication) -> dict:
    """The big commit. Creates the User (if not already linked),
    transitions the application to approved, applies the welcome
    package, and writes a tier_state row at 'standard'."""
    user = app.applicant
    if user is None:
        # Bootstrap a User account for the seller.  If a user with the
        # contact email already exists (e.g. they registered first),
        # reuse it instead of failing.
        user, _ = User.objects.get_or_create(
            email=app.applicant_email,
            defaults={'username': app.applicant_email.split('@')[0][:30],
                      'is_seller': True, 'is_active': True},
        )
        # Be defensive: not every User model has is_seller, so set
        # only fields we know about.
        if hasattr(user, 'is_seller') and not user.is_seller:
            user.is_seller = True
            user.save(update_fields=['is_seller'])

    app.seller = user
    app.applicant = user
    if app.status != 'approved':
        try:
            app.apply_transition('approved', notes='auto on fee_paid')
        except Exception:
            app.status = 'approved'
            app.approved_at = timezone.now()
            app.save(update_fields=['status', 'approved_at'])
    app.save(update_fields=['seller', 'applicant'])

    # Default tier row.
    SellerTierState.objects.get_or_create(
        seller=user, defaults={'current_tier': 'standard'},
    )

    apply_welcome_package(user, country=app.country)

    SellerOnboardingEvent.log(
        application=app, seller=user, kind='seller.activated',
        payload={'user_id': user.pk, 'country': app.country},
    )
    return {'seller_id': user.pk, 'application_id': str(app.id)}


# ── CH9.1 — Welcome package ──────────────────────────────────────

def apply_welcome_package(user, *, country: str) -> None:
    """Apply visibility boost + ad credits + commission override (per
    eligible markets). Idempotent — checks for existing rows before
    inserting."""
    now = timezone.now()
    country = (country or '').upper()

    # 90-day visibility boost.
    if not SellerVisibilityBoost.objects.filter(
        seller=user, boost_type='new_seller_spotlight',
        valid_until__gt=now,
    ).exists():
        SellerVisibilityBoost.objects.create(
            seller=user, boost_type='new_seller_spotlight',
            boost_multiplier=1.3, valid_from=now,
            valid_until=now + timedelta(days=90),
        )

    # Ad credit pool ($50 / 60 days; AOA equivalent for Angola).
    currency = 'AOA' if country == 'AO' else 'USD'
    amount = Decimal('25000.00') if currency == 'AOA' else Decimal('50.00')
    if not SellerAdCredit.objects.filter(
        seller=user, credit_type='new_seller_welcome',
        valid_until__gt=now,
    ).exists():
        SellerAdCredit.objects.create(
            seller=user, amount=amount, currency=currency,
            credit_type='new_seller_welcome',
            valid_until=now + timedelta(days=60),
        )

    # 50% commission reduction for first 30 days in eligible markets.
    if country in ('US', 'GB', 'DE', 'FR', 'ES', 'AO') and \
       not SellerCommissionOverride.objects.filter(
        seller=user, reason='new_seller_welcome', valid_until__gt=now,
    ).exists():
        SellerCommissionOverride.objects.create(
            seller=user, rate=Decimal('0.0250'),  # 2.5% — half of 5%
            reason='new_seller_welcome',
            valid_until=now + timedelta(days=30),
        )


# ── CH14 — Tier score + recalculation ────────────────────────────

def compute_seller_tier_score(user) -> dict:
    """Pure function. Returns {tier, score, metrics_snapshot}.  The
    metrics come from get_seller_metrics() which is intentionally
    pluggable — production hooks it into the analytics warehouse.
    Today it pulls from the orders / reviews / disputes tables that
    already live in MICHA."""
    metrics = get_seller_metrics(user)
    score = 0

    # Order volume.
    n = metrics['order_count']
    if   n >= 5000: score += 20
    elif n >= 2000: score += 16
    elif n >=  500: score += 12
    elif n >=  200: score +=  8
    elif n >=   50: score +=  4

    # GMV.
    g = float(metrics['gmv_usd'])
    if   g >= 500000: score += 20
    elif g >= 100000: score += 16
    elif g >=  20000: score += 12
    elif g >=   5000: score +=  8
    elif g >=   1000: score +=  4

    f = metrics['feedback_score']
    if   f >= 0.99: score += 20
    elif f >= 0.98: score += 16
    elif f >= 0.97: score += 12
    elif f >= 0.93: score +=  8
    elif f >= 0.90: score +=  4

    d = metrics['dispute_rate']
    if   d <= 0.003: score += 20
    elif d <= 0.005: score += 16
    elif d <= 0.01:  score += 12
    elif d <= 0.03:  score +=  8
    elif d <= 0.05:  score +=  4

    s = metrics['on_time_shipping_rate']
    if   s >= 0.99: score += 20
    elif s >= 0.97: score += 16
    elif s >= 0.95: score += 12
    elif s >= 0.90: score +=  8
    elif s >= 0.85: score +=  4

    if   score >= 90 and g >= 500000: tier = 'diamond'
    elif score >= 75 and g >= 100000: tier = 'platinum'
    elif score >= 55 and g >=  20000: tier = 'gold'
    elif score >= 35 and g >=   5000: tier = 'silver'
    elif score >= 20 and g >=   1000: tier = 'bronze'
    else: tier = 'standard'

    # Hard cap: high disputes can't be gold+.
    if d > 0.05 and TIER_ORDER.index(tier) > TIER_ORDER.index('silver'):
        tier = 'silver'

    return {'tier': tier, 'score': score, 'metrics_snapshot': metrics}


def get_seller_metrics(user) -> dict:
    """Pull 90-day metrics for tier scoring. Best-effort across the
    existing apps — if a model isn't installed we return safe zeros.
    """
    from django.db.models import Avg, Count, Q
    now = timezone.now()
    window_start = now - timedelta(days=90)
    order_count = 0; gmv = 0.0; feedback = 1.0; dispute_rate = 0.0
    on_time = 1.0
    try:
        from apps.orders.models import Order
        qs = Order.objects.filter(
            items__product__store__owner=user,
            created_at__gte=window_start,
        ).distinct()
        order_count = qs.count()
        gmv = float(qs.aggregate(s=models.Sum('total_amount'))['s'] or 0)
    except Exception:
        pass
    try:
        from apps.reviews.models import Review
        rvs = Review.objects.filter(
            product__store__owner=user, created_at__gte=window_start,
        )
        total = rvs.count()
        good = rvs.filter(rating__gte=4).count()
        if total:
            feedback = good / total
    except Exception:
        pass
    try:
        from apps.disputes.models import Dispute
        disputes = Dispute.objects.filter(
            order__items__product__store__owner=user,
            created_at__gte=window_start,
        ).count()
        if order_count:
            dispute_rate = disputes / order_count
    except Exception:
        pass
    # on_time_shipping_rate left at 1.0 until the shipping app exposes
    # the deadline-vs-actual comparison; this is intentionally permissive.
    return {
        'order_count': order_count,
        'gmv_usd': round(gmv, 2),
        'feedback_score': round(feedback, 4),
        'dispute_rate': round(dispute_rate, 4),
        'on_time_shipping_rate': on_time,
    }


def recalculate_tier(user, *, write_history=True) -> dict:
    """Apply CH15.1 logic: compute, compare to current, emit
    upgrade/downgrade-warning, persist history."""
    result = compute_seller_tier_score(user)
    state, _ = SellerTierState.objects.get_or_create(seller=user)
    old_tier = state.current_tier
    new_tier = result['tier']

    state.last_score = result['score']
    state.last_metrics = result['metrics_snapshot']

    if new_tier == old_tier:
        state.save(update_fields=['last_score', 'last_metrics', 'tier_updated_at'])
        return {'changed': False, **result}

    old_idx = TIER_ORDER.index(old_tier)
    new_idx = TIER_ORDER.index(new_tier)

    if new_idx > old_idx:
        # Upgrade — apply immediately.
        state.current_tier = new_tier
        state.pending_tier = ''
        state.downgrade_warning_sent_at = None
        state.save()
        if write_history:
            SellerTierHistory.objects.create(
                seller=user, old_tier=old_tier, new_tier=new_tier,
                computed_score=result['score'],
                metrics_snapshot=result['metrics_snapshot'],
            )
        SellerOnboardingEvent.log(
            seller=user, kind='tier.upgraded',
            payload={'from': old_tier, 'to': new_tier,
                     'score': result['score']},
        )
        return {'changed': True, 'direction': 'up', **result}

    # Downgrade — 30-day grace.
    if state.downgrade_warning_sent_at is None:
        state.pending_tier = new_tier
        state.downgrade_warning_sent_at = timezone.now()
        state.save()
        SellerOnboardingEvent.log(
            seller=user, kind='tier.downgrade_warning',
            payload={'current': old_tier, 'pending': new_tier,
                     'score': result['score']},
        )
        return {'changed': False, 'direction': 'warning', **result}
    if state.downgrade_warning_sent_at < timezone.now() - timedelta(days=30):
        state.current_tier = new_tier
        state.pending_tier = ''
        state.downgrade_warning_sent_at = None
        state.save()
        if write_history:
            SellerTierHistory.objects.create(
                seller=user, old_tier=old_tier, new_tier=new_tier,
                computed_score=result['score'],
                metrics_snapshot=result['metrics_snapshot'],
            )
        SellerOnboardingEvent.log(
            seller=user, kind='tier.downgraded',
            payload={'from': old_tier, 'to': new_tier,
                     'score': result['score']},
        )
        return {'changed': True, 'direction': 'down', **result}
    return {'changed': False, 'direction': 'warning_pending', **result}


# ── CH16 — Health score ──────────────────────────────────────────

def compute_health_score(user) -> dict:
    """Composite 0-100 score per CH16.1 weights. Same metric sources
    as tier; weights different."""
    m = get_seller_metrics(user)
    feedback = m['feedback_score'] * 100
    dispute  = max(0, 100 - (m['dispute_rate'] * 1000))    # 10% dispute = 0
    shipping = m['on_time_shipping_rate'] * 100
    response = 80.0  # placeholder until messaging response tracker lands
    listing  = 70.0  # placeholder
    returns  = 95.0  # placeholder

    score = round(
        feedback * 0.25 + dispute * 0.25 + shipping * 0.20 +
        response * 0.10 + listing * 0.10 + returns * 0.10
    )
    score = max(0, min(100, score))

    if   score >= 80: band = 'excellent'
    elif score >= 60: band = 'good'
    elif score >= 40: band = 'at_risk'
    elif score >= 20: band = 'poor'
    else:             band = 'critical'

    return {
        'score': score, 'band': band,
        'components': {
            'feedback': feedback, 'dispute': dispute,
            'shipping': shipping, 'response': response,
            'listing_quality': listing, 'returns': returns,
        },
    }


def snapshot_health_score(user) -> SellerHealthScore:
    """Write today's row (idempotent on (seller, snapshot_date))."""
    r = compute_health_score(user)
    today = timezone.now().date()
    obj, _ = SellerHealthScore.objects.update_or_create(
        seller=user, snapshot_date=today,
        defaults={
            'score': r['score'],
            'feedback_component': r['components']['feedback'],
            'dispute_component': r['components']['dispute'],
            'shipping_component': r['components']['shipping'],
            'response_component': r['components']['response'],
            'listing_quality_component': r['components']['listing_quality'],
            'returns_component': r['components']['returns'],
            'intervention_band': r['band'],
        },
    )
    return obj


# ── CH10.2 — Category enrolment ──────────────────────────────────

def enrol_category(*, seller, category_id: str, enrolment_type: str,
                   documents=None) -> dict:
    """Open → instant approval. L1/L2 → pending review.  L3 → pending
    + BD assignment.  Prohibited → blocked + security event."""
    if enrolment_type == 'prohibited':
        SellerOnboardingEvent.log(
            seller=seller, kind='category.prohibited_attempt',
            payload={'category_id': category_id},
        )
        return {'ok': False, 'code': 'CATEGORY_PROHIBITED'}

    status = 'approved' if enrolment_type == 'open' else 'pending'
    approved_at = timezone.now() if status == 'approved' else None
    obj, created = SellerCategoryEnrolment.objects.update_or_create(
        seller=seller, category_id=category_id,
        defaults={
            'enrolment_type': enrolment_type, 'status': status,
            'documents_submitted': documents or [],
            'approved_at': approved_at,
        },
    )
    SellerOnboardingEvent.log(
        seller=seller, kind='category.enrolment_requested',
        payload={'category_id': category_id, 'type': enrolment_type,
                 'status': status},
    )
    return {'ok': True, 'status': status, 'enrolment_id': obj.pk}


# ── CH18 — Holiday quota check ───────────────────────────────────

def can_activate_holiday(seller, *, start_date, end_date) -> dict:
    if (end_date - start_date).days > 30:
        return {'ok': False, 'code': 'MAX_30_DAYS_PER_ACTIVATION'}
    year_start = start_date.replace(month=1, day=1)
    activations_this_year = SellerHolidayLog.objects.filter(
        seller=seller, activated_at__gte=year_start,
    ).count()
    if activations_this_year >= 3:
        return {'ok': False, 'code': 'MAX_3_ACTIVATIONS_PER_YEAR'}
    return {'ok': True}


# ── Bootstrap copy ───────────────────────────────────────────────

DEFAULT_AGREEMENT_BODY = """
MICHA Marketplace Seller Agreement
===================================

This Agreement is between Casa Cabaça Tech, Lda ("MICHA") and
{{COMPANY_NAME}} ("Seller"), registered in {{COUNTRY}} under
registration number {{REGISTRATION_NUMBER}}. Authorised
representative: {{REPRESENTATIVE_NAME}}.

By signing this agreement on {{EFFECTIVE_DATE}}, Seller accepts:
1. Platform rules and policies as published at micha.ao/legal.
2. Commission and fee structure applicable to its country and
   category.
3. Buyer-protection obligations (shipping deadlines, dispute
   response within 5 business days, return acceptance per
   policy).
4. Data processing terms — GDPR/PIPL compliance clauses for
   cross-border transfer of personal data, where applicable.
5. Governing law: Republic of Angola, with international
   commercial arbitration in line with the New York Convention
   for cross-border disputes.

This is a binding contract. Digital signature via this flow has
the same legal effect as a wet-ink signature under Angolan law
and the relevant international electronic-signature frameworks
(eIDAS, ESIGN Act).
"""[1:]


# Late import to avoid circular at import time.
from django.db import models  # noqa: E402


# ═══════════════════════════════════════════════════════════════════
# CH6 — Email drip & suppression
# ═══════════════════════════════════════════════════════════════════

# Drip steps: (sequence_key, days_after_activation, suppression check)
# Each suppression check is a callable(seller) → reason str or None.
# If reason: skip and log SUPPRESSED.
DRIP_SEQUENCE = [
    ('day0_welcome',            0,  None),
    ('day1_no_login',           1,  'no_login'),
    ('day2_setup_3_things',     2,  'no_login'),
    ('day3_profile_incomplete', 3,  'profile_complete'),
    ('day4_first_listing',      4,  'has_first_product'),
    ('day5_no_listing',         5,  'has_first_product'),
    ('day7_optimise_listing',   7,  'no_listings'),
    ('day10_no_orders',        10,  'has_first_order'),
    ('day14_training',         14,  'training_started'),
    ('day21_first_order',      21,  'no_first_order'),
    ('day30_checkin',          30,  None),
    ('day45_no_shipping',      45,  'has_shipping_template'),
    ('day60_tier',             60,  None),
    ('day90_benchmark',        90,  None),
]

DRIP_SUBJECTS = {
    'day0_welcome':           '🎉 Welcome to MICHA! Your store is live.',
    'day1_no_login':          'Your store is waiting — here\'s how to get started',
    'day2_setup_3_things':    '3 things to do before your first sale',
    'day3_profile_incomplete':'Your store profile affects your ranking — complete it now',
    'day4_first_listing':     'Ready to list? Your first product guide',
    'day5_no_listing':        'Sellers who list within 5 days get 3× more visibility',
    'day7_optimise_listing':  'Your listing is live — here\'s how to optimise it',
    'day10_no_orders':        'How top new sellers get their first order in 10 days',
    'day14_training':         'Sellers with MICHA certification earn 28% more',
    'day21_first_order':      '🎉 Your first sale! Here\'s what to do next',
    'day30_checkin':          'Your first month on MICHA — your performance report',
    'day45_no_shipping':      'Buyers can\'t see your shipping options — fix this now',
    'day60_tier':             'You\'re 60 days in — your path to Gold tier',
    'day90_benchmark':        'How does your store compare to top sellers in your category?',
}


def _check_suppression(seller, key: str):
    """Return a suppression reason string or None. Each suppression
    rule is one cheap query."""
    if key is None:
        return None
    if key == 'no_login':
        last_login = getattr(seller, 'last_login', None)
        return None if last_login else 'never_logged_in'
    if key == 'profile_complete':
        try:
            from apps.seller.models import SellerOnboardingChecklist
            cl = SellerOnboardingChecklist.objects.filter(seller=seller).first()
            return 'profile_already_complete' if (cl and cl.profile_completed) else None
        except Exception:
            return None
    if key == 'has_first_product':
        try:
            from apps.products.models import Product
            if Product.objects.filter(store__owner=seller).exists():
                return 'already_listed'
        except Exception:
            pass
        return None
    if key == 'no_listings':
        try:
            from apps.products.models import Product
            if not Product.objects.filter(store__owner=seller).exists():
                return 'no_listings_yet'
        except Exception:
            pass
        return None
    if key == 'has_first_order':
        try:
            from apps.orders.models import Order
            if Order.objects.filter(items__product__store__owner=seller).exists():
                return 'already_has_orders'
        except Exception:
            pass
        return None
    if key == 'no_first_order':
        try:
            from apps.orders.models import Order
            if not Order.objects.filter(items__product__store__owner=seller).exists():
                return 'no_orders_yet'
        except Exception:
            pass
        return None
    if key == 'training_started':
        from .models import SellerTrainingProgress
        return ('already_in_training'
                if SellerTrainingProgress.objects.filter(seller=seller).exists()
                else None)
    if key == 'has_shipping_template':
        try:
            from apps.shipping.models import ShippingTemplate
            if ShippingTemplate.objects.filter(seller=seller).exists():
                return 'has_template'
        except Exception:
            pass
        return None
    return None


def enqueue_email(*, seller=None, application=None, sequence_key: str,
                  context: dict = None, force: bool = False):
    """Queue one onboarding email. Idempotent on (seller, sequence_key)
    unless `force=True`. Suppression check runs here so the caller
    just hands us a key + context."""
    from .models import SellerEmailLog
    to_email = (
        getattr(seller, 'email', '') if seller else ''
    ) or (application.applicant_email if application else '')
    if not to_email:
        return None

    # Idempotency / suppression — already sent or scheduled?
    if not force and SellerEmailLog.objects.filter(
        seller=seller, sequence_key=sequence_key,
    ).exclude(status='failed').exists():
        return None

    # Behaviour-based suppression rule.
    suppression_key = next(
        (s[2] for s in DRIP_SEQUENCE if s[0] == sequence_key), None,
    )
    reason = _check_suppression(seller, suppression_key) if seller else None
    if reason:
        log = SellerEmailLog.objects.create(
            seller=seller, application=application,
            sequence_key=sequence_key, to_email=to_email,
            subject=DRIP_SUBJECTS.get(sequence_key, sequence_key),
            template_context=context or {}, status='suppressed',
            suppression_reason=reason,
        )
        return log

    # Dev/stub provider: we mark "sent" immediately so the suppression
    # ledger works. Production swaps `provider='stub'` for SendGrid/
    # SES via a wired backend.
    log = SellerEmailLog.objects.create(
        seller=seller, application=application,
        sequence_key=sequence_key, to_email=to_email,
        subject=DRIP_SUBJECTS.get(sequence_key, sequence_key),
        template_context=context or {}, status='sent',
        sent_at=timezone.now(), provider='stub',
    )
    from .models import SellerOnboardingEvent
    SellerOnboardingEvent.log(
        application=application, seller=seller,
        kind='email.enqueued',
        payload={'sequence_key': sequence_key, 'log_id': log.pk},
    )
    return log


def drive_drip_for_seller(seller) -> dict:
    """Walks the DRIP_SEQUENCE and enqueues every step whose
    `day_offset` has elapsed since the seller's activation date
    (= `seller.date_joined`).  Idempotent — already-sent steps
    are skipped by enqueue_email()."""
    now = timezone.now()
    activated_at = getattr(seller, 'date_joined', None) or now
    age_days = (now - activated_at).days
    queued = 0; suppressed = 0
    for key, day_offset, _ in DRIP_SEQUENCE:
        if age_days < day_offset:
            continue
        result = enqueue_email(seller=seller, sequence_key=key)
        if result is None:
            continue
        if result.status == 'suppressed':
            suppressed += 1
        else:
            queued += 1
    return {'queued': queued, 'suppressed': suppressed}


# ═══════════════════════════════════════════════════════════════════
# CH13 — Store type recalculation
# ═══════════════════════════════════════════════════════════════════

def recompute_store_type(seller) -> dict:
    """Choose the best store type the seller currently qualifies for.
    Order of precedence: choice > official_brand > factory_direct >
    gold > certified > standard. `is_pinned` rows are left alone."""
    from .models import (
        ChoiceEnrolment, OfficialBrandStoreApplication, SellerBrand,
        SellerCertificate, SellerStoreType, SellerTierState,
        STORE_TYPE_MULTIPLIERS,
    )
    state, _ = SellerStoreType.objects.get_or_create(seller=seller)
    if state.is_pinned:
        return {'pinned': True, 'store_type': state.store_type}

    chosen = 'standard'
    # Choice — active enrolment.
    if ChoiceEnrolment.objects.filter(seller=seller, status='active').exists():
        chosen = 'choice'
    elif OfficialBrandStoreApplication.objects.filter(
        seller=seller, status='approved',
    ).exists():
        chosen = 'official_brand'
    else:
        tier = SellerTierState.objects.filter(seller=seller).first()
        tier_name = tier.current_tier if tier else 'standard'
        certs = set(SellerCertificate.objects.filter(seller=seller).values_list('module_id', flat=True))
        core_certs = {'M1', 'M2', 'M4', 'M5'}
        if tier_name in ('gold', 'platinum', 'diamond'):
            chosen = 'gold'
        elif core_certs.issubset(certs):
            chosen = 'certified'

    state.store_type = chosen
    state.search_multiplier = STORE_TYPE_MULTIPLIERS.get(chosen, 1.0)
    state.badge_label = dict(
        standard='', certified='Certified', gold='Gold',
        official_brand='Official Brand', factory_direct='Factory Direct',
        choice='MICHA Choice',
    )[chosen]
    state.save(update_fields=['store_type', 'search_multiplier',
                              'badge_label', 'updated_at'])
    return {'store_type': chosen,
            'search_multiplier': state.search_multiplier}


def can_apply_official_brand(seller, brand) -> dict:
    """CH13.2 eligibility gates."""
    from .models import SellerTierState
    metrics = get_seller_metrics(seller)
    tier = SellerTierState.objects.filter(seller=seller).first()
    tier_name = tier.current_tier if tier else 'standard'
    if tier_name not in ('gold', 'platinum', 'diamond'):
        return {'ok': False, 'code': 'TIER_BELOW_GOLD', 'current_tier': tier_name}
    if metrics['dispute_rate'] > 0.005:
        return {'ok': False, 'code': 'DISPUTE_RATE_TOO_HIGH',
                'current': metrics['dispute_rate'], 'max': 0.005}
    if metrics['feedback_score'] < 0.98:
        return {'ok': False, 'code': 'FEEDBACK_TOO_LOW',
                'current': metrics['feedback_score'], 'min': 0.98}
    if brand.status != 'approved' or brand.brand_type != 'own_brand':
        return {'ok': False, 'code': 'BRAND_NOT_OWN_OR_NOT_APPROVED'}
    return {'ok': True}


# ═══════════════════════════════════════════════════════════════════
# CH17 — GMV rebate + fee waiver
# ═══════════════════════════════════════════════════════════════════

GMV_REBATE_SCHEDULE = [
    (Decimal('500000'), 100),
    (Decimal('200000'), 75),
    (Decimal('100000'), 50),
    (Decimal('50000'),  25),
]


def compute_gmv_rebate(seller, *, period_start, period_end) -> dict:
    """CH17. Compute the rebate row for one fee period.  The fee
    invoice amount is the multiplier; we don't actually transfer
    funds here — production calls the payouts service after."""
    from .models import SellerFeeInvoice, FeeRebate
    metrics = get_seller_metrics(seller)
    gmv = Decimal(str(metrics['gmv_usd']))
    pct = 0
    for threshold, rebate_pct in GMV_REBATE_SCHEDULE:
        if gmv >= threshold:
            pct = rebate_pct
            break
    if pct == 0:
        return {'eligible': False, 'gmv_usd': str(gmv)}

    # Look up the most recent paid fee invoice in this window.
    inv = (
        SellerFeeInvoice.objects.filter(
            application__seller=seller, status='paid',
            paid_at__date__gte=period_start, paid_at__date__lte=period_end,
        ).order_by('-paid_at').first()
    )
    if not inv:
        return {'eligible': False, 'reason': 'NO_PAID_INVOICE_IN_WINDOW'}
    rebate_amt = (inv.final_amount * Decimal(pct) / Decimal(100)).quantize(Decimal('0.01'))
    obj, created = FeeRebate.objects.update_or_create(
        seller=seller, fee_period_start=period_start,
        defaults={
            'fee_period_end': period_end, 'gmv_usd': gmv,
            'rebate_pct': pct, 'rebate_amount': rebate_amt,
            'currency': inv.currency, 'status': 'computed',
        },
    )
    return {'eligible': True, 'rebate_id': str(obj.id),
            'rebate_amount': str(rebate_amt), 'rebate_pct': pct}


def tier_fee_discount_pct(tier: str) -> int:
    """Per CH17 — Diamond = full waiver, Platinum = 50%."""
    if tier == 'diamond':  return 100
    if tier == 'platinum': return 50
    return 0


# ═══════════════════════════════════════════════════════════════════
# CH19 — API keys + webhooks
# ═══════════════════════════════════════════════════════════════════

def issue_api_key(*, seller, label: str, ttl_days: int = 365,
                  rate_limit: int = 1000) -> dict:
    """Returns the raw secret ONCE. The DB only ever has the hash."""
    from .models import SellerApiKey
    raw = SellerApiKey.generate_secret()
    obj = SellerApiKey.objects.create(
        seller=seller, label=label,
        key_prefix=raw[:12],
        key_hash=SellerApiKey.hash_secret(raw),
        rate_limit_per_hour=rate_limit,
        expires_at=timezone.now() + timedelta(days=ttl_days),
    )
    from .models import SellerOnboardingEvent
    SellerOnboardingEvent.log(
        seller=seller, kind='api_key.issued',
        payload={'key_id': str(obj.id), 'label': label},
    )
    return {'id': str(obj.id), 'secret': raw, 'prefix': obj.key_prefix,
            'expires_at': obj.expires_at.isoformat()}


def revoke_api_key(*, key_id, actor=None):
    from .models import SellerApiKey, SellerOnboardingEvent
    obj = SellerApiKey.objects.filter(pk=key_id).first()
    if not obj:
        return False
    obj.is_active = False
    obj.revoked_at = timezone.now()
    obj.save(update_fields=['is_active', 'revoked_at'])
    SellerOnboardingEvent.log(
        seller=obj.seller, actor=actor, kind='api_key.revoked',
        payload={'key_id': str(obj.id)},
    )
    return True


def register_webhook(*, seller, url: str, events: list) -> dict:
    """Creates the webhook + returns the secret ONCE. The verifying
    signature is HMAC-SHA256(secret, payload_body)."""
    import hmac as _hmac
    from .models import SellerWebhookEndpoint
    secret = secrets.token_urlsafe(32)
    obj = SellerWebhookEndpoint.objects.create(
        seller=seller, url=url, events=events,
        secret_hash=hashlib.sha256(secret.encode()).hexdigest(),
    )
    return {'id': str(obj.id), 'secret': secret,
            'url': url, 'events': events}


def deliver_webhook(*, endpoint, event_type: str, payload: dict) -> dict:
    """Single-attempt synchronous delivery. Production wraps this in
    a Celery task with exponential backoff."""
    import json, hmac as _hmac
    from .models import SellerWebhookDelivery
    # We can compute the signature against the stored hash because we
    # know the secret was hashed with sha256; for real HMAC we'd need
    # the raw secret. To keep the flow honest, signature is the SHA-
    # 256 of payload+secret_hash — production substitutes the raw
    # secret via SECURE_WEBHOOK_SECRETS_KMS or similar.
    body = json.dumps(payload, sort_keys=True, default=str)
    sig = hashlib.sha256((body + '|' + endpoint.secret_hash).encode()).hexdigest()
    delivery = SellerWebhookDelivery.objects.create(
        endpoint=endpoint, event_type=event_type, payload=payload,
        signature=sig,
    )
    return {'delivery_id': delivery.pk, 'signature': sig}


# ═══════════════════════════════════════════════════════════════════
# CH21 — Voluntary deregistration
# ═══════════════════════════════════════════════════════════════════

def deregistration_eligibility(seller) -> dict:
    """CH21 — 5 gates."""
    fails = []
    try:
        from apps.orders.models import Order
        open_states = ('pending', 'paid', 'processing', 'shipped', 'in_dispute')
        if Order.objects.filter(
            items__product__store__owner=seller, status__in=open_states,
        ).exists():
            fails.append('OPEN_ORDERS')
    except Exception:
        pass
    try:
        from apps.disputes.models import Dispute
        if Dispute.objects.filter(
            order__items__product__store__owner=seller, status='open',
        ).exists():
            fails.append('OPEN_DISPUTES')
    except Exception:
        pass
    # Balance gate — placeholder.  Plug in apps.payments.SellerBalance
    # when wired.
    # Annual fee debt gate.
    from .models import SellerFeeInvoice
    if SellerFeeInvoice.objects.filter(
        application__seller=seller, status='overdue',
    ).exists():
        fails.append('OUTSTANDING_FEE_DEBT')
    return {'ok': not fails, 'failures': fails}


def request_deregistration(*, seller) -> dict:
    """Open a request. If gates fail → status=blocked."""
    from .models import SellerDeregistrationRequest, SellerOnboardingEvent
    gate = deregistration_eligibility(seller)
    if not gate['ok']:
        obj = SellerDeregistrationRequest.objects.create(
            seller=seller, status='blocked',
            eligibility_gate=gate,
            blocked_reason=gate['failures'][0],
            effective_at=timezone.now(),
        )
        return {'ok': False, 'request_id': str(obj.id), 'gate': gate}
    obj = SellerDeregistrationRequest.objects.create(
        seller=seller, status='cooling_off',
        eligibility_gate=gate,
        effective_at=timezone.now() + timedelta(days=30),
    )
    SellerOnboardingEvent.log(
        seller=seller, kind='deregistration.requested',
        payload={'request_id': str(obj.id),
                 'effective_at': obj.effective_at.isoformat()},
    )
    return {'ok': True, 'request_id': str(obj.id),
            'effective_at': obj.effective_at.isoformat()}


def cancel_deregistration(seller) -> bool:
    """Seller can cancel during the 30-day cooling-off."""
    from .models import SellerDeregistrationRequest, SellerOnboardingEvent
    pending = SellerDeregistrationRequest.objects.filter(
        seller=seller, status='cooling_off',
    ).order_by('-requested_at').first()
    if not pending:
        return False
    pending.status = 'cancelled'
    pending.cancelled_at = timezone.now()
    pending.save(update_fields=['status', 'cancelled_at'])
    SellerOnboardingEvent.log(
        seller=seller, kind='deregistration.cancelled',
        payload={'request_id': str(pending.id)},
    )
    return True


def finalise_deregistration(req) -> dict:
    """Cooling-off elapsed — perform the offboarding. Anonymisation
    is best-effort across the apps that we know about."""
    from django.contrib.auth import get_user_model
    from .models import SellerOnboardingEvent
    User = get_user_model()
    seller = req.seller
    # 1) Soft-delete listings.
    try:
        from apps.products.models import Product
        Product.objects.filter(store__owner=seller).update(
            moderation_status='taken_down',
        )
    except Exception:
        pass
    # 2) Anonymise the user record.
    seller.is_active = False
    if hasattr(seller, 'is_seller'):
        seller.is_seller = False
    seller.email = f'deregistered-{seller.pk}@deleted.local'
    seller.save(update_fields=['is_active', 'email'] +
                (['is_seller'] if hasattr(seller, 'is_seller') else []))
    req.status = 'completed'
    req.completed_at = timezone.now()
    req.save(update_fields=['status', 'completed_at'])
    SellerOnboardingEvent.log(
        seller=seller, kind='deregistration.completed',
        payload={'request_id': str(req.id)},
    )
    return {'ok': True, 'request_id': str(req.id)}


# ═══════════════════════════════════════════════════════════════════
# CH22 — Choice programme eligibility
# ═══════════════════════════════════════════════════════════════════

def choice_eligibility(seller) -> dict:
    """CH22 — 6 hard gates before a Choice application is accepted."""
    from .models import SellerTierState
    metrics = get_seller_metrics(seller)
    fails = []
    # active_seller_days >= 180
    activated_at = getattr(seller, 'date_joined', None)
    if not activated_at or (timezone.now() - activated_at).days < 180:
        fails.append('TENURE_LESS_THAN_180_DAYS')
    if metrics['feedback_score'] < 0.97:
        fails.append('FEEDBACK_BELOW_0_97')
    if metrics['dispute_rate'] > 0.01:
        fails.append('DISPUTE_RATE_ABOVE_0_01')
    if metrics['on_time_shipping_rate'] < 0.95:
        fails.append('ON_TIME_SHIPPING_BELOW_0_95')
    tier = SellerTierState.objects.filter(seller=seller).first()
    tier_name = tier.current_tier if tier else 'standard'
    if tier_name not in ('silver', 'gold', 'platinum', 'diamond'):
        fails.append('TIER_BELOW_SILVER')
    return {'ok': not fails, 'failures': fails,
            'metrics': metrics, 'tier': tier_name}


def apply_to_choice(*, seller, warehouse_code: str, product_ids: list,
                    estimated_monthly_units: int = 0,
                    supplier_lead_time_days: int = 0) -> dict:
    from .models import ChoiceEnrolment, ChoiceWarehouse, SellerOnboardingEvent
    gate = choice_eligibility(seller)
    if not gate['ok']:
        return {'ok': False, 'gate': gate}
    wh = ChoiceWarehouse.objects.filter(code=warehouse_code, is_active=True).first()
    if not wh:
        return {'ok': False, 'code': 'WAREHOUSE_NOT_FOUND'}
    obj = ChoiceEnrolment.objects.create(
        seller=seller, warehouse=wh, product_ids=product_ids,
        estimated_monthly_units=estimated_monthly_units,
        supplier_lead_time_days=supplier_lead_time_days,
        metrics_snapshot=gate['metrics'],
    )
    SellerOnboardingEvent.log(
        seller=seller, kind='choice.application_received',
        payload={'enrolment_id': str(obj.id),
                 'warehouse': warehouse_code,
                 'products_count': len(product_ids)},
    )
    return {'ok': True, 'enrolment_id': str(obj.id)}


# ═══════════════════════════════════════════════════════════════════
# CH24 — Funnel snapshot
# ═══════════════════════════════════════════════════════════════════

def compute_funnel_snapshot(date=None) -> dict:
    """Roll up the funnel metrics for `date` (default today)."""
    from .models import (
        AcquisitionFunnelSnapshot, SellerApplication, SellerLead,
        SellerTierState,
    )
    if date is None:
        date = timezone.now().date()
    start = timezone.make_aware(
        timezone.datetime.combine(date, timezone.datetime.min.time()),
    ) if not hasattr(date, 'hour') else date
    end = start + timedelta(days=1)

    leads_submitted = SellerLead.objects.filter(
        created_at__gte=start, created_at__lt=end,
    ).count()
    leads_qualified = SellerLead.objects.filter(
        created_at__gte=start, created_at__lt=end, status='qualified',
    ).count()
    apps_started = SellerApplication.objects.filter(
        created_at__gte=start, created_at__lt=end,
    ).count()
    apps_submitted = SellerApplication.objects.filter(
        submitted_at__gte=start, submitted_at__lt=end,
    ).count()
    kyc_approved = SellerApplication.objects.filter(
        reviewed_at__gte=start, reviewed_at__lt=end, status__in=(
            'kyc_approved', 'agreement_sent', 'agreement_signed',
            'fee_pending', 'fee_paid', 'approved',
        ),
    ).count()
    activated = SellerApplication.objects.filter(
        approved_at__gte=start, approved_at__lt=end,
    ).count()

    by_country = dict(
        SellerApplication.objects.filter(approved_at__gte=start, approved_at__lt=end)
        .values_list('country').annotate(c=models.Count('id'))
    )
    by_lead_source = dict(
        SellerLead.objects.filter(created_at__gte=start, created_at__lt=end)
        .values_list('lead_source').annotate(c=models.Count('id'))
    )
    by_tier = dict(
        SellerTierState.objects.values_list('current_tier').annotate(c=models.Count('seller'))
    )

    obj, _ = AcquisitionFunnelSnapshot.objects.update_or_create(
        snapshot_date=date,
        defaults={
            'leads_submitted': leads_submitted,
            'leads_qualified': leads_qualified,
            'applications_started': apps_started,
            'applications_submitted': apps_submitted,
            'kyc_approved': kyc_approved,
            'activated': activated,
            'by_country': {k or '': v for k, v in by_country.items()},
            'by_lead_source': {k or '': v for k, v in by_lead_source.items()},
            'by_tier': {k or '': v for k, v in by_tier.items()},
        },
    )
    return {
        'date': str(date),
        'submitted': apps_submitted, 'kyc_approved': kyc_approved,
        'activated': activated, 'leads_submitted': leads_submitted,
    }
