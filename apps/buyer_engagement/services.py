"""
Buyer engagement domain services
=================================

Each function maps to a chapter in the doc. Pure-logic where it can
be (compute_dormancy_band, compute_ltv); side-effectful when it has
to be (release_first_purchase_rewards, start_recovery_sequence).
"""
from __future__ import annotations

import secrets
import logging
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.utils import timezone

from .models import (
    AcquisitionChannelSpend, BuyerAttributionTouch, BirthdayReward,
    BrowseAbandonmentSignal, BuyerKpiSnapshot, BuyerLTV,
    DormancyState, EmailLifecycleLog, EngagementEvent,
    FirstPurchaseTrigger, HomeFeedPersonalisation,
    MembershipBillingLog, MessageTemplate, PremiumMembership,
    PushDecision, RecoverySequenceState, ReferralActivation,
    SeasonalCampaign, SeasonalCampaignParticipant, SocialShareEvent,
    ViralLoopAttribution, WelcomeIncentive, WinBackCampaignRun,
    WELCOME_TYPE_CHOICES,
)

User = get_user_model()
log = logging.getLogger(__name__)


# ── CH2 — Attribution ────────────────────────────────────────────

def record_attribution(*, attribution_id: str, stage: str,
                       user=None, **fields) -> BuyerAttributionTouch:
    """Insert one touch in the attribution chain. Idempotent on
    (attribution_id, stage, user)."""
    existing = BuyerAttributionTouch.objects.filter(
        attribution_id=attribution_id, stage=stage,
        user=user,
    ).first()
    if existing:
        return existing
    touch = BuyerAttributionTouch.objects.create(
        attribution_id=attribution_id, stage=stage, user=user,
        channel=fields.get('channel', ''),
        utm_source=(fields.get('utm_source') or '')[:120],
        utm_medium=(fields.get('utm_medium') or '')[:120],
        utm_campaign=(fields.get('utm_campaign') or '')[:120],
        utm_term=(fields.get('utm_term') or '')[:120],
        utm_content=(fields.get('utm_content') or '')[:120],
        referrer=(fields.get('referrer') or '')[:255],
        landing_path=(fields.get('landing_path') or '')[:255],
        device_type=(fields.get('device_type') or '')[:16],
        country=(fields.get('country') or '')[:2],
    )
    EngagementEvent.log(
        user=user, kind=f'attribution.{stage}',
        payload={'channel': touch.channel,
                 'attribution_id': attribution_id,
                 'utm_source': touch.utm_source,
                 'utm_campaign': touch.utm_campaign},
    )
    return touch


def attribution_chain_for(user) -> dict:
    """Return first-touch and last-touch summary for a user."""
    touches = list(BuyerAttributionTouch.objects.filter(user=user).order_by('occurred_at'))
    if not touches:
        return {'first_touch': None, 'last_touch': None, 'count': 0}
    return {
        'first_touch': {
            'channel': touches[0].channel,
            'utm_source': touches[0].utm_source,
            'utm_campaign': touches[0].utm_campaign,
            'occurred_at': touches[0].occurred_at.isoformat(),
        },
        'last_touch': {
            'channel': touches[-1].channel,
            'utm_source': touches[-1].utm_source,
            'utm_campaign': touches[-1].utm_campaign,
            'occurred_at': touches[-1].occurred_at.isoformat(),
        },
        'count': len(touches),
    }


# ── CH3 — Welcome incentive ──────────────────────────────────────

# Country → default welcome offer. AOA tuned for the MICHA-Angola
# launch; USD blocks kept for parity with the doc.
WELCOME_OFFER_MATRIX = {
    'AO': {'type': 'coupon', 'amount': '500.00', 'currency': 'AOA',
           'min_order': '2500.00', 'ttl_days': 30},
    'US': {'type': 'coupon', 'amount': '5.00',  'currency': 'USD',
           'min_order': '25.00',  'ttl_days': 30},
    'BR': {'type': 'coupon', 'amount': '15.00', 'currency': 'BRL',
           'min_order': '75.00',  'ttl_days': 30},
}
DEFAULT_WELCOME = {'type': 'coupon', 'amount': '3.00', 'currency': 'USD',
                   'min_order': '15.00', 'ttl_days': 30}


