"""
Data & Analytics REST surface — thin views over services.py.
"""
from __future__ import annotations

from datetime import date as date_cls
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
    AbTestEvaluation, AttributionModelRun, BanditArm,
    BanditExperiment, BuyerCohort, ChurnPrediction, CohortCell,
    Customer360Profile, DataAccessGrant, DataCatalogueEntry,
    DataPlatformKpiSnapshot, DataQualityCheck, DataQualityIncident,
    DataRequestAuditLog, DeliveryPerformanceReport, EtlPipelineRun,
    FeatureDefinition, FraudLossReport, GmvDecomposition,
    MetricDefinition, PiiFieldRegistry, QueryAnalyticsRollup,
    RealtimeMetricSnapshot, ScheduledReport, SellerAnalyticsReport,
)

User = get_user_model()


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        u = getattr(request, 'user', None)
        return bool(u and u.is_authenticated and getattr(u, 'is_staff', False))


# ─── CH2 — Realtime ───────────────────────────────────────────

class RealtimeDashboardView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        rows = RealtimeMetricSnapshot.objects.order_by('-bucket_minute')[:60]
        return Response(list(rows.values(
            'bucket_minute', 'gmv', 'orders_count', 'active_users',
            'payments_succeeded',
        )))

    def post(self, request):
        snap = services.snapshot_realtime_metrics()
        return Response({'bucket': snap.bucket_minute.isoformat(),
                         'gmv': str(snap.gmv),
                         'orders': snap.orders_count})


# ─── CH3 — Seller reports ────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def seller_report_generate(request):
    target = request.user
    if request.user.is_staff and request.data.get('seller_id'):
        target = get_object_or_404(User, pk=request.data['seller_id'])
    report = services.generate_seller_report(
        seller=target,
        period=request.data.get('period', 'weekly'),
    )
    return Response({'report_id': str(report.id),
                     'metrics': report.metrics}, status=201)


# ─── CH4 — Cohorts ───────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def cohort_compute(request):
    month = date_cls.fromisoformat(request.data.get('cohort_month'))
    cohort = services.compute_cohort(cohort_month=month)
    cells = cohort.cells.values('month_offset', 'active_users', 'retention_pct')
    return Response({'cohort_size': cohort.cohort_size,
                     'cells': list(cells)})


class CohortMatrixView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        out = []
        for c in BuyerCohort.objects.order_by('-cohort_month')[:12]:
            out.append({
                'cohort_month': str(c.cohort_month),
                'size': c.cohort_size,
                'cells': list(c.cells.values('month_offset', 'retention_pct')),
            })
        return Response(out)


# ─── CH5 — GMV decomposition ─────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def gmv_decompose(request):
    obj = services.decompose_gmv(
        period_start=date_cls.fromisoformat(request.data['period_start']),
        period_end=date_cls.fromisoformat(request.data['period_end']),
    )
    return Response({
        'gmv_current': str(obj.gmv_current),
        'gmv_previous': str(obj.gmv_previous),
        'gmv_delta_pct': obj.gmv_delta_pct,
        'traffic_contribution_pct': obj.traffic_contribution_pct,
        'conversion_contribution_pct': obj.conversion_contribution_pct,
        'aov_contribution_pct': obj.aov_contribution_pct,
    })


# ─── CH6/7 — Fraud loss + delivery reports ──────────────────

@api_view(['GET'])
@permission_classes([IsAdmin])
def fraud_loss_report(request):
    d_str = request.query_params.get('date')
    d = date_cls.fromisoformat(d_str) if d_str else timezone.now().date()
    snap = FraudLossReport.objects.filter(snapshot_date=d).first()
    if not snap:
        snap = services.snapshot_fraud_loss(snapshot_date=d)
    return Response({
        'date': str(snap.snapshot_date),
        'chargeback_loss': str(snap.chargeback_loss),
        'refund_abuse_loss': str(snap.refund_abuse_loss),
        'total_loss': str(snap.total_loss),
        'loss_rate_bps': snap.loss_rate_bps,
    })


