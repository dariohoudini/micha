"""
Buyer engagement REST endpoints.

Public-ish (no auth) endpoints accept attribution touches and share
clicks — those are necessary entry points for the user before they
have a session. Authenticated endpoints expose per-user state +
admin endpoints expose roll-ups.
"""
from __future__ import annotations

from datetime import date as date_cls
from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import (
    AcquisitionChannelSpend, BuyerAttributionTouch, BirthdayReward,
    BrowseAbandonmentSignal, BuyerKpiSnapshot, BuyerLTV,
    DormancyState, EmailLifecycleLog, EngagementEvent,
    FirstPurchaseTrigger, MembershipBillingLog, PremiumMembership,
    RecoverySequenceState, SeasonalCampaign, SocialShareEvent,
    WelcomeIncentive, WinBackCampaignRun,
)


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        u = getattr(request, 'user', None)
        return bool(u and u.is_authenticated and getattr(u, 'is_staff', False))


# ─── CH2 — Attribution (public) ─────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def record_attribution_view(request):
    """POST /attribution/touch  body:
    {attribution_id, stage, channel, utm_source, ...}."""
    attr_id = (request.data.get('attribution_id') or '')[:64]
    stage = request.data.get('stage')
    if not attr_id or not stage:
        return Response({'detail': 'attribution_id and stage required'}, status=400)
    user = request.user if request.user.is_authenticated else None
    touch = services.record_attribution(
        attribution_id=attr_id, stage=stage, user=user,
        channel=request.data.get('channel', ''),
        utm_source=request.data.get('utm_source', ''),
        utm_medium=request.data.get('utm_medium', ''),
        utm_campaign=request.data.get('utm_campaign', ''),
        utm_term=request.data.get('utm_term', ''),
        utm_content=request.data.get('utm_content', ''),
        referrer=request.data.get('referrer', ''),
        landing_path=request.data.get('landing_path', ''),
        device_type=request.data.get('device_type', ''),
        country=request.data.get('country', ''),
    )
    return Response({'touch_id': touch.pk}, status=201)


class MyAttributionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(services.attribution_chain_for(request.user))


# ─── CH3 — Welcome ──────────────────────────────────────────────