def grant_welcome_incentive(*, user, country: str = '',
                            channel: str = '',
                            ip: str = '',
                            device_hash: str = '') -> WelcomeIncentive:
    """CH3 — single grant per user. Idempotent: if the user already
    has an `issued` or `used` incentive we return it unchanged. Runs
    the fraud engine first — a `block` decision voids the request
    without ever issuing a coupon."""
    existing = WelcomeIncentive.objects.filter(
        user=user, status__in=('issued', 'used'),
    ).first()
    if existing:
        return existing

    # Fraud check — abuse vector here is the "create N accounts to
    # farm N welcome coupons" pattern.
    try:
        from apps.fraud_engine.services import evaluate_fraud
        decision = evaluate_fraud(
            action='welcome_grant', user=user, ip=ip,
            device_hash=device_hash,
            email=getattr(user, 'email', ''),
        )
        if decision.decision == 'block':
            EngagementEvent.log(
                user=user, kind='welcome.fraud_blocked',
                payload={'reasons': decision.reasons,
                         'score': decision.score},
            )
            # Issue a placeholder voided row so the API caller sees
            # the rejection in /welcome/me/.
            return WelcomeIncentive.objects.create(
                user=user, incentive_type='coupon',
                coupon_code='', amount=Decimal('0'),
                currency='AOA', status='voided',
                voided_reason=f'fraud:{decision.score}',
                expires_at=timezone.now(),
            )
    except Exception:
        pass  # Fraud engine never blocks the welcome path on its own errors.
    cfg = WELCOME_OFFER_MATRIX.get((country or '').upper(), DEFAULT_WELCOME)
    code = 'WELCOME-' + secrets.token_urlsafe(6)[:8].upper()
    obj = WelcomeIncentive.objects.create(
        user=user, incentive_type=cfg['type'], coupon_code=code,
        amount=Decimal(cfg['amount']), currency=cfg['currency'],
        minimum_order_value=Decimal(cfg['min_order']),
        issued_via_channel=channel,
        expires_at=timezone.now() + timedelta(days=cfg['ttl_days']),
    )
    EngagementEvent.log(
        user=user, kind='welcome.issued',
        payload={'coupon_code': code, 'amount': cfg['amount'],
                 'currency': cfg['currency']},
    )
    # Mirror into the buyer-side email lifecycle log.
    if getattr(user, 'email', None):
        EmailLifecycleLog.objects.create(
            user=user, stage='welcome', template_key='welcome_coupon',
            to_email=user.email,
            subject=f'Welcome to MICHA — here\'s {cfg["amount"]} {cfg["currency"]} off',
            status='sent', sent_at=timezone.now(),
        )
    return obj


def void_welcome_incentive(user, reason: str) -> bool:
    """CH3.2 — anti-abuse void."""
    obj = WelcomeIncentive.objects.filter(user=user, status='issued').first()
    if not obj:
        return False
    obj.status = 'voided'
    obj.voided_reason = reason[:80]
    obj.save(update_fields=['status', 'voided_reason'])
    EngagementEvent.log(user=user, kind='welcome.voided',
                         payload={'reason': reason})
    return True


# ── CH4 — First purchase ─────────────────────────────────────────

@transaction.atomic
def record_first_purchase(*, user, order_id: str,
                          purchased_at=None) -> dict:
    """CH4.1. Idempotent — a second call for the same user returns
    the existing trigger row without re-issuing rewards. The
    `verify` step is called separately after the order moves past
    refund window."""
    purchased_at = purchased_at or timezone.now()
    trigger, created = FirstPurchaseTrigger.objects.get_or_create(
        user=user,
        defaults={'order_id': order_id, 'purchased_at': purchased_at,
                  'status': 'pending'},
    )
    if not created:
        return {'created': False, 'trigger_id': trigger.pk}

    # Mark welcome incentive used if present.
    inc = WelcomeIncentive.objects.filter(user=user, status='issued').first()
    if inc:
        inc.status = 'used'
        inc.used_at = timezone.now()
        inc.used_on_order_id = order_id
        inc.save(update_fields=['status', 'used_at', 'used_on_order_id'])

    # Add attribution touch.
    last = (
        BuyerAttributionTouch.objects.filter(user=user).order_by('-occurred_at').first()
    )
    record_attribution(
        attribution_id=last.attribution_id if last else f'u{user.pk}',
        stage='first_purchase', user=user,
        channel=last.channel if last else '',
    )

    EngagementEvent.log(
        user=user, kind='first_purchase.recorded',
        payload={'order_id': order_id, 'trigger_id': trigger.pk},
    )
    return {'created': True, 'trigger_id': trigger.pk}


def verify_first_purchase(*, user) -> dict:
    """Past refund window → mark verified and release rewards.
    Production calls this from a delayed Celery task ~14 days after
    purchase."""
    trigger = FirstPurchaseTrigger.objects.filter(user=user).first()
    if not trigger or trigger.status != 'pending':
        return {'ok': False, 'reason': 'NO_PENDING_TRIGGER'}
    trigger.status = 'verified'
    trigger.verified_at = timezone.now()
    released = ['welcome_incentive_used']
    # Release referral bonus if any.
    activation = ReferralActivation.objects.filter(
        referee_user=user, stage='registration',
    ).first()
    if activation:
        ReferralActivation.objects.create(
            referrer_user=activation.referrer_user,
            referral_code=activation.referral_code,
            referee_user=user, stage='first_purchase',
        )
        ReferralActivation.objects.create(
            referrer_user=activation.referrer_user,
            referral_code=activation.referral_code,
            referee_user=user, stage='rewarded',
        )
        released.append(f'referral_reward_to_user_{activation.referrer_user_id}')
        EngagementEvent.log(
            user=activation.referrer_user, kind='referral.rewarded',
            payload={'referee_user_id': user.pk, 'order_id': trigger.order_id},
        )
    trigger.rewards_released = released
    trigger.save(update_fields=['status', 'verified_at', 'rewards_released'])
    EngagementEvent.log(
        user=user, kind='first_purchase.verified',
        payload={'rewards': released},
    )
    return {'ok': True, 'rewards': released}