@api_view(['GET'])
@permission_classes([IsAdmin])
def delivery_performance_report(request):
    d_str = request.query_params.get('date')
    d = date_cls.fromisoformat(d_str) if d_str else timezone.now().date()
    snap = DeliveryPerformanceReport.objects.filter(snapshot_date=d).first()
    if not snap:
        snap = services.snapshot_delivery_performance(snapshot_date=d)
    return Response({
        'date': str(snap.snapshot_date),
        'shipments_delivered': snap.shipments_delivered,
        'avg_transit_days': snap.avg_transit_days,
        'p50': snap.p50_transit_days, 'p90': snap.p90_transit_days,
        'on_time_pct': snap.on_time_pct,
        'by_carrier': snap.by_carrier,
    })


# ─── CH8 — Query analytics ───────────────────────────────────

class QueryAnalyticsView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        d_str = request.query_params.get('date')
        d = date_cls.fromisoformat(d_str) if d_str else timezone.now().date()
        rows = QueryAnalyticsRollup.objects.filter(
            snapshot_date=d,
        ).order_by('-search_count').values(
            'query', 'search_count', 'zero_results_count',
            'clicks', 'ctr', 'conversions', 'avg_click_position',
        )[:100]
        return Response(list(rows))

    def post(self, request):
        return Response({'rows': services.rollup_query_analytics()})


# ─── CH9 — A/B evaluation ────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def ab_evaluate(request):
    ev = services.evaluate_ab_test(
        experiment_slug=request.data.get('experiment_slug', ''),
        metric=request.data.get('metric', 'ctr'),
        control_n=int(request.data.get('control_n', 0)),
        control_mean=float(request.data.get('control_mean', 0)),
        control_variance=float(request.data.get('control_variance', 0)),
        variant_n=int(request.data.get('variant_n', 0)),
        variant_mean=float(request.data.get('variant_mean', 0)),
        variant_variance=float(request.data.get('variant_variance', 0)),
        cuped_covariate_corr=float(request.data.get('cuped_covariate_corr', 0)),
    )
    return Response({
        'lift_pct': ev.lift_pct, 'z_score': ev.z_score,
        'p_value': ev.p_value, 'significant': ev.significant,
        'cuped_variance_reduction_pct': ev.cuped_variance_reduction_pct,
        'recommendation': ev.recommendation,
    }, status=201)


