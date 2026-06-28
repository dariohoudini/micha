"""
Extended REST endpoints for the remaining seller-onboarding flows.
Imported from urls.py alongside views.py — kept separate so views.py
stays focused on the core CH1–CH16 funnel.
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
    AcquisitionFunnelSnapshot, ChoiceEnrolment, ChoiceWarehouse,
    FeeRebate, OfficialBrandStoreApplication, SellerApiAuthorisation,
    SellerApiKey, SellerBrand, SellerDeregistrationRequest,
    SellerEmailLog, SellerOnboardingEvent, SellerStoreType,
    SellerWebhookDelivery, SellerWebhookEndpoint,
)


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        u = getattr(request, 'user', None)
        return bool(u and u.is_authenticated and getattr(u, 'is_staff', False))


# ───── CH6 — Email drip & log ────────────────────────────────────

class EmailLogListView(generics.ListAPIView):
    """GET /emails/me — seller can audit which onboarding emails fired
    for them and which were suppressed (and why)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = SellerEmailLog.objects.filter(seller=request.user).values(
            'sequence_key', 'subject', 'status', 'suppression_reason',
            'queued_at', 'sent_at', 'opened_at', 'clicked_at',
        )[:200]
        return Response(list(qs))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def trigger_transactional_email(request):
    """POST /emails/transactional  body: {sequence_key, context} — used
    by other apps (orders/disputes) to fire behaviour-triggered
    emails per CH6.2 without coupling them to this app's internals."""
    key = request.data.get('sequence_key')
    if not key:
        return Response({'detail': 'sequence_key required'}, status=400)
    log = services.enqueue_email(
        seller=request.user, sequence_key=key,
        context=request.data.get('context') or {},
        force=True,
    )
    if not log:
        return Response({'queued': False}, status=200)
    return Response({'queued': True, 'log_id': log.pk, 'status': log.status})


# ───── CH13 — Store types ────────────────────────────────────────

class MyStoreTypeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        state = services.recompute_store_type(request.user)
        live = SellerStoreType.objects.filter(seller=request.user).first()
        return Response({
            'computed': state,
            'persisted': {
                'store_type': live.store_type,
                'search_multiplier': live.search_multiplier,
                'badge_label': live.badge_label,
                'is_pinned': live.is_pinned,
                'updated_at': live.updated_at.isoformat(),
            } if live else None,
        })


class OfficialBrandStoreApplyView(APIView):
    """POST /store-types/official-brand/apply  body:
    {brand_id, banner_key, logo_key, featured_product_ids}."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        brand_id = request.data.get('brand_id')
        brand = get_object_or_404(SellerBrand, pk=brand_id, seller=request.user)
        gate = services.can_apply_official_brand(request.user, brand)
        if not gate['ok']:
            return Response(gate, status=422)
        # Block duplicates.
        if OfficialBrandStoreApplication.objects.filter(
            seller=request.user, brand=brand,
            status__in=('pending', 'approved'),
        ).exists():
            return Response({'detail': 'pending or approved already exists'},
                            status=409)
        obj = OfficialBrandStoreApplication.objects.create(
            seller=request.user, brand=brand,
            banner_key=request.data.get('banner_key', ''),
            logo_key=request.data.get('logo_key', ''),
            featured_product_ids=request.data.get('featured_product_ids') or [],
            metrics_snapshot=gate,
        )
        SellerOnboardingEvent.log(
            seller=request.user, kind='official_brand.application_received',
            payload={'application_id': str(obj.id),
                     'brand_id': str(brand.id)},
        )
        return Response({'application_id': str(obj.id)}, status=201)


# ───── CH17 — GMV rebate ─────────────────────────────────────────

class MyRebatesView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = FeeRebate.objects.filter(seller=request.user).values(
            'id', 'fee_period_start', 'fee_period_end', 'gmv_usd',
            'rebate_pct', 'rebate_amount', 'currency', 'status',
            'credited_at', 'payment_reference',
        )[:50]
        return Response(list(rows))


@api_view(['POST'])
@permission_classes([IsAdmin])
def compute_rebate(request):
    """POST /admin/rebates/compute body:
    {seller_id, period_start, period_end}."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    seller = get_object_or_404(User, pk=request.data.get('seller_id'))
    period_start = date_cls.fromisoformat(request.data['period_start'])
    period_end = date_cls.fromisoformat(request.data['period_end'])
    result = services.compute_gmv_rebate(
        seller, period_start=period_start, period_end=period_end,
    )
    return Response(result)


# ───── CH19 — API keys + apps + webhooks ────────────────────────