def revert_first_purchase(*, user, reason: str) -> bool:
    """Refund / chargeback within window → flip the trigger so any
    pending reward release is blocked, and void the welcome
    incentive."""
    trigger = FirstPurchaseTrigger.objects.filter(user=user).first()
    if not trigger:
        return False
    trigger.status = 'reverted'
    trigger.save(update_fields=['status'])
    void_welcome_incentive(user, reason=reason)
    EngagementEvent.log(
        user=user, kind='first_purchase.reverted',
        payload={'reason': reason},
    )
    return True


# ── CH5 — Referral activation ────────────────────────────────────

def record_referral_touch(*, referrer_user, referral_code: str,
                          stage: str, referee_user=None,
                          ip: str = '', fingerprint: str = '') -> ReferralActivation:
    # Cross-check with the heavyweight fraud engine in addition to
    # the legacy in-house heuristic. We keep the legacy score because
    # the engine is opt-in: if VelocityRule rows aren't seeded yet
    # the legacy check still flags farm patterns.
    legacy_score = _referral_fraud_score(referrer_user, ip, fingerprint)
    engine_score = 0
    try:
        from apps.fraud_engine.services import evaluate_fraud
        d = evaluate_fraud(
            action='referral_register' if stage == 'registration' else 'referral_click',
            user=referee_user or referrer_user,
            ip=ip, device_hash=fingerprint,
            email=getattr(referee_user, 'email', '') if referee_user else '',
        )
        engine_score = d.score
    except Exception:
        pass
    obj = ReferralActivation.objects.create(
        referrer_user=referrer_user, referral_code=referral_code,
        stage=stage, referee_user=referee_user,
        ip_address=ip or None, device_fingerprint=fingerprint[:64],
        fraud_score=max(legacy_score, engine_score),
    )
    EngagementEvent.log(
        user=referee_user or referrer_user, kind=f'referral.{stage}',
        payload={'referrer_user_id': referrer_user.pk,
                 'referee_user_id': referee_user.pk if referee_user else None,
                 'code': referral_code,
                 'fraud_score': obj.fraud_score},
    )
    return obj


def _referral_fraud_score(referrer_user, ip, fingerprint):
    """Cheap heuristic per CH5.3: more touches from same fingerprint
    in the last 24h → higher score."""
    if not fingerprint:
        return 0
    recent = ReferralActivation.objects.filter(
        device_fingerprint=fingerprint,
        occurred_at__gte=timezone.now() - timedelta(hours=24),
    ).count()
    return min(100, recent * 10)


# ── CH10 — Premium membership ────────────────────────────────────

PREMIUM_PRICING = {
    'monthly':   {'amount': '500.00',  'currency': 'AOA', 'days': 30},
    'quarterly': {'amount': '1350.00', 'currency': 'AOA', 'days': 90},
    'annual':    {'amount': '4800.00', 'currency': 'AOA', 'days': 365},
}


def enrol_premium(*, user, plan: str = 'monthly',
                  trial_days: int = 7) -> PremiumMembership:
    if plan not in PREMIUM_PRICING:
        plan = 'monthly'
    cfg = PREMIUM_PRICING[plan]
    now = timezone.now()
    obj, created = PremiumMembership.objects.get_or_create(
        user=user,
        defaults={
            'plan': plan,
            'status': 'trial' if trial_days > 0 else 'active',
            'monthly_price': Decimal(cfg['amount']),
            'currency': cfg['currency'],
            'current_period_start': now,
            'current_period_end': now + timedelta(days=cfg['days']),
            'trial_ends_at': (now + timedelta(days=trial_days)) if trial_days else None,
        },
    )
    if created:
        EngagementEvent.log(
            user=user, kind='premium.enrolled',
            payload={'plan': plan, 'trial_days': trial_days},
        )
    return obj


def cancel_premium(*, user, reason: str = '') -> bool:
    m = PremiumMembership.objects.filter(user=user).first()
    if not m or m.status in ('cancelled', 'expired'):
        return False
    m.auto_renew = False
    m.cancelled_at = timezone.now()
    m.cancel_reason = reason[:80]
    # Per CH10.3 — service continues until current_period_end. Only
    # status flips once the period closes.
    m.save(update_fields=['auto_renew', 'cancelled_at', 'cancel_reason'])
    EngagementEvent.log(user=user, kind='premium.cancelled',
                         payload={'reason': reason})
    return True