class MyWelcomeIncentiveView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        inc = WelcomeIncentive.objects.filter(user=request.user).first()
        if not inc:
            return Response({'detail': 'none'}, status=404)
        return Response({
            'coupon_code': inc.coupon_code,
            'amount': str(inc.amount), 'currency': inc.currency,
            'minimum_order_value': str(inc.minimum_order_value),
            'status': inc.status,
            'expires_at': inc.expires_at.isoformat(),
            'used_at': inc.used_at and inc.used_at.isoformat(),
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def grant_welcome_view(request):
    """POST /welcome/grant — idempotent self-grant for the requesting
    user. Production triggers this from the registration signal."""
    inc = services.grant_welcome_incentive(
        user=request.user,
        country=request.data.get('country', '') or
                (getattr(request.user, 'country', '') or ''),
        channel=request.data.get('channel', ''),
    )
    return Response({'coupon_code': inc.coupon_code,
                     'amount': str(inc.amount),
                     'currency': inc.currency,
                     'expires_at': inc.expires_at.isoformat()})


# ─── CH4 — First purchase ──────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def first_purchase_record(request):
    """Admin / internal endpoint — order app calls into this after
    payment confirmation. Body: {user_id, order_id}."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u = get_object_or_404(User, pk=request.data.get('user_id'))
    return Response(services.record_first_purchase(
        user=u, order_id=request.data.get('order_id', '')[:64],
    ))


@api_view(['POST'])
@permission_classes([IsAdmin])
def first_purchase_verify(request):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u = get_object_or_404(User, pk=request.data.get('user_id'))
    return Response(services.verify_first_purchase(user=u))


# ─── CH10 — Premium membership ─────────────────────────────────

class MyMembershipView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        m = PremiumMembership.objects.filter(user=request.user).first()
        if not m:
            return Response({'state': 'none'})
        return Response({
            'plan': m.plan, 'status': m.status,
            'started_at': m.started_at.isoformat(),
            'current_period_end': m.current_period_end.isoformat(),
            'trial_ends_at': m.trial_ends_at and m.trial_ends_at.isoformat(),
            'auto_renew': m.auto_renew,
            'monthly_price': str(m.monthly_price), 'currency': m.currency,
            'cancelled_at': m.cancelled_at and m.cancelled_at.isoformat(),
            'failed_charge_count': m.failed_charge_count,
        })

    def post(self, request):
        m = services.enrol_premium(
            user=request.user, plan=request.data.get('plan', 'monthly'),
            trial_days=int(request.data.get('trial_days') or 7),
        )
        return Response({'plan': m.plan, 'status': m.status}, status=201)

    def delete(self, request):
        ok = services.cancel_premium(
            user=request.user,
            reason=request.data.get('reason', '') if isinstance(request.data, dict) else '',
        )
        return Response({'cancelled': ok})


@api_view(['POST'])
@permission_classes([IsAdmin])
def membership_charge(request):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u = get_object_or_404(User, pk=request.data.get('user_id'))
    return Response(services.charge_premium(
        user=u, psp_reference=request.data.get('psp_reference', ''),
        succeeded=bool(request.data.get('succeeded', True)),
        failure_code=request.data.get('failure_code', ''),
    ))


# ─── CH11/12 — Recovery sequences ───────────────────────────────

class MyRecoverySequencesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = RecoverySequenceState.objects.filter(user=request.user).values(
            'id', 'kind', 'target_id', 'current_step', 'total_steps',
            'next_message_at', 'last_message_sent_at',
            'status', 'converted_at', 'started_at',
        )[:50]
        return Response(list(rows))


@api_view(['POST'])
@permission_classes([IsAdmin])
def recovery_start(request):
    """Admin entrypoint: caller wires this to cart/checkout/browse
    detection. Body: {user_id, kind, target_id, target_payload}."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    u = get_object_or_404(User, pk=request.data.get('user_id'))
    seq = services.start_recovery_sequence(
        user=u, kind=request.data.get('kind', 'cart'),
        target_id=request.data.get('target_id', ''),
        target_payload=request.data.get('target_payload') or {},
    )
    return Response({'seq_id': seq.pk}, status=201)


# ─── CH13 — Browse abandonment ─────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def record_browse_signal_view(request):
    """POST /browse/abandon  body: {session_id, product_ids,
    primary_category_id, avg_view_sec}."""
    obj = services.record_browse_signal(
        user=request.user,
        session_id=request.data.get('session_id', ''),
        product_ids=request.data.get('product_ids') or [],
        primary_category=request.data.get('primary_category_id', ''),
        avg_view_sec=int(request.data.get('avg_view_sec') or 0),
    )
    return Response({'signal_id': obj.pk, 'high_intent': obj.high_intent},
                    status=201)


# ─── CH16 — Dormancy + win-back ────────────────────────────────

class MyDormancyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        obj = services.update_dormancy_state(request.user)
        return Response({
            'band': obj.band,
            'days_since_last_purchase': obj.days_since_last_purchase,
            'days_since_last_session': obj.days_since_last_session,
            'lifetime_orders': obj.lifetime_orders,
            'lifetime_gmv': str(obj.lifetime_gmv),
            'updated_at': obj.updated_at.isoformat(),
        })


class MyWinBackRunsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = WinBackCampaignRun.objects.filter(user=request.user).values(
            'id', 'band', 'template_key', 'incentive_kind',
            'incentive_value', 'channels_used', 'outcome',
            'sent_at', 'opened_at', 'clicked_at', 'reactivated_at',
        )[:50]
        return Response(list(rows))


# ─── CH20 — Birthday ───────────────────────────────────────────

class MyBirthdayRewardsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = BirthdayReward.objects.filter(user=request.user).values(
            'birthday_year', 'coupon_code', 'coins_granted',
            'sent_at', 'expires_at', 'used_at',
        )
        return Response(list(rows))


# ─── CH21 — Seasonal campaigns ─────────────────────────────────

class SeasonalCampaignListView(APIView):
    """GET /campaigns/active — currently live seasonal campaigns."""
    permission_classes = [AllowAny]

    def get(self, request):
        now = timezone.now()
        qs = SeasonalCampaign.objects.filter(
            status='live', starts_at__lte=now, ends_at__gte=now,
        ).values('id', 'slug', 'name', 'starts_at', 'ends_at',
                 'discount_pct', 'banner_key', 'boost_multiplier')
        return Response(list(qs))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def campaign_join(request, slug):
    campaign = get_object_or_404(SeasonalCampaign, slug=slug, status='live')
    p = services.enrol_user_in_campaign(user=request.user, campaign=campaign, auto=False)
    return Response({'campaign': slug, 'participant_id': p.pk}, status=201)


# ─── CH22 — Social share ───────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def share_create(request):
    """POST /shares  body: {target, entity_kind, entity_id}."""
    obj = services.create_share_link(
        sharer=request.user,
        target=request.data.get('target', 'copy_link'),
        entity_kind=request.data.get('entity_kind', 'product'),
        entity_id=request.data.get('entity_id', ''),
    )
    return Response({'short_code': obj.short_code,
                     'id': obj.pk}, status=201)


@api_view(['GET'])
@permission_classes([AllowAny])
def share_click(request, short_code):
    """GET /s/<short_code> — share-click capture; returns the entity
    pointer so the FE can navigate. No auth required (this is the
    pre-install landing path)."""
    services.record_share_click(short_code)
    share = SocialShareEvent.objects.filter(short_code=short_code).first()
    if not share:
        return Response({'detail': 'not found'}, status=404)
    return Response({
        'shared_entity': share.shared_entity,
        'entity_id': share.entity_id,
        'sharer_id': share.sharer_id,
    })


class MyShareStatsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = SocialShareEvent.objects.filter(sharer=request.user).values(
            'short_code', 'share_target', 'shared_entity', 'entity_id',
            'clicks', 'conversions', 'created_at',
        )[:100]
        return Response(list(rows))


# ─── CH23 — LTV ────────────────────────────────────────────────

class MyLTVView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        ltv = services.compute_ltv(request.user)
        return Response({
            'realised_90d': str(ltv.realised_90d),
            'realised_180d': str(ltv.realised_180d),
            'realised_365d': str(ltv.realised_365d),
            'realised_lifetime': str(ltv.realised_lifetime),
            'predicted_next_12m': str(ltv.predicted_next_12m),
            'confidence': ltv.confidence, 'segment': ltv.segment,
            'rfm': {'r': ltv.rfm_recency, 'f': ltv.rfm_frequency,
                    'm': ltv.rfm_monetary},
            'last_computed_at': ltv.last_computed_at.isoformat(),
        })


# ─── CH24 — KPI ────────────────────────────────────────────────

class BuyerKpiSnapshotView(APIView):
    """GET /admin/buyer-kpis/?date=YYYY-MM-DD — daily snapshot.
    POST recompute now."""
    permission_classes = [IsAdmin]

    def get(self, request):
        d_str = request.query_params.get('date')
        d = date_cls.fromisoformat(d_str) if d_str else timezone.now().date()
        snap = BuyerKpiSnapshot.objects.filter(snapshot_date=d).first()
        if not snap:
            snap = services.compute_buyer_kpi_snapshot(snapshot_date=d)
        return Response({
            'date': str(snap.snapshot_date),
            'new_users': snap.new_users, 'new_buyers': snap.new_buyers,
            'activation_rate': snap.activation_rate,
            'first_purchase_within_7d_pct': snap.first_purchase_within_7d_pct,
            'first_purchase_within_30d_pct': snap.first_purchase_within_30d_pct,
            'repeat_buyer_rate': snap.repeat_buyer_rate,
            'dormant_population': snap.dormant_population,
            'by_channel': snap.by_channel, 'by_segment': snap.by_segment,
        })

    def post(self, request):
        d_str = request.data.get('date')
        d = date_cls.fromisoformat(d_str) if d_str else timezone.now().date()
        snap = services.compute_buyer_kpi_snapshot(snapshot_date=d)
        return Response({'date': str(snap.snapshot_date),
                         'new_users': snap.new_users,
                         'new_buyers': snap.new_buyers})


class AcquisitionChannelSpendListView(APIView):
    """GET /admin/channel-spend/?date=YYYY-MM-DD — paid-media spend."""
    permission_classes = [IsAdmin]

    def get(self, request):
        d_str = request.query_params.get('date')
        d = date_cls.fromisoformat(d_str) if d_str else timezone.now().date()
        rows = AcquisitionChannelSpend.objects.filter(snapshot_date=d).values(
            'channel', 'country', 'spend_usd', 'impressions',
            'clicks', 'installs', 'registrations', 'first_purchases',
        )
        return Response(list(rows))


# ─── Audit ─────────────────────────────────────────────────────

class MyEngagementEventsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = EngagementEvent.objects.filter(user=request.user).values(
            'kind', 'payload', 'created_at',
        )[:100]
        return Response(list(rows))


# ─── CH19 — Affinity / personalised home feed ─────────────────

class MyHomeFeedView(APIView):
    """GET /home-feed/me — latest personalised feed snapshot. Recomputes
    on demand if no snapshot exists yet."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import HomeFeedPersonalisation
        latest = HomeFeedPersonalisation.objects.filter(
            user=request.user,
        ).order_by('-created_at').first()
        if not latest:
            latest = services.snapshot_home_feed_for(request.user)
        return Response({
            'created_at': latest.created_at.isoformat(),
            'experiment_id': latest.experiment_id,
            'affinity_vector': latest.affinity_vector,
            'blocks_selected': latest.blocks_selected,
            'blocks_demoted': latest.blocks_demoted,
        })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def home_feed_recompute(request):
    snap = services.snapshot_home_feed_for(
        request.user,
        experiment_id=request.data.get('experiment_id', ''),
    )
    return Response({'created_at': snap.created_at.isoformat(),
                     'blocks_selected': snap.blocks_selected,
                     'price_band': snap.affinity_vector.get('price_band')})


# ─── Template render endpoint ─────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def render_template_view(request):
    """POST /templates/render  body: {key, kind, locale, context}."""
    out = services.render_template(
        key=request.data.get('key', ''),
        kind=request.data.get('kind', 'email'),
        locale=request.data.get('locale', 'pt-AO'),
        context=request.data.get('context') or {},
    )
    return Response(out)