class ApiKeyListCreateView(APIView):
    """GET /api-keys — list (without secrets).
    POST /api-keys  body: {label, ttl_days} — returns the secret ONCE."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = SellerApiKey.objects.filter(seller=request.user).values(
            'id', 'label', 'key_prefix', 'is_active',
            'last_used_at', 'request_count', 'rate_limit_per_hour',
            'expires_at', 'revoked_at', 'created_at',
        )
        return Response(list(rows))

    def post(self, request):
        result = services.issue_api_key(
            seller=request.user,
            label=(request.data.get('label') or 'api-key')[:80],
            ttl_days=int(request.data.get('ttl_days') or 365),
            rate_limit=int(request.data.get('rate_limit') or 1000),
        )
        return Response(result, status=201)


class ApiKeyRevokeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        key = get_object_or_404(SellerApiKey, pk=pk, seller=request.user)
        services.revoke_api_key(key_id=key.id, actor=request.user)
        return Response({'detail': 'revoked'})


class WebhookEndpointListCreateView(APIView):
    """GET /webhooks — list.  POST  body: {url, events} — returns
    the HMAC secret ONCE."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = SellerWebhookEndpoint.objects.filter(
            seller=request.user,
        ).values('id', 'url', 'events', 'is_active',
                 'consecutive_failures', 'disabled_at', 'created_at')
        return Response(list(rows))

    def post(self, request):
        result = services.register_webhook(
            seller=request.user,
            url=request.data.get('url') or '',
            events=request.data.get('events') or [],
        )
        return Response(result, status=201)


class WebhookEndpointDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        ep = get_object_or_404(
            SellerWebhookEndpoint, pk=pk, seller=request.user,
        )
        ep.is_active = False
        ep.disabled_at = timezone.now()
        ep.save(update_fields=['is_active', 'disabled_at'])
        return Response({'detail': 'disabled'})


class WebhookDeliveryListView(APIView):
    """GET /webhooks/<id>/deliveries — recent attempts (for debug)."""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        ep = get_object_or_404(
            SellerWebhookEndpoint, pk=pk, seller=request.user,
        )
        rows = SellerWebhookDelivery.objects.filter(endpoint=ep).values(
            'id', 'event_type', 'attempt', 'response_status',
            'delivered_at', 'failed_reason', 'created_at',
        )[:100]
        return Response(list(rows))


# ───── CH21 — Voluntary deregistration ───────────────────────────

class DeregistrationView(APIView):
    """POST /deregistration  → opens a request.
    DELETE /deregistration  → cancels during cooling-off.
    GET /deregistration   → current state."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        req = SellerDeregistrationRequest.objects.filter(
            seller=request.user,
        ).order_by('-requested_at').first()
        if not req:
            return Response({'state': 'none'})
        return Response({
            'state': req.status,
            'request_id': str(req.id),
            'requested_at': req.requested_at.isoformat(),
            'effective_at': req.effective_at.isoformat(),
            'cancelled_at': req.cancelled_at and req.cancelled_at.isoformat(),
            'completed_at': req.completed_at and req.completed_at.isoformat(),
            'eligibility_gate': req.eligibility_gate,
            'blocked_reason': req.blocked_reason,
        })

    def post(self, request):
        result = services.request_deregistration(seller=request.user)
        return Response(result, status=201 if result['ok'] else 422)

    def delete(self, request):
        ok = services.cancel_deregistration(request.user)
        return Response({'cancelled': ok}, status=200 if ok else 404)


# ───── CH22 — Choice ─────────────────────────────────────────────

class ChoiceEligibilityView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(services.choice_eligibility(request.user))


class ChoiceApplyView(APIView):
    """POST /choice/apply  body:
    {warehouse_code, product_ids[], estimated_monthly_units, supplier_lead_time_days}."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        result = services.apply_to_choice(
            seller=request.user,
            warehouse_code=request.data.get('warehouse_code', ''),
            product_ids=request.data.get('product_ids') or [],
            estimated_monthly_units=int(request.data.get('estimated_monthly_units') or 0),
            supplier_lead_time_days=int(request.data.get('supplier_lead_time_days') or 0),
        )
        return Response(result, status=201 if result.get('ok') else 422)


class MyChoiceEnrolmentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = ChoiceEnrolment.objects.filter(seller=request.user).values(
            'id', 'warehouse_id', 'product_ids', 'status',
            'estimated_monthly_units', 'inbound_deadline',
            'activated_at', 'created_at',
        )
        return Response(list(rows))


# ───── CH24 — Acquisition KPI ────────────────────────────────────

class FunnelSnapshotView(APIView):
    """GET /admin/funnel/?date=YYYY-MM-DD — returns the snapshot row.
    POST /admin/funnel/snapshot — recompute now and return."""
    permission_classes = [IsAdmin]

    def get(self, request):
        d_str = request.query_params.get('date')
        d = date_cls.fromisoformat(d_str) if d_str else timezone.now().date()
        snap = AcquisitionFunnelSnapshot.objects.filter(snapshot_date=d).first()
        if not snap:
            services.compute_funnel_snapshot(date=d)
            snap = AcquisitionFunnelSnapshot.objects.filter(snapshot_date=d).first()
        return Response({
            'date': str(snap.snapshot_date),
            'leads_submitted': snap.leads_submitted,
            'leads_qualified': snap.leads_qualified,
            'applications_started': snap.applications_started,
            'applications_submitted': snap.applications_submitted,
            'kyc_approved': snap.kyc_approved,
            'activated': snap.activated,
            'first_listing_within_7d': snap.first_listing_within_7d,
            'first_sale_within_30d': snap.first_sale_within_30d,
            'retained_at_90d': snap.retained_at_90d,
            'by_country': snap.by_country,
            'by_lead_source': snap.by_lead_source,
            'by_tier': snap.by_tier,
        })

    def post(self, request):
        d_str = request.data.get('date')
        d = date_cls.fromisoformat(d_str) if d_str else timezone.now().date()
        return Response(services.compute_funnel_snapshot(date=d))