def charge_premium(*, user, psp_reference: str = '',
                   succeeded: bool = None,
                   failure_code: str = '') -> dict:
    """Charge the user's plan. If `succeeded` is None we route through
    the real PaymentGateway registry (Multicaixa for AOA, Stripe for
    USD/EUR/GBP/BRL, dev-stub otherwise). Pass an explicit bool to
    short-circuit (used by the dev billing sweep + tests)."""
    m = PremiumMembership.objects.filter(user=user).first()
    if not m:
        return {'ok': False, 'reason': 'NO_MEMBERSHIP'}
    cfg = PREMIUM_PRICING[m.plan]

    # Route through the gateway registry unless caller pinned the
    # outcome explicitly.
    if succeeded is None:
        try:
            from apps.payment_gateways.services import charge as _pg_charge
            result = _pg_charge(
                amount=m.monthly_price, currency=m.currency,
                purpose='premium_billing', user=user,
                country=getattr(user, 'country', '') or 'AO',
                idempotency_key=f'premium_{m.pk}_{int(m.current_period_end.timestamp())}',
                user_metadata={'phone': getattr(user, 'phone', '') or ''},
                gateway_metadata={},
            )
            succeeded = (result.get('status') == 'succeeded')
            psp_reference = result.get('gateway_intent_id') or psp_reference
            failure_code = result.get('failure_code') or failure_code
        except Exception as e:
            log.exception('premium gateway charge failed user=%s err=%s', user.pk, e)
            succeeded = False
            failure_code = 'GATEWAY_EXCEPTION'
    if succeeded:
        new_start = m.current_period_end
        new_end = new_start + timedelta(days=cfg['days'])
        MembershipBillingLog.objects.create(
            membership=m, amount=m.monthly_price, currency=m.currency,
            period_start=new_start, period_end=new_end,
            psp_reference=psp_reference, status='succeeded',
        )
        m.current_period_start = new_start
        m.current_period_end = new_end
        m.last_charged_at = timezone.now()
        m.failed_charge_count = 0
        if m.status in ('trial', 'grace'):
            m.status = 'active' if m.auto_renew else 'cancelled'
        m.save()
        EngagementEvent.log(user=user, kind='premium.charged_ok',
                             payload={'plan': m.plan})
        return {'ok': True, 'period_end': m.current_period_end.isoformat()}
    # Failed.
    MembershipBillingLog.objects.create(
        membership=m, amount=m.monthly_price, currency=m.currency,
        period_start=m.current_period_start, period_end=m.current_period_end,
        psp_reference=psp_reference, status='failed',
        failure_code=failure_code[:40],
    )
    m.failed_charge_count = (m.failed_charge_count or 0) + 1
    if m.failed_charge_count >= 3:
        m.status = 'expired'
    else:
        m.status = 'grace'
    m.save(update_fields=['failed_charge_count', 'status'])
    EngagementEvent.log(user=user, kind='premium.charge_failed',
                         payload={'attempt': m.failed_charge_count,
                                  'code': failure_code})
    return {'ok': False, 'attempt': m.failed_charge_count,
            'status': m.status}


# ── CH11/CH12 — Recovery sequences ───────────────────────────────

# 5-step cadence per CH11.2.
DEFAULT_RECOVERY_STEPS_HRS = [1, 4, 24, 48, 72]


def start_recovery_sequence(*, user, kind: str,
                            target_id: str = '',
                            target_payload=None,
                            steps_hrs=None) -> RecoverySequenceState:
    steps = steps_hrs or DEFAULT_RECOVERY_STEPS_HRS
    seq = RecoverySequenceState.objects.create(
        user=user, kind=kind, target_id=target_id,
        target_payload=target_payload or {},
        total_steps=len(steps),
        next_message_at=timezone.now() + timedelta(hours=steps[0]),
    )
    EngagementEvent.log(
        user=user, kind=f'recovery.{kind}_started',
        payload={'seq_id': seq.pk, 'steps': len(steps)},
    )
    return seq


def advance_recovery(seq: RecoverySequenceState,
                     steps_hrs=None) -> dict:
    """Move to the next step or complete. Caller is the Celery worker
    that just dispatched a message."""
    steps = steps_hrs or DEFAULT_RECOVERY_STEPS_HRS
    seq.last_message_sent_at = timezone.now()
    seq.current_step += 1
    if seq.current_step >= seq.total_steps:
        seq.status = 'completed'
    else:
        seq.next_message_at = timezone.now() + timedelta(
            hours=steps[min(seq.current_step, len(steps) - 1)],
        )
    seq.save(update_fields=[
        'last_message_sent_at', 'current_step',
        'next_message_at', 'status',
    ])
    EngagementEvent.log(
        user=seq.user, kind=f'recovery.{seq.kind}_step',
        payload={'seq_id': seq.pk, 'step': seq.current_step,
                 'status': seq.status},
    )
    return {'step': seq.current_step, 'status': seq.status}


def convert_recovery_sequences(*, user) -> int:
    """Called when the user makes a purchase — stop every active
    sequence and attribute conversion."""
    qs = RecoverySequenceState.objects.filter(user=user, status='active')
    n = 0
    for seq in qs:
        seq.status = 'converted'
        seq.converted_at = timezone.now()
        seq.save(update_fields=['status', 'converted_at'])
        EngagementEvent.log(
            user=user, kind=f'recovery.{seq.kind}_converted',
            payload={'seq_id': seq.pk, 'step_at_convert': seq.current_step},
        )
        n += 1
    return n


