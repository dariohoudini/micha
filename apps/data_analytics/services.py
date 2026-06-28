"""
Data & Analytics Platform — domain services.
"""
from __future__ import annotations

import hashlib
import logging
import math
import random
from datetime import date as date_cls
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models as django_models
from django.utils import timezone

from .models import (
    AbTestEvaluation, AttributionModelRun, BanditArm,
    BanditExperiment, BuyerCohort, ChurnPrediction, CohortCell,
    ConsumerGroupLag, Customer360Profile, DataAccessGrant,
    DataAnalyticsEvent, DataCatalogueEntry, DataGovernancePolicy,
    DataPlatformKpiSnapshot, DataQualityCheck, DataQualityIncident,
    DataRequestAuditLog, DeliveryPerformanceReport, EtlPipelineRun,
    EtlTableSync, EventStreamTopic, FeatureDefinition, FeatureValue,
    FeatureUsageRollup, FraudLossReport, GmvDecomposition,
    MetricDefinition, PiiFieldRegistry, QueryAnalyticsRollup,
    RealtimeMetricSnapshot, ScheduledReport, SellerAnalyticsReport,
)

User = get_user_model()
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# CH2 — Realtime metrics
# ═══════════════════════════════════════════════════════════════════

def snapshot_realtime_metrics() -> RealtimeMetricSnapshot:
    """Per-minute live roll-up. Production = Flink; dev = direct
    queries over the last minute of operational tables."""
    now = timezone.now().replace(second=0, microsecond=0)
    start = now - timedelta(minutes=1)
    gmv = Decimal('0')
    orders = 0
    payments = 0
    try:
        from apps.orders.models import Order
        qs = Order.objects.filter(created_at__gte=start, created_at__lt=now)
        orders = qs.count()
        gmv = Decimal(str(qs.aggregate(s=django_models.Sum('total_amount'))['s'] or 0))
    except Exception:
        pass
    try:
        from apps.payment_gateways.models import PaymentIntent
        payments = PaymentIntent.objects.filter(
            completed_at__gte=start, completed_at__lt=now,
            status='succeeded',
        ).count()
    except Exception:
        pass
    active = 0
    try:
        from apps.analytics.models import UserEvent
        active = (
            UserEvent.objects.filter(created_at__gte=start, created_at__lt=now)
            .values('user').distinct().count()
        )
    except Exception:
        pass
    obj, _ = RealtimeMetricSnapshot.objects.update_or_create(
        bucket_minute=start,
        defaults={
            'gmv': gmv, 'orders_count': orders,
            'active_users': active,
            'payments_succeeded': payments,
        },
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH3 — Seller report
# ═══════════════════════════════════════════════════════════════════

def generate_seller_report(*, seller, period: str = 'weekly',
                              period_start: date_cls = None) -> SellerAnalyticsReport:
    if period_start is None:
        today = timezone.now().date()
        period_start = today - timedelta(days=today.weekday() + 7)
    span = {'daily': 1, 'weekly': 7, 'monthly': 30}.get(period, 7)
    period_end = period_start + timedelta(days=span - 1)
    existing = SellerAnalyticsReport.objects.filter(
        seller=seller, period=period, period_start=period_start,
    ).first()
    if existing:
        return existing

    metrics: dict = {'orders': 0, 'gmv': '0', 'aov': '0',
                      'refunds': 0, 'new_buyers': 0}
    try:
        from apps.orders.models import Order
        qs = Order.objects.filter(
            items__product__store__owner=seller,
            created_at__date__gte=period_start,
            created_at__date__lte=period_end,
        ).distinct()
        n = qs.count()
        gmv = Decimal(str(qs.aggregate(s=django_models.Sum('total_amount'))['s'] or 0))
        metrics['orders'] = n
        metrics['gmv'] = str(gmv)
        metrics['aov'] = str((gmv / n).quantize(Decimal('0.01'))) if n else '0'
    except Exception:
        pass

    report = SellerAnalyticsReport.objects.create(
        seller=seller, period=period,
        period_start=period_start, period_end=period_end,
        metrics=metrics,
    )
    DataAnalyticsEvent.log(kind='seller_report.generated',
                            payload={'seller_id': seller.pk,
                                     'period': period})
    return report


# ═══════════════════════════════════════════════════════════════════
# CH4 — Cohorts
# ═══════════════════════════════════════════════════════════════════

def compute_cohort(*, cohort_month: date_cls,
                     max_offset: int = 6) -> BuyerCohort:
    """Builds the retention matrix for one acquisition month."""
    cohort_month = cohort_month.replace(day=1)
    month_end = (cohort_month + timedelta(days=32)).replace(day=1)
    members = list(
        User.objects.filter(
            date_joined__date__gte=cohort_month,
            date_joined__date__lt=month_end,
        ).values_list('pk', flat=True)
    )
    cohort, _ = BuyerCohort.objects.update_or_create(
        cohort_month=cohort_month,
        defaults={'cohort_size': len(members)},
    )
    if not members:
        return cohort
    try:
        from apps.orders.models import Order
        for offset in range(max_offset + 1):
            m_start = (cohort_month + timedelta(days=32 * offset)).replace(day=1)
            m_end = (m_start + timedelta(days=32)).replace(day=1)
            # NOTE: Order's buyer FK is named `buyer`, NOT `user`.
            active = (
                Order.objects.filter(
                    buyer_id__in=members,
                    created_at__date__gte=m_start,
                    created_at__date__lt=m_end,
                ).values('buyer').distinct().count()
            )
            CohortCell.objects.update_or_create(
                cohort=cohort, month_offset=offset,
                defaults={
                    'active_users': active,
                    'retention_pct': active / len(members) * 100,
                },
            )
    except Exception:
        pass
    return cohort


# ═══════════════════════════════════════════════════════════════════
# CH5 — GMV decomposition
# ═══════════════════════════════════════════════════════════════════

def decompose_gmv(*, period_start: date_cls,
                    period_end: date_cls) -> GmvDecomposition:
    """GMV = traffic × conversion × AOV.
    Contribution of each driver to the delta via log decomposition."""
    span = (period_end - period_start).days + 1
    prev_start = period_start - timedelta(days=span)
    prev_end = period_start - timedelta(days=1)

    def _stats(s, e):
        gmv = Decimal('0'); orders = 0; sessions = 1
        try:
            from apps.orders.models import Order
            qs = Order.objects.filter(created_at__date__gte=s,
                                       created_at__date__lte=e)
            orders = qs.count()
            gmv = Decimal(str(qs.aggregate(x=django_models.Sum('total_amount'))['x'] or 0))
        except Exception:
            pass
        try:
            from apps.analytics.models import UserEvent
            sessions = max(1, UserEvent.objects.filter(
                created_at__date__gte=s, created_at__date__lte=e,
                event_type='app.open',
            ).count())
        except Exception:
            sessions = max(1, orders * 10)
        return gmv, orders, sessions

    gmv_c, orders_c, sess_c = _stats(period_start, period_end)
    gmv_p, orders_p, sess_p = _stats(prev_start, prev_end)

    delta_pct = float((gmv_c - gmv_p) / gmv_p * 100) if gmv_p > 0 else 0.0

    # Log decomposition: ln(GMV ratio) = ln(traffic ratio) +
    # ln(conv ratio) + ln(AOV ratio). Contributions normalised.
    contrib = {'traffic': 0.0, 'conversion': 0.0, 'aov': 0.0}
    try:
        if gmv_p > 0 and gmv_c > 0:
            conv_c = orders_c / sess_c
            conv_p = max(1e-9, orders_p / sess_p)
            aov_c = float(gmv_c) / max(orders_c, 1)
            aov_p = float(gmv_p) / max(orders_p, 1)
            l_total = math.log(float(gmv_c) / float(gmv_p))
            if abs(l_total) > 1e-9:
                contrib['traffic'] = math.log(sess_c / sess_p) / l_total * 100
                contrib['conversion'] = math.log(conv_c / conv_p) / l_total * 100
                contrib['aov'] = math.log(aov_c / aov_p) / l_total * 100
    except Exception:
        pass

    obj, _ = GmvDecomposition.objects.update_or_create(
        period_start=period_start, period_end=period_end,
        defaults={
            'gmv_current': gmv_c, 'gmv_previous': gmv_p,
            'gmv_delta_pct': delta_pct,
            'traffic_contribution_pct': contrib['traffic'],
            'conversion_contribution_pct': contrib['conversion'],
            'aov_contribution_pct': contrib['aov'],
        },
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH6 — Fraud loss
# ═══════════════════════════════════════════════════════════════════

def snapshot_fraud_loss(snapshot_date: date_cls = None) -> FraudLossReport:
    if snapshot_date is None:
        snapshot_date = timezone.now().date()
    start = timezone.make_aware(
        timezone.datetime.combine(snapshot_date, timezone.datetime.min.time())
    )
    end = start + timedelta(days=1)
    cb = disp = Decimal('0')
    try:
        from apps.payments.models import Chargeback
        cb = Decimal(str(
            Chargeback.objects.filter(created_at__gte=start, created_at__lt=end)
            .aggregate(s=django_models.Sum('amount'))['s'] or 0
        ))
    except Exception:
        pass
    refund_abuse = Decimal('0')
    try:
        from apps.trust_safety.models import RefundFarmingCase
        refund_abuse = Decimal(str(
            RefundFarmingCase.objects.filter(
                detected_at__gte=start, detected_at__lt=end,
            ).aggregate(s=django_models.Sum('total_refund_amount'))['s'] or 0
        ))
    except Exception:
        pass
    total = cb + disp + refund_abuse
    obj, _ = FraudLossReport.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'chargeback_loss': cb, 'dispute_loss': disp,
            'refund_abuse_loss': refund_abuse,
            'total_loss': total,
        },
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH7 — Delivery performance
# ═══════════════════════════════════════════════════════════════════

def snapshot_delivery_performance(snapshot_date: date_cls = None) -> DeliveryPerformanceReport:
    if snapshot_date is None:
        snapshot_date = timezone.now().date()
    start = timezone.make_aware(
        timezone.datetime.combine(snapshot_date, timezone.datetime.min.time())
    )
    end = start + timedelta(days=1)
    delivered = 0
    transit_days: list[float] = []
    by_carrier: dict = {}
    try:
        from apps.logistics_ops.models import TrackingStatusUnified, ShippingLabel
        qs = TrackingStatusUnified.objects.filter(
            delivered_at__gte=start, delivered_at__lt=end,
        )
        delivered = qs.count()
        for t in qs:
            lbl = ShippingLabel.objects.filter(tracking_number=t.tracking_number).first()
            if lbl:
                d = (t.delivered_at - lbl.created_at).total_seconds() / 86400
                transit_days.append(d)
                by_carrier[lbl.carrier_id] = by_carrier.get(lbl.carrier_id, 0) + 1
    except Exception:
        pass
    transit_days.sort()
    n = len(transit_days)
    avg = sum(transit_days) / n if n else 0
    p50 = transit_days[n // 2] if n else 0
    p90 = transit_days[int(n * 0.9)] if n else 0
    on_time = sum(1 for d in transit_days if d <= 10)
    obj, _ = DeliveryPerformanceReport.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'shipments_delivered': delivered,
            'avg_transit_days': avg, 'p50_transit_days': p50,
            'p90_transit_days': p90,
            'on_time_pct': (on_time / n * 100) if n else 0,
            'by_carrier': by_carrier,
        },
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH8 — Per-query rollup
# ═══════════════════════════════════════════════════════════════════

def rollup_query_analytics(snapshot_date: date_cls = None) -> int:
    if snapshot_date is None:
        snapshot_date = timezone.now().date()
    start = timezone.make_aware(
        timezone.datetime.combine(snapshot_date, timezone.datetime.min.time())
    )
    end = start + timedelta(days=1)
    n = 0
    try:
        from apps.search_discovery.models import SearchClickLog, ZeroResultsLog
        impressions = (
            SearchClickLog.objects.filter(
                occurred_at__gte=start, occurred_at__lt=end,
            ).values('query').annotate(
                imp=django_models.Count('id', filter=django_models.Q(action='impression')),
                clk=django_models.Count('id', filter=django_models.Q(action='click')),
                conv=django_models.Count('id', filter=django_models.Q(action='purchase')),
                pos=django_models.Avg('position', filter=django_models.Q(action='click')),
            )
        )
        zero_by_q = dict(
            ZeroResultsLog.objects.filter(
                occurred_at__gte=start, occurred_at__lt=end,
            ).values_list('query').annotate(c=django_models.Count('id'))
        )
        for row in impressions:
            QueryAnalyticsRollup.objects.update_or_create(
                snapshot_date=snapshot_date, query=row['query'],
                defaults={
                    'search_count': row['imp'] or 0,
                    'clicks': row['clk'] or 0,
                    'ctr': (row['clk'] / row['imp'] * 100) if row['imp'] else 0,
                    'conversions': row['conv'] or 0,
                    'avg_click_position': row['pos'] or 0,
                    'zero_results_count': zero_by_q.get(row['query'], 0),
                },
            )
            n += 1
    except Exception as e:
        log.exception('query rollup failed: %s', e)
    return n


# ═══════════════════════════════════════════════════════════════════
# CH9 — A/B significance + CUPED
# ═══════════════════════════════════════════════════════════════════

def _norm_sf(z: float) -> float:
    """Survival function of the standard normal (1 - CDF) via erfc."""
    return 0.5 * math.erfc(z / math.sqrt(2))


def evaluate_ab_test(*, experiment_slug: str, metric: str = 'ctr',
                       control_n: int, control_mean: float,
                       control_variance: float,
                       variant_n: int, variant_mean: float,
                       variant_variance: float,
                       cuped_covariate_corr: float = 0.0,
                       alpha: float = 0.05) -> AbTestEvaluation:
    """Two-sample z-test + optional CUPED variance reduction.
    CUPED: var_adjusted = var × (1 - ρ²) where ρ = pre-period
    covariate correlation."""
    cuped_applied = abs(cuped_covariate_corr) > 0.01
    reduction = 0.0
    cv = control_variance
    vv = variant_variance
    if cuped_applied:
        factor = 1 - cuped_covariate_corr ** 2
        cv *= factor
        vv *= factor
        reduction = (1 - factor) * 100

    se = math.sqrt(
        (cv / max(control_n, 1)) + (vv / max(variant_n, 1)),
    ) or 1e-12
    z = (variant_mean - control_mean) / se
    p = 2 * _norm_sf(abs(z))
    significant = p < alpha
    lift = ((variant_mean - control_mean) / control_mean * 100) if control_mean else 0

    if significant and lift > 0:
        rec = 'ship_variant'
    elif significant and lift < 0:
        rec = 'keep_control'
    elif control_n + variant_n > 100000:
        rec = 'inconclusive'
    else:
        rec = 'continue'

    return AbTestEvaluation.objects.create(
        experiment_slug=experiment_slug[:80], metric=metric[:40],
        control_n=control_n, control_mean=control_mean,
        control_variance=control_variance,
        variant_n=variant_n, variant_mean=variant_mean,
        variant_variance=variant_variance,
        lift_pct=lift, z_score=z, p_value=p,
        significant=significant,
        cuped_applied=cuped_applied,
        cuped_variance_reduction_pct=reduction,
        recommendation=rec,
    )


# ═══════════════════════════════════════════════════════════════════
# CH10 — ETL
# ═══════════════════════════════════════════════════════════════════

def start_etl_run(*, pipeline_name: str,
                    run_kind: str = 'incremental') -> EtlPipelineRun:
    return EtlPipelineRun.objects.create(
        pipeline_name=pipeline_name[:80], run_kind=run_kind,
    )


def finish_etl_run(run: EtlPipelineRun, *, rows_extracted: int,
                     rows_loaded: int, rows_failed: int = 0,
                     error: str = '') -> EtlPipelineRun:
    run.rows_extracted = rows_extracted
    run.rows_loaded = rows_loaded
    run.rows_failed = rows_failed
    run.finished_at = timezone.now()
    if error:
        run.status = 'failed'
        run.error_message = error[:5000]
    elif rows_failed:
        run.status = 'partial'
    else:
        run.status = 'success'
    run.save()
    return run


def advance_watermark(*, source_table: str, watermark: str) -> EtlTableSync:
    obj, _ = EtlTableSync.objects.update_or_create(
        source_table=source_table[:120],
        defaults={'last_watermark': watermark[:64],
                   'last_synced_at': timezone.now()},
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH13 — Churn prediction
# ═══════════════════════════════════════════════════════════════════

def predict_churn(user, *, snapshot_date: date_cls = None) -> ChurnPrediction:
    """Heuristic churn model. Production swaps a trained model — the
    interface (probability + factors) stays the same."""
    if snapshot_date is None:
        snapshot_date = timezone.now().date()
    factors = []
    prob = 0.2
    try:
        from apps.buyer_engagement.models import DormancyState
        dorm = DormancyState.objects.filter(user=user).first()
        if dorm:
            days = dorm.days_since_last_purchase
            if days > 365:
                prob += 0.55; factors.append('no_purchase_365d')
            elif days > 180:
                prob += 0.4; factors.append('no_purchase_180d')
            elif days > 90:
                prob += 0.25; factors.append('no_purchase_90d')
            elif days > 30:
                prob += 0.1; factors.append('no_purchase_30d')
            if dorm.lifetime_orders == 0:
                prob += 0.15; factors.append('never_purchased')
    except Exception:
        pass
    if user.last_login and (timezone.now() - user.last_login).days > 60:
        prob += 0.15
        factors.append('no_login_60d')
    prob = min(0.99, prob)
    if   prob > 0.85: band = 'critical'
    elif prob > 0.6:  band = 'high'
    elif prob > 0.3:  band = 'medium'
    else:             band = 'low'
    intervention = {'critical': 'winback_high_value_coupon',
                     'high': 'winback_coupon',
                     'medium': 'email_nudge',
                     'low': ''}[band]
    obj, _ = ChurnPrediction.objects.update_or_create(
        user=user, snapshot_date=snapshot_date,
        defaults={
            'churn_probability': round(prob, 4),
            'risk_band': band, 'top_factors': factors,
            'intervention_recommended': intervention,
        },
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH15 — Multi-touch attribution
# ═══════════════════════════════════════════════════════════════════

def run_attribution_model(*, model: str,
                             window_start: date_cls,
                             window_end: date_cls) -> AttributionModelRun:
    """Computes channel credits over BuyerAttributionTouch journeys
    using the chosen weighting scheme."""
    journeys: dict[str, list] = {}
    try:
        from apps.buyer_engagement.models import BuyerAttributionTouch
        touches = BuyerAttributionTouch.objects.filter(
            occurred_at__date__gte=window_start,
            occurred_at__date__lte=window_end,
        ).order_by('attribution_id', 'occurred_at')
        for t in touches:
            journeys.setdefault(t.attribution_id, []).append(t)
    except Exception:
        pass

    credits: dict[str, float] = {}
    conversions = 0
    for jid, ts in journeys.items():
        if not any(t.stage == 'first_purchase' for t in ts):
            continue
        conversions += 1
        channels = [t.channel or 'unknown' for t in ts]
        n = len(channels)
        if model == 'last_touch':
            weights = {channels[-1]: 1.0}
        elif model == 'first_touch':
            weights = {channels[0]: 1.0}
        elif model == 'linear':
            weights = {}
            for c in channels:
                weights[c] = weights.get(c, 0) + 1 / n
        elif model == 'time_decay':
            weights = {}
            half = 2.0
            raw = [(0.5 ** ((n - 1 - i) / half)) for i in range(n)]
            total = sum(raw)
            for i, c in enumerate(channels):
                weights[c] = weights.get(c, 0) + raw[i] / total
        elif model == 'position_based':
            weights = {}
            if n == 1:
                weights[channels[0]] = 1.0
            else:
                weights[channels[0]] = weights.get(channels[0], 0) + 0.4
                weights[channels[-1]] = weights.get(channels[-1], 0) + 0.4
                for c in channels[1:-1]:
                    weights[c] = weights.get(c, 0) + 0.2 / max(1, n - 2)
        else:
            weights = {channels[-1]: 1.0}
        for c, w in weights.items():
            credits[c] = credits.get(c, 0) + w

    obj, _ = AttributionModelRun.objects.update_or_create(
        model=model, window_start=window_start, window_end=window_end,
        defaults={
            'total_conversions': conversions,
            'channel_credits': {k: round(v, 3) for k, v in credits.items()},
        },
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH17 — Data quality
# ═══════════════════════════════════════════════════════════════════

def run_dq_checks() -> dict:
    """Walk active checks; the dev evaluators handle row_count_anomaly
    and freshness against the operational DB."""
    from django.db import connection
    passed = failed = 0
    for check in DataQualityCheck.objects.filter(is_active=True):
        status = 'pass'
        observed: dict = {}
        try:
            if check.check_kind == 'row_count_anomaly':
                table = check.config.get('table', '')
                min_rows = int(check.config.get('min_rows', 0))
                if table in connection.introspection.table_names():
                    with connection.cursor() as cur:
                        cur.execute(f'SELECT COUNT(*) FROM "{table}"')
                        count = cur.fetchone()[0]
                    observed = {'row_count': count}
                    if count < min_rows:
                        status = 'fail'
                else:
                    status = 'fail'
                    observed = {'error': 'TABLE_NOT_FOUND'}
            elif check.check_kind == 'freshness':
                sync = EtlTableSync.objects.filter(
                    source_table=check.config.get('table', ''),
                ).first()
                max_age = int(check.config.get('max_age_minutes', 1440))
                if sync and sync.last_synced_at:
                    age = (timezone.now() - sync.last_synced_at).total_seconds() / 60
                    observed = {'age_minutes': round(age, 1)}
                    if age > max_age:
                        status = 'fail'
                else:
                    status = 'warn'
        except Exception as e:
            status = 'fail'
            observed = {'error': str(e)[:200]}
        check.last_run_at = timezone.now()
        check.last_status = status
        check.save(update_fields=['last_run_at', 'last_status'])
        if status == 'fail':
            DataQualityIncident.objects.create(
                quality_check=check, severity='error',
                observed_value=observed,
                expected_range=check.config,
            )
            failed += 1
        else:
            passed += 1
    return {'passed': passed, 'failed': failed}


# ═══════════════════════════════════════════════════════════════════
# CH21 — Feature store
# ═══════════════════════════════════════════════════════════════════

def write_feature(*, feature_code: str, entity_id: str, value) -> FeatureValue:
    feature = FeatureDefinition.objects.get(code=feature_code)
    obj, _ = FeatureValue.objects.update_or_create(
        feature=feature, entity_id=entity_id[:64],
        defaults={'value': value},
    )
    return obj


def read_features(*, entity_id: str,
                    feature_codes: list[str]) -> dict:
    rows = FeatureValue.objects.filter(
        feature__code__in=feature_codes, entity_id=entity_id,
    ).select_related('feature')
    return {r.feature.code: r.value for r in rows}


# ═══════════════════════════════════════════════════════════════════
# CH22 — Bandit
# ═══════════════════════════════════════════════════════════════════

def bandit_select_arm(experiment: BanditExperiment) -> BanditArm:
    """Thompson sampling (default): sample from each arm's Beta
    posterior, pick the max."""
    arms = list(experiment.arms.all())
    if not arms:
        raise ValueError('NO_ARMS')
    if experiment.algorithm == 'epsilon_greedy':
        if random.random() < experiment.epsilon:
            return random.choice(arms)
        return max(arms, key=lambda a: (a.rewards / a.pulls) if a.pulls else 0)
    if experiment.algorithm == 'ucb1':
        total = sum(a.pulls for a in arms) or 1
        def ucb(a):
            if a.pulls == 0:
                return float('inf')
            return a.rewards / a.pulls + math.sqrt(2 * math.log(total) / a.pulls)
        return max(arms, key=ucb)
    # Thompson.
    return max(arms, key=lambda a: random.betavariate(a.alpha, a.beta))


def bandit_record_outcome(arm: BanditArm, *, rewarded: bool) -> BanditArm:
    arm.pulls += 1
    if rewarded:
        arm.rewards += 1
        arm.alpha += 1
    else:
        arm.beta += 1
    arm.save()
    return arm


# ═══════════════════════════════════════════════════════════════════
# CH23 — Customer 360
# ═══════════════════════════════════════════════════════════════════

def refresh_c360(user) -> Customer360Profile:
    data: dict = {}
    try:
        from apps.orders.models import Order
        qs = Order.objects.filter(buyer=user)
        agg = qs.aggregate(n=django_models.Count('id'),
                            s=django_models.Sum('total_amount'),
                            first=django_models.Min('created_at'),
                            last=django_models.Max('created_at'))
        data['lifetime_orders'] = agg['n'] or 0
        data['lifetime_gmv'] = Decimal(str(agg['s'] or 0))
        data['avg_order_value'] = (
            (data['lifetime_gmv'] / data['lifetime_orders']).quantize(Decimal('0.01'))
            if data['lifetime_orders'] else Decimal('0')
        )
        data['first_order_at'] = agg['first']
        data['last_order_at'] = agg['last']
    except Exception:
        pass
    try:
        from apps.buyer_engagement.models import BuyerLTV, DormancyState
        ltv = BuyerLTV.objects.filter(user=user).first()
        if ltv:
            data['ltv_segment'] = ltv.segment or ''
        dorm = DormancyState.objects.filter(user=user).first()
        if dorm:
            data['dormancy_band'] = dorm.band
    except Exception:
        pass
    try:
        from apps.trust_safety.models import BuyerTrustScore
        ts = BuyerTrustScore.objects.filter(user=user).first()
        if ts:
            data['trust_band'] = ts.band
    except Exception:
        pass
    try:
        churn = ChurnPrediction.objects.filter(user=user).order_by('-snapshot_date').first()
        if churn:
            data['churn_risk_band'] = churn.risk_band
    except Exception:
        pass
    try:
        from apps.cs_ops.models import SupportTicket
        data['open_tickets'] = SupportTicket.objects.filter(
            requester=user,
            status__in=('new', 'open', 'pending_buyer', 'pending_seller'),
        ).count()
    except Exception:
        pass
    try:
        from apps.fraud_engine.models import DeviceUserLink
        data['device_count'] = DeviceUserLink.objects.filter(user=user).count()
    except Exception:
        pass

    obj, _ = Customer360Profile.objects.update_or_create(
        user=user, defaults=data,
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH24 — Platform KPI
# ═══════════════════════════════════════════════════════════════════

def snapshot_platform_kpis(snapshot_date: date_cls = None) -> DataPlatformKpiSnapshot:
    if snapshot_date is None:
        snapshot_date = timezone.now().date()
    start = timezone.make_aware(
        timezone.datetime.combine(snapshot_date, timezone.datetime.min.time())
    )
    end = start + timedelta(days=1)
    etl = EtlPipelineRun.objects.filter(started_at__gte=start, started_at__lt=end)
    etl_n = etl.count()
    etl_ok = etl.filter(status='success').count()
    rows = etl.aggregate(s=django_models.Sum('rows_loaded'))['s'] or 0
    dq = DataQualityCheck.objects.filter(last_run_at__gte=start, last_run_at__lt=end)
    dq_n = dq.count()
    dq_pass = dq.filter(last_status='pass').count()
    open_incidents = DataQualityIncident.objects.filter(resolved=False).count()
    stale = 0
    for f in FeatureDefinition.objects.filter(is_active=True):
        cutoff = timezone.now() - timedelta(minutes=f.freshness_sla_minutes)
        if not FeatureValue.objects.filter(
            feature=f, computed_at__gte=cutoff,
        ).exists() and FeatureValue.objects.filter(feature=f).exists():
            stale += 1
    gdpr_open = 0
    try:
        from apps.data_rights.models import DataSubjectRequest
        gdpr_open = DataSubjectRequest.objects.exclude(
            status__in=('completed', 'rejected'),
        ).count()
    except Exception:
        pass
    obj, _ = DataPlatformKpiSnapshot.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'etl_runs': etl_n,
            'etl_success_pct': (etl_ok / etl_n * 100) if etl_n else 0,
            'etl_rows_loaded': rows,
            'dq_checks_run': dq_n,
            'dq_pass_pct': (dq_pass / dq_n * 100) if dq_n else 0,
            'dq_open_incidents': open_incidents,
            'feature_count': FeatureDefinition.objects.filter(is_active=True).count(),
            'stale_features': stale,
            'catalogued_datasets': DataCatalogueEntry.objects.count(),
            'pii_fields_registered': PiiFieldRegistry.objects.count(),
            'active_experiments': BanditExperiment.objects.filter(status='running').count(),
            'gdpr_requests_open': gdpr_open,
            'c360_profiles': Customer360Profile.objects.count(),
        },
    )
    return obj