# ─── CH10 — ETL ──────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def etl_start(request):
    run = services.start_etl_run(
        pipeline_name=request.data.get('pipeline_name', ''),
        run_kind=request.data.get('run_kind', 'incremental'),
    )
    return Response({'run_id': str(run.id)}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def etl_finish(request):
    run = get_object_or_404(EtlPipelineRun, pk=request.data.get('run_id'))
    services.finish_etl_run(
        run,
        rows_extracted=int(request.data.get('rows_extracted', 0)),
        rows_loaded=int(request.data.get('rows_loaded', 0)),
        rows_failed=int(request.data.get('rows_failed', 0)),
        error=request.data.get('error', ''),
    )
    return Response({'status': run.status})


# ─── CH11 — Semantic layer ───────────────────────────────────

class MetricDefinitionView(generics.ListCreateAPIView):
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return MetricDefinition.objects.all()

    def list(self, request):
        return Response(list(self.get_queryset().values()))

    def create(self, request):
        obj, _ = MetricDefinition.objects.update_or_create(
            code=request.data.get('code', '')[:40],
            defaults={
                'display_name': request.data.get('display_name', '')[:120],
                'description': request.data.get('description', ''),
                'sql_expression': request.data.get('sql_expression', ''),
                'grain': request.data.get('grain', 'daily'),
                'owner_team': request.data.get('owner_team', '')[:64],
                'unit': request.data.get('unit', '')[:20],
                'is_certified': bool(request.data.get('is_certified', False)),
            },
        )
        return Response({'code': obj.code}, status=201)


# ─── CH12 — GDPR audit ───────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def gdpr_audit_log(request):
    obj = DataRequestAuditLog.objects.create(
        request_id=request.data.get('request_id', '')[:64],
        request_kind=request.data.get('request_kind', 'access'),
        step=request.data.get('step', '')[:40],
        actor=request.user,
        systems_touched=request.data.get('systems_touched') or [],
        detail=request.data.get('detail') or {},
    )
    return Response({'log_id': obj.pk}, status=201)


# ─── CH13 — Churn ────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def churn_predict(request):
    user = get_object_or_404(User, pk=request.data.get('user_id'))
    pred = services.predict_churn(user)
    return Response({
        'churn_probability': pred.churn_probability,
        'risk_band': pred.risk_band,
        'top_factors': pred.top_factors,
        'intervention_recommended': pred.intervention_recommended,
    }, status=201)


# ─── CH15 — Attribution ──────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def attribution_run(request):
    run = services.run_attribution_model(
        model=request.data.get('model', 'linear'),
        window_start=date_cls.fromisoformat(request.data['window_start']),
        window_end=date_cls.fromisoformat(request.data['window_end']),
    )
    return Response({
        'total_conversions': run.total_conversions,
        'channel_credits': run.channel_credits,
    }, status=201)


# ─── CH16 — Catalogue ────────────────────────────────────────

class DataCatalogueView(generics.ListCreateAPIView):
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return DataCatalogueEntry.objects.all()

    def list(self, request):
        return Response(list(self.get_queryset().values(
            'dataset_name', 'layer', 'owner_team',
            'pii_classification', 'retention_days',
        )[:200]))

    def create(self, request):
        obj, _ = DataCatalogueEntry.objects.update_or_create(
            dataset_name=request.data.get('dataset_name', '')[:160],
            defaults={
                'layer': request.data.get('layer', 'operational'),
                'description': request.data.get('description', ''),
                'owner_team': request.data.get('owner_team', '')[:64],
                'pii_classification': request.data.get('pii_classification', 'none'),
                'retention_days': int(request.data.get('retention_days', 365)),
                'upstream_datasets': request.data.get('upstream_datasets') or [],
                'schema_fields': request.data.get('schema_fields') or [],
            },
        )
        return Response({'dataset_name': obj.dataset_name}, status=201)


# ─── CH17 — Data quality ─────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def dq_check_create(request):
    obj = DataQualityCheck.objects.create(
        dataset_name=request.data.get('dataset_name', '')[:160],
        check_kind=request.data.get('check_kind', 'row_count_anomaly'),
        config=request.data.get('config') or {},
    )
    return Response({'check_id': obj.pk}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def dq_run_all(request):
    return Response(services.run_dq_checks())


# ─── CH18 — Access grants ────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def access_grant(request):
    grantee = get_object_or_404(User, pk=request.data.get('grantee_id'))
    from datetime import timedelta as _td
    obj = DataAccessGrant.objects.create(
        grantee=grantee,
        dataset_name=request.data.get('dataset_name', '')[:160],
        access_level=request.data.get('access_level', 'read'),
        justification=request.data.get('justification', ''),
        approved_by=request.user,
        expires_at=timezone.now() + _td(days=int(request.data.get('ttl_days', 90))),
    )
    return Response({'grant_id': str(obj.id),
                     'expires_at': obj.expires_at.isoformat()}, status=201)


# ─── CH19 — PII registry ─────────────────────────────────────

class PiiRegistryView(generics.ListCreateAPIView):
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return PiiFieldRegistry.objects.all()

    def list(self, request):
        return Response(list(self.get_queryset().values()[:300]))

    def create(self, request):
        obj, _ = PiiFieldRegistry.objects.update_or_create(
            dataset_name=request.data.get('dataset_name', '')[:160],
            field_name=request.data.get('field_name', '')[:120],
            defaults={
                'pii_kind': request.data.get('pii_kind', 'email'),
                'masking_strategy': request.data.get('masking_strategy', 'hash'),
                'encrypted_at_rest': bool(request.data.get('encrypted_at_rest', False)),
            },
        )
        return Response({'id': obj.pk}, status=201)


# ─── CH21 — Feature store ────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def feature_define(request):
    obj, _ = FeatureDefinition.objects.update_or_create(
        code=request.data.get('code', '')[:64],
        defaults={
            'description': request.data.get('description', ''),
            'entity': request.data.get('entity', 'user'),
            'dtype': request.data.get('dtype', 'float'),
            'freshness_sla_minutes': int(request.data.get('freshness_sla_minutes', 1440)),
            'owner_team': request.data.get('owner_team', '')[:64],
        },
    )
    return Response({'code': obj.code}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def feature_write(request):
    obj = services.write_feature(
        feature_code=request.data.get('feature_code', ''),
        entity_id=request.data.get('entity_id', ''),
        value=request.data.get('value'),
    )
    return Response({'id': obj.pk}, status=201)


@api_view(['GET'])
@permission_classes([IsAdmin])
def feature_read(request):
    return Response(services.read_features(
        entity_id=request.query_params.get('entity_id', ''),
        feature_codes=(request.query_params.get('codes') or '').split(','),
    ))


# ─── CH22 — Bandit ───────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def bandit_create(request):
    exp = BanditExperiment.objects.create(
        slug=request.data.get('slug', '')[:80],
        name=request.data.get('name', '')[:160],
        algorithm=request.data.get('algorithm', 'thompson'),
        epsilon=float(request.data.get('epsilon', 0.1)),
    )
    for arm_key in (request.data.get('arms') or []):
        BanditArm.objects.create(experiment=exp, arm_key=str(arm_key)[:64])
    return Response({'experiment_id': str(exp.id)}, status=201)


@api_view(['POST'])
@permission_classes([AllowAny])
def bandit_select(request):
    exp = get_object_or_404(BanditExperiment, slug=request.data.get('slug', ''))
    try:
        arm = services.bandit_select_arm(exp)
    except ValueError as e:
        return Response({'code': str(e)}, status=422)
    return Response({'arm_key': arm.arm_key, 'arm_id': arm.pk})


@api_view(['POST'])
@permission_classes([AllowAny])
def bandit_reward(request):
    arm = get_object_or_404(BanditArm, pk=request.data.get('arm_id'))
    services.bandit_record_outcome(arm, rewarded=bool(request.data.get('rewarded', False)))
    return Response({'pulls': arm.pulls, 'rewards': arm.rewards})


# ─── CH23 — Customer 360 ─────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAdmin])
def c360_profile(request):
    user = get_object_or_404(User, pk=request.query_params.get('user_id'))
    profile = services.refresh_c360(user)
    return Response({
        'user_id': user.pk,
        'lifetime_orders': profile.lifetime_orders,
        'lifetime_gmv': str(profile.lifetime_gmv),
        'avg_order_value': str(profile.avg_order_value),
        'ltv_segment': profile.ltv_segment,
        'dormancy_band': profile.dormancy_band,
        'churn_risk_band': profile.churn_risk_band,
        'trust_band': profile.trust_band,
        'open_tickets': profile.open_tickets,
        'device_count': profile.device_count,
        'refreshed_at': profile.refreshed_at.isoformat(),
    })


# ─── CH24 — KPI ──────────────────────────────────────────────

class PlatformKpiView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        d_str = request.query_params.get('date')
        d = date_cls.fromisoformat(d_str) if d_str else timezone.now().date()
        snap = DataPlatformKpiSnapshot.objects.filter(snapshot_date=d).first()
        if not snap:
            snap = services.snapshot_platform_kpis(snapshot_date=d)
        return Response({
            'date': str(snap.snapshot_date),
            'etl_runs': snap.etl_runs,
            'etl_success_pct': snap.etl_success_pct,
            'dq_checks_run': snap.dq_checks_run,
            'dq_pass_pct': snap.dq_pass_pct,
            'dq_open_incidents': snap.dq_open_incidents,
            'feature_count': snap.feature_count,
            'stale_features': snap.stale_features,
            'catalogued_datasets': snap.catalogued_datasets,
            'pii_fields_registered': snap.pii_fields_registered,
            'active_experiments': snap.active_experiments,
            'gdpr_requests_open': snap.gdpr_requests_open,
            'c360_profiles': snap.c360_profiles,
        })