# ── CH13 — Browse abandonment signal ─────────────────────────────

def record_browse_signal(*, user, session_id: str,
                         product_ids: list,
                         primary_category: str = '',
                         avg_view_sec: int = 0) -> BrowseAbandonmentSignal:
    high_intent = len(product_ids) >= 3 and avg_view_sec >= 20
    obj = BrowseAbandonmentSignal.objects.create(
        user=user, session_id=session_id[:64],
        products_viewed_ids=product_ids[:50],
        primary_category_id=primary_category[:64],
        avg_view_duration_sec=avg_view_sec,
        high_intent=high_intent,
    )
    EngagementEvent.log(
        user=user, kind='browse.abandoned',
        payload={'signal_id': obj.pk, 'high_intent': high_intent,
                 'product_count': len(product_ids)},
    )
    return obj


# ── CH16 — Dormancy + Win-back ───────────────────────────────────

def compute_dormancy_band(days_since_purchase: int) -> str:
    if days_since_purchase <= 30:   return 'active'
    if days_since_purchase <= 60:   return 'lapsing'
    if days_since_purchase <= 90:   return 'dormant_60'
    if days_since_purchase <= 180:  return 'dormant_90'
    if days_since_purchase <= 365:  return 'dormant_180'
    return 'dormant_365_plus'


def update_dormancy_state(user) -> DormancyState:
    now = timezone.now()
    last_purchase = None
    try:
        from apps.orders.models import Order
        # NOTE: Order's buyer FK is named `buyer`, NOT `user`.
        last_purchase = Order.objects.filter(
            buyer=user, status__in=('paid', 'shipped', 'delivered', 'completed'),
        ).order_by('-created_at').values_list('created_at', flat=True).first()
    except Exception:
        pass
    last_session = getattr(user, 'last_login', None)
    days_purchase = (now - last_purchase).days if last_purchase else 9999
    days_session = (now - last_session).days if last_session else 9999

    lifetime_orders = 0
    lifetime_gmv = Decimal('0')
    try:
        from apps.orders.models import Order
        agg = Order.objects.filter(buyer=user).aggregate(
            n=models.Count('id'), s=models.Sum('total_amount'),
        )
        lifetime_orders = agg['n'] or 0
        lifetime_gmv = Decimal(str(agg['s'] or 0))
    except Exception:
        pass

    band = compute_dormancy_band(days_purchase)
    obj, _ = DormancyState.objects.update_or_create(
        user=user,
        defaults={
            'band': band, 'last_purchase_at': last_purchase,
            'days_since_last_purchase': min(days_purchase, 32767),
            'last_session_at': last_session,
            'days_since_last_session': min(days_session, 32767),
            'lifetime_orders': lifetime_orders,
            'lifetime_gmv': lifetime_gmv,
        },
    )
    return obj


def queue_winback(user, band: str) -> WinBackCampaignRun:
    """Idempotent — one send per (user, band) per day."""
    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    existing = WinBackCampaignRun.objects.filter(
        user=user, band=band, sent_at__gte=today_start,
    ).first()
    if existing:
        return existing
    template_map = {
        'lapsing':         ('lapsing_nudge',     'coupon',  Decimal('300')),
        'dormant_60':      ('dormant_60_offer',  'coupon',  Decimal('500')),
        'dormant_90':      ('dormant_90_offer',  'coupon',  Decimal('1000')),
        'dormant_180':     ('dormant_180_offer', 'coupon',  Decimal('2000')),
        'dormant_365_plus':('dormant_365_offer', 'coupon',  Decimal('3000')),
    }
    if band not in template_map:
        return None  # No win-back for active/dormant_30 (too early/too late nuance handled elsewhere)
    tpl, kind, value = template_map[band]
    run = WinBackCampaignRun.objects.create(
        user=user, band=band, template_key=tpl,
        incentive_kind=kind, incentive_value=value,
        channels_used=['email', 'push'],
    )
    EngagementEvent.log(
        user=user, kind='winback.queued',
        payload={'band': band, 'template': tpl, 'value': str(value)},
    )
    return run


# ── CH17 — Push decision ─────────────────────────────────────────

def record_push_decision(*, user, push_type: str, decision: str,
                          reason: str = '', segment_id: str = ''):
    return PushDecision.objects.create(
        user=user, push_type=push_type[:40], decision=decision,
        reason=reason[:80], segment_id=segment_id[:64],
    )


# ── CH19 — Home feed personalisation snapshot ───────────────────

def snapshot_home_feed(*, user, affinity: dict,
                       blocks_selected: list,
                       blocks_demoted: list = None,
                       experiment_id: str = '') -> HomeFeedPersonalisation:
    return HomeFeedPersonalisation.objects.create(
        user=user, affinity_vector=affinity,
        blocks_selected=blocks_selected[:20],
        blocks_demoted=(blocks_demoted or [])[:20],
        experiment_id=experiment_id[:40],
    )


# ── CH20 — Birthday reward ───────────────────────────────────────

def grant_birthday_reward(user) -> BirthdayReward:
    today = timezone.now().date()
    year = today.year
    obj, created = BirthdayReward.objects.get_or_create(
        user=user, birthday_year=year,
        defaults={
            'coupon_code': 'BIRTHDAY-' + secrets.token_urlsafe(6)[:8].upper(),
            'coins_granted': 100,
            'expires_at': timezone.now() + timedelta(days=14),
        },
    )
    if created:
        EngagementEvent.log(
            user=user, kind='birthday.granted',
            payload={'code': obj.coupon_code, 'coins': obj.coins_granted},
        )
    return obj


# ── CH21 — Seasonal campaign ─────────────────────────────────────

def enrol_user_in_campaign(*, user, campaign: SeasonalCampaign,
                           auto: bool = True) -> SeasonalCampaignParticipant:
    obj, _ = SeasonalCampaignParticipant.objects.get_or_create(
        campaign=campaign, user=user,
        defaults={'auto_enrolled': auto},
    )
    return obj


# ── CH22 — Social sharing ────────────────────────────────────────

def create_share_link(*, sharer, target: str, entity_kind: str,
                      entity_id: str) -> SocialShareEvent:
    obj = SocialShareEvent.objects.create(
        sharer=sharer, share_target=target, shared_entity=entity_kind,
        entity_id=entity_id[:64],
        short_code=SocialShareEvent.make_short_code(),
    )
    EngagementEvent.log(
        user=sharer, kind='share.created',
        payload={'target': target, 'entity': entity_kind,
                 'short_code': obj.short_code},
    )
    return obj


def record_share_click(short_code: str) -> bool:
    n = SocialShareEvent.objects.filter(short_code=short_code).update(
        clicks=models.F('clicks') + 1,
    )
    return bool(n)


def record_share_conversion(*, short_code: str, converted_user,
                            kind: str = 'install'):
    share = SocialShareEvent.objects.filter(short_code=short_code).first()
    if not share:
        return None
    SocialShareEvent.objects.filter(pk=share.pk).update(
        conversions=models.F('conversions') + 1,
    )
    return ViralLoopAttribution.objects.create(
        share_event=share, converted_user=converted_user,
        conversion_kind=kind[:24],
    )


# ── CH23 — LTV ───────────────────────────────────────────────────

def compute_ltv(user) -> BuyerLTV:
    now = timezone.now()
    r90 = r180 = r365 = rl = Decimal('0')
    n_orders = 0
    try:
        from apps.orders.models import Order
        qs = Order.objects.filter(buyer=user)
        rl = Decimal(str(qs.aggregate(s=models.Sum('total_amount'))['s'] or 0))
        n_orders = qs.count()
        for days, attr in ((90, 'r90'), (180, 'r180'), (365, 'r365')):
            v = Decimal(str(qs.filter(
                created_at__gte=now - timedelta(days=days),
            ).aggregate(s=models.Sum('total_amount'))['s'] or 0))
            if attr == 'r90': r90 = v
            elif attr == 'r180': r180 = v
            else: r365 = v
    except Exception:
        pass

    # Lightweight RFM bucketing.  Recency: smaller days → higher.
    dorm = DormancyState.objects.filter(user=user).first()
    days_recent = dorm.days_since_last_purchase if dorm else 9999
    if   days_recent <= 30:  rfm_r = 5
    elif days_recent <= 60:  rfm_r = 4
    elif days_recent <= 90:  rfm_r = 3
    elif days_recent <= 180: rfm_r = 2
    else:                    rfm_r = 1
    if   n_orders >= 20: rfm_f = 5
    elif n_orders >= 10: rfm_f = 4
    elif n_orders >= 5:  rfm_f = 3
    elif n_orders >= 2:  rfm_f = 2
    else:                rfm_f = 1
    if   rl >= 100000: rfm_m = 5
    elif rl >= 50000:  rfm_m = 4
    elif rl >= 20000:  rfm_m = 3
    elif rl >= 5000:   rfm_m = 2
    else:              rfm_m = 1

    score = rfm_r + rfm_f + rfm_m
    if   score >= 13: segment = 'VIP'
    elif score >= 10: segment = 'High'
    elif score >= 7:  segment = 'Mid'
    else:             segment = 'Low'

    # Cheap predicted LTV — repeat-rate × AOV × expected orders.
    aov = (rl / n_orders) if n_orders else Decimal('0')
    expected_orders_12m = Decimal(rfm_f) * Decimal('1.2')
    predicted = (aov * expected_orders_12m).quantize(Decimal('0.01'))
    confidence = min(0.99, 0.30 + n_orders * 0.05)

    obj, _ = BuyerLTV.objects.update_or_create(
        user=user,
        defaults={
            'realised_90d': r90, 'realised_180d': r180,
            'realised_365d': r365, 'realised_lifetime': rl,
            'predicted_next_12m': predicted, 'confidence': confidence,
            'segment': segment,
            'rfm_recency': rfm_r, 'rfm_frequency': rfm_f, 'rfm_monetary': rfm_m,
        },
    )
    return obj


# ── CH24 — KPI snapshot ──────────────────────────────────────────

def compute_buyer_kpi_snapshot(snapshot_date=None) -> BuyerKpiSnapshot:
    if snapshot_date is None:
        snapshot_date = timezone.now().date()
    start = timezone.make_aware(
        timezone.datetime.combine(snapshot_date, timezone.datetime.min.time()),
    )
    end = start + timedelta(days=1)
    new_users = User.objects.filter(date_joined__gte=start, date_joined__lt=end).count()
    # First-purchasers triggered today.
    new_buyers = FirstPurchaseTrigger.objects.filter(
        created_at__gte=start, created_at__lt=end,
    ).count()
    # Cohort: users who joined in last 30d & purchased within 7d / 30d.
    thirty = start - timedelta(days=30)
    cohort = User.objects.filter(date_joined__gte=thirty, date_joined__lt=start)
    cohort_size = cohort.count()
    cohort_ids = list(cohort.values_list('pk', flat=True))
    triggers_7d = 0; triggers_30d = 0
    if cohort_ids:
        for fpt in FirstPurchaseTrigger.objects.filter(user_id__in=cohort_ids):
            delta = (fpt.purchased_at - fpt.user.date_joined).days
            if delta <= 7:  triggers_7d += 1
            if delta <= 30: triggers_30d += 1
    first_7d_pct = triggers_7d / cohort_size if cohort_size else 0
    first_30d_pct = triggers_30d / cohort_size if cohort_size else 0
    activation_rate = new_buyers / new_users if new_users else 0

    # Avg order value + repeat-buyer rate from the realised LTV table.
    repeat_buyers = BuyerLTV.objects.filter(rfm_frequency__gte=2).count()
    total_buyers = BuyerLTV.objects.exclude(realised_lifetime=0).count()
    repeat_rate = (repeat_buyers / total_buyers) if total_buyers else 0
    dormant_pop = DormancyState.objects.filter(
        band__startswith='dormant',
    ).count()

    by_channel = dict(
        BuyerAttributionTouch.objects.filter(stage='registration', occurred_at__gte=start, occurred_at__lt=end)
        .values_list('channel').annotate(c=models.Count('id'))
    )
    by_segment = dict(
        BuyerLTV.objects.values_list('segment').annotate(c=models.Count('user'))
    )

    obj, _ = BuyerKpiSnapshot.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'new_users': new_users, 'new_buyers': new_buyers,
            'first_purchase_within_7d_pct': first_7d_pct,
            'first_purchase_within_30d_pct': first_30d_pct,
            'activation_rate': activation_rate,
            'repeat_buyer_rate': repeat_rate,
            'dormant_population': dormant_pop,
            'by_channel': {k or '': v for k, v in by_channel.items()},
            'by_segment': {k or '': v for k, v in by_segment.items()},
        },
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH19 — Affinity vector computation
# ═══════════════════════════════════════════════════════════════════

def compute_affinity_vector(user) -> dict:
    """Aggregate behavioural signals into a buyer-affinity vector.

    Sources we tap (whichever are installed):
      - apps.recommendations.ProductInteraction (view/click/wishlist/cart/purchase)
      - apps.ai_engine.BehavioralEvent          (richer event stream)
      - apps.orders.Order                        (realised demand)

    Output is a normalised dict that downstream personalisers consume:
      {
        'categories':  {cat_id: weight_0_to_1, ...},
        'brands':      {brand: weight, ...},
        'price_band':  'low'|'mid'|'high'|'luxury',
        'recency':     {'last_7d_events': N, 'last_30d_events': N},
        'taste_words': ['minimalist', 'vintage', ...]  # optional
      }
    """
    from collections import Counter
    now = timezone.now()
    window_start = now - timedelta(days=90)

    category_weights = Counter()
    brand_weights = Counter()
    last_7d = 0
    last_30d = 0
    price_amounts = []

    # ── ProductInteraction stream ─────────────────────────────
    try:
        from apps.recommendations.models import ProductInteraction
        # Weights: view=1, click=2, wishlist=4, add_to_cart=6, purchase=10
        weight_map = {
            'view': 1, 'click': 2, 'wishlist': 4,
            'add_to_cart': 6, 'purchase': 10,
        }
        interactions = ProductInteraction.objects.filter(
            user=user, created_at__gte=window_start,
        ).select_related('product').values(
            'product__category__name', 'product__brand',
            'product__price', 'interaction_type', 'created_at',
        )
        for row in interactions:
            w = weight_map.get(row.get('interaction_type'), 1)
            cat = row.get('product__category__name') or ''
            br = row.get('product__brand') or ''
            if cat:
                category_weights[cat] += w
            if br:
                brand_weights[br] += w
            price = row.get('product__price')
            if price:
                price_amounts.append(float(price))
            ts = row.get('created_at')
            if ts:
                age_days = (now - ts).days
                if age_days <= 7:  last_7d += 1
                if age_days <= 30: last_30d += 1
    except Exception:
        pass

    # ── BehavioralEvent stream ────────────────────────────────
    try:
        from apps.ai_engine.models import BehavioralEvent
        events = BehavioralEvent.objects.filter(
            user=user, created_at__gte=window_start,
        ).values('event_type', 'metadata', 'created_at')[:5000]
        for ev in events:
            cat = (ev.get('metadata') or {}).get('category')
            if cat:
                category_weights[cat] += 1
            ts = ev.get('created_at')
            if ts:
                age = (now - ts).days
                if age <= 7:  last_7d += 1
                if age <= 30: last_30d += 1
    except Exception:
        pass

    # ── Orders ─────────────────────────────────────────────────
    try:
        from apps.orders.models import Order
        orders = Order.objects.filter(
            buyer=user, created_at__gte=window_start,
        ).values('total_amount', 'created_at')
        for o in orders:
            if o['total_amount']:
                price_amounts.append(float(o['total_amount']))
    except Exception:
        pass

    # Normalise category & brand weights → 0-1.
    def _normalise(counter):
        total = sum(counter.values()) or 1
        return {k: round(v / total, 4) for k, v in counter.most_common(20)}

    # Price band.
    avg_price = (sum(price_amounts) / len(price_amounts)) if price_amounts else 0
    if   avg_price >= 50000: price_band = 'luxury'
    elif avg_price >= 15000: price_band = 'high'
    elif avg_price >= 3000:  price_band = 'mid'
    else:                    price_band = 'low'

    affinity = {
        'categories':  _normalise(category_weights),
        'brands':      _normalise(brand_weights),
        'price_band':  price_band,
        'avg_price':   round(avg_price, 2),
        'recency':     {'last_7d_events': last_7d,
                        'last_30d_events': last_30d},
        'computed_at': now.isoformat(),
    }
    return affinity


def snapshot_home_feed_for(user, *, experiment_id: str = '') -> HomeFeedPersonalisation:
    """Compute the affinity vector, decide which feed blocks to show
    given the affinity, and persist the snapshot. The rendering layer
    reads back the latest snapshot for the user on home page mount.
    """
    affinity = compute_affinity_vector(user)
    blocks_selected = []
    blocks_demoted = []

    # Block selection logic.  Simple heuristic — production swaps a
    # learned policy in here.
    if affinity['recency']['last_30d_events'] >= 10:
        blocks_selected.append('recently_viewed_resume')
    if affinity['categories']:
        top_cat = max(affinity['categories'], key=affinity['categories'].get)
        blocks_selected.append(f'category_top_{top_cat}')
    if affinity['price_band'] in ('high', 'luxury'):
        blocks_selected.append('premium_picks')
    else:
        blocks_demoted.append('premium_picks')
        blocks_selected.append('budget_finds')
    blocks_selected.extend([
        'flash_sale', 'new_arrivals', 'trending_now',
        'top_picks_for_you',
    ])

    snap = HomeFeedPersonalisation.objects.create(
        user=user, affinity_vector=affinity,
        blocks_selected=blocks_selected[:20],
        blocks_demoted=blocks_demoted[:20],
        experiment_id=experiment_id[:40],
    )
    EngagementEvent.log(
        user=user, kind='affinity.computed',
        payload={'snapshot_id': snap.pk,
                 'top_category': blocks_selected[0] if blocks_selected else None,
                 'price_band': affinity['price_band']},
    )
    return snap


# ═══════════════════════════════════════════════════════════════════
# Template catalogue + render helpers
# ═══════════════════════════════════════════════════════════════════

def render_template(*, key: str, kind: str, locale: str = 'pt-AO',
                    context: dict = None) -> dict:
    """Pick the right MessageTemplate row and return rendered fields.
    Falls back to (key, kind, 'pt-AO') if the requested locale is
    missing, then to ('en-US')."""
    context = context or {}
    tpl = (
        MessageTemplate.objects.filter(key=key, kind=kind, locale=locale, is_active=True).first()
        or MessageTemplate.objects.filter(key=key, kind=kind, locale='pt-AO', is_active=True).first()
        or MessageTemplate.objects.filter(key=key, kind=kind, locale='en-US', is_active=True).first()
        or MessageTemplate.objects.filter(key=key, kind=kind, is_active=True).first()
    )
    if not tpl:
        return {'found': False, 'subject': '', 'body': '', 'deep_link': '', 'cta_label': ''}

    def _safe(s):
        try:
            return s.format(**{k: ('' if v is None else v) for k, v in context.items()})
        except Exception:
            return s

    return {
        'found': True,
        'subject': _safe(tpl.subject),
        'body': _safe(tpl.body),
        'deep_link': _safe(tpl.deep_link),
        'cta_label': _safe(tpl.cta_label),
    }
