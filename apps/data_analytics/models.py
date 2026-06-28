"""
Data & Analytics Platform — data model
======================================

Implements AliExpress_Data_Analytics_Additional.docx CH1–CH24 where
existing apps don't already own the schema. We DO NOT duplicate:

  - apps.analytics.UserEvent / FunnelEvent / SellerPerformance
  - apps.data_rights.DataSubjectRequest (GDPR request workflow)
  - apps.forecasting.DailyDemand / DemandForecast
  - apps.payment_ops.FinancialReportSnapshot (payment P&L)
  - apps.search_discovery.SearchKpiSnapshot / SearchExperiment
  - apps.buyer_engagement.BuyerAttributionTouch / BuyerLTV

New tables:

  CH2   RealtimeMetricSnapshot          — live GMV / users / funnel
  CH3   SellerAnalyticsReport           — generated report metadata
  CH4   BuyerCohort, CohortCell         — retention matrix
  CH5   GmvDecomposition                — GMV delta drivers
  CH6   FraudLossReport
  CH7   DeliveryPerformanceReport
  CH8   QueryAnalyticsRollup            — per-query daily stats
  CH9   AbTestEvaluation                — significance + CUPED
  CH10  EtlPipelineRun, EtlTableSync    — CDC + full-load tracking
  CH11  MetricDefinition, ScheduledReport
  CH12  DataRequestAuditLog             — bridges data_rights
  CH13  ChurnPrediction
  CH14  FeatureUsageRollup
  CH15  AttributionModelRun             — multi-touch model results
  CH16  DataCatalogueEntry
  CH17  DataQualityCheck, DataQualityIncident
  CH18  DataGovernancePolicy, DataAccessGrant
  CH19  PiiFieldRegistry
  CH20  EventStreamTopic, ConsumerGroupLag
  CH21  FeatureDefinition, FeatureValue — ML feature store
  CH22  BanditExperiment, BanditArm
  CH23  Customer360Profile
  CH24  DataPlatformKpiSnapshot
  Audit DataAnalyticsEvent
"""
from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


# ─────────────────────────────────────────────────────────────────
# CH2 — Realtime metrics
# ─────────────────────────────────────────────────────────────────

class RealtimeMetricSnapshot(models.Model):
    """Per-minute roll-up consumed by the live dashboard. In
    production a Flink job feeds this; in dev the Celery sweeper
    computes it from the operational tables."""

    id = models.BigAutoField(primary_key=True)
    bucket_minute = models.DateTimeField(db_index=True)
    gmv = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    orders_count = models.PositiveIntegerField(default=0)
    active_users = models.PositiveIntegerField(default=0)
    sessions_started = models.PositiveIntegerField(default=0)
    carts_created = models.PositiveIntegerField(default=0)
    checkouts_started = models.PositiveIntegerField(default=0)
    payments_succeeded = models.PositiveIntegerField(default=0)
    funnel_view_to_cart_pct = models.FloatField(default=0)
    funnel_cart_to_checkout_pct = models.FloatField(default=0)
    funnel_checkout_to_paid_pct = models.FloatField(default=0)
    by_country = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('bucket_minute',)]
        ordering = ['-bucket_minute']


# ─────────────────────────────────────────────────────────────────
# CH3 — Seller analytics reports
# ─────────────────────────────────────────────────────────────────

REPORT_PERIOD_CHOICES = (
    ('daily',   'Daily'),
    ('weekly',  'Weekly'),
    ('monthly', 'Monthly'),
    ('custom',  'Custom range'),
)


class SellerAnalyticsReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='analytics_reports')
    period = models.CharField(max_length=10, choices=REPORT_PERIOD_CHOICES)
    period_start = models.DateField()
    period_end = models.DateField()
    metrics = models.JSONField(default=dict, blank=True)
    export_format = models.CharField(
        max_length=8, default='json',
        choices=(('json', 'JSON'), ('csv', 'CSV'), ('pdf', 'PDF')),
    )
    file_key = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(
        max_length=12, default='generated',
        choices=(('queued', 'Queued'), ('generated', 'Generated'),
                 ('delivered', 'Delivered'), ('failed', 'Failed')),
    )
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('seller', 'period', 'period_start')]


# ─────────────────────────────────────────────────────────────────
# CH4 — Buyer cohorts
# ─────────────────────────────────────────────────────────────────

class BuyerCohort(models.Model):
    """One row per acquisition-month cohort."""

    id = models.BigAutoField(primary_key=True)
    cohort_month = models.DateField(unique=True, db_index=True)
    cohort_size = models.PositiveIntegerField(default=0)
    avg_first_order_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    computed_at = models.DateTimeField(auto_now=True)


class CohortCell(models.Model):
    """Retention matrix cell: % of the cohort active in month N."""

    id = models.BigAutoField(primary_key=True)
    cohort = models.ForeignKey(BuyerCohort, on_delete=models.CASCADE, related_name='cells')
    month_offset = models.PositiveSmallIntegerField()
    active_users = models.PositiveIntegerField(default=0)
    retention_pct = models.FloatField(default=0)
    repeat_purchase_pct = models.FloatField(default=0)
    cumulative_ltv = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        unique_together = [('cohort', 'month_offset')]


# ─────────────────────────────────────────────────────────────────
# CH5 — GMV decomposition
# ─────────────────────────────────────────────────────────────────

class GmvDecomposition(models.Model):
    """CH5.2 — GMV delta = traffic × conversion × AOV decomposition
    per period so leadership sees WHICH driver moved."""

    id = models.BigAutoField(primary_key=True)
    period_start = models.DateField()
    period_end = models.DateField()
    gmv_current = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    gmv_previous = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    gmv_delta_pct = models.FloatField(default=0)
    traffic_contribution_pct = models.FloatField(default=0)
    conversion_contribution_pct = models.FloatField(default=0)
    aov_contribution_pct = models.FloatField(default=0)
    by_category = models.JSONField(default=dict, blank=True)
    by_country = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('period_start', 'period_end')]


# ─────────────────────────────────────────────────────────────────
# CH6 — Fraud loss report
# ─────────────────────────────────────────────────────────────────

class FraudLossReport(models.Model):
    snapshot_date = models.DateField(primary_key=True)
    chargeback_loss = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    dispute_loss = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    refund_abuse_loss = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    promo_abuse_loss = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    manipulation_loss = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    prevented_loss_estimate = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_loss = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    loss_rate_bps = models.FloatField(
        default=0, help_text='Total loss as basis points of GMV.',
    )
    by_pattern = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH7 — Delivery performance report
# ─────────────────────────────────────────────────────────────────

class DeliveryPerformanceReport(models.Model):
    snapshot_date = models.DateField(primary_key=True)
    shipments_delivered = models.PositiveIntegerField(default=0)
    avg_transit_days = models.FloatField(default=0)
    p50_transit_days = models.FloatField(default=0)
    p90_transit_days = models.FloatField(default=0)
    on_time_pct = models.FloatField(default=0)
    delayed_count = models.PositiveIntegerField(default=0)
    lost_count = models.PositiveIntegerField(default=0)
    by_carrier = models.JSONField(default=dict, blank=True)
    by_lane = models.JSONField(
        default=dict, blank=True,
        help_text='origin→destination country pair stats.',
    )
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH8 — Per-query search rollup
# ─────────────────────────────────────────────────────────────────

class QueryAnalyticsRollup(models.Model):
    """Daily per-query stats — complements the global
    search_discovery.SearchKpiSnapshot."""

    id = models.BigAutoField(primary_key=True)
    snapshot_date = models.DateField(db_index=True)
    query = models.CharField(max_length=200, db_index=True)
    search_count = models.PositiveIntegerField(default=0)
    zero_results_count = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    ctr = models.FloatField(default=0)
    conversions = models.PositiveIntegerField(default=0)
    avg_click_position = models.FloatField(default=0)

    class Meta:
        unique_together = [('snapshot_date', 'query')]


# ─────────────────────────────────────────────────────────────────
# CH9 — A/B evaluation
# ─────────────────────────────────────────────────────────────────

class AbTestEvaluation(models.Model):
    """Statistical evaluation of an experiment. References the
    search_discovery.SearchExperiment by slug (string) so this app
    can also evaluate non-search experiments."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    experiment_slug = models.CharField(max_length=80, db_index=True)
    metric = models.CharField(max_length=40, default='ctr')
    control_n = models.PositiveIntegerField(default=0)
    control_mean = models.FloatField(default=0)
    control_variance = models.FloatField(default=0)
    variant_n = models.PositiveIntegerField(default=0)
    variant_mean = models.FloatField(default=0)
    variant_variance = models.FloatField(default=0)
    lift_pct = models.FloatField(default=0)
    z_score = models.FloatField(default=0)
    p_value = models.FloatField(default=1)
    significant = models.BooleanField(default=False)
    cuped_applied = models.BooleanField(default=False)
    cuped_variance_reduction_pct = models.FloatField(default=0)
    recommendation = models.CharField(
        max_length=16, default='continue',
        choices=(('ship_variant', 'Ship variant'),
                 ('keep_control', 'Keep control'),
                 ('continue', 'Continue running'),
                 ('inconclusive', 'Inconclusive — stop')),
    )
    evaluated_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH10 — ETL pipeline
# ─────────────────────────────────────────────────────────────────

class EtlPipelineRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pipeline_name = models.CharField(max_length=80, db_index=True)
    run_kind = models.CharField(
        max_length=12, default='incremental',
        choices=(('full', 'Full load'), ('incremental', 'Incremental / CDC'),
                 ('backfill', 'Backfill')),
    )
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    rows_extracted = models.PositiveBigIntegerField(default=0)
    rows_loaded = models.PositiveBigIntegerField(default=0)
    rows_failed = models.PositiveBigIntegerField(default=0)
    status = models.CharField(
        max_length=12, default='running',
        choices=(('running', 'Running'), ('success', 'Success'),
                 ('partial', 'Partial'), ('failed', 'Failed')),
    )
    error_message = models.TextField(blank=True, default='')


class EtlTableSync(models.Model):
    """High-watermark per source table for CDC."""

    source_table = models.CharField(max_length=120, primary_key=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_watermark = models.CharField(max_length=64, blank=True, default='')
    sync_frequency_minutes = models.PositiveIntegerField(default=60)
    is_active = models.BooleanField(default=True)


# ─────────────────────────────────────────────────────────────────
# CH11 — Semantic layer + scheduled reports
# ─────────────────────────────────────────────────────────────────

class MetricDefinition(models.Model):
    """Canonical metric definitions — the semantic layer that BI
    tools read so 'GMV' means the same thing everywhere."""

    code = models.CharField(max_length=40, primary_key=True)
    display_name = models.CharField(max_length=120)
    description = models.TextField(blank=True, default='')
    sql_expression = models.TextField()
    grain = models.CharField(max_length=24, default='daily')
    owner_team = models.CharField(max_length=64, blank=True, default='')
    unit = models.CharField(max_length=20, blank=True, default='')
    is_certified = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)


class ScheduledReport(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160)
    metric_codes = models.JSONField(default=list)
    recipients = models.JSONField(default=list)
    cadence = models.CharField(
        max_length=12, default='weekly',
        choices=(('daily', 'Daily'), ('weekly', 'Weekly'),
                 ('monthly', 'Monthly')),
    )
    delivery_channel = models.CharField(
        max_length=12, default='email',
        choices=(('email', 'Email'), ('slack', 'Slack'),
                 ('webhook', 'Webhook')),
    )
    last_sent_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH12 — GDPR audit log
# ─────────────────────────────────────────────────────────────────

class DataRequestAuditLog(models.Model):
    """Append-only audit of every step in a data-subject-request
    workflow. Bridges apps.data_rights.DataSubjectRequest by id."""

    id = models.BigAutoField(primary_key=True)
    request_id = models.CharField(max_length=64, db_index=True)
    request_kind = models.CharField(
        max_length=16,
        choices=(('access', 'Access'), ('erasure', 'Erasure'),
                 ('portability', 'Portability'),
                 ('rectification', 'Rectification')),
    )
    step = models.CharField(max_length=40)
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='gdpr_audit_actions',
    )
    systems_touched = models.JSONField(default=list, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ─────────────────────────────────────────────────────────────────
# CH13 — Churn prediction
# ─────────────────────────────────────────────────────────────────

class ChurnPrediction(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='churn_predictions')
    snapshot_date = models.DateField(db_index=True)
    churn_probability = models.FloatField()
    risk_band = models.CharField(
        max_length=12,
        choices=(('low', 'Low <30%'), ('medium', 'Medium 30-60%'),
                 ('high', 'High 60-85%'), ('critical', 'Critical >85%')),
    )
    top_factors = models.JSONField(default=list, blank=True)
    model_version = models.CharField(max_length=20, default='v0_heuristic')
    intervention_recommended = models.CharField(max_length=40, blank=True, default='')

    class Meta:
        unique_together = [('user', 'snapshot_date')]


# ─────────────────────────────────────────────────────────────────
# CH14 — Feature usage rollup
# ─────────────────────────────────────────────────────────────────

class FeatureUsageRollup(models.Model):
    """Daily per-feature usage; raw events stay in apps.analytics.
    UserEvent — this is the aggregated dashboard layer."""

    id = models.BigAutoField(primary_key=True)
    snapshot_date = models.DateField(db_index=True)
    feature_key = models.CharField(max_length=64, db_index=True)
    unique_users = models.PositiveIntegerField(default=0)
    total_events = models.PositiveIntegerField(default=0)
    adoption_pct = models.FloatField(default=0)
    retention_d7_pct = models.FloatField(default=0)

    class Meta:
        unique_together = [('snapshot_date', 'feature_key')]


# ─────────────────────────────────────────────────────────────────
# CH15 — Attribution model run
# ─────────────────────────────────────────────────────────────────

ATTRIBUTION_MODEL_CHOICES = (
    ('last_touch',     'Last touch'),
    ('first_touch',    'First touch'),
    ('linear',         'Linear'),
    ('time_decay',     'Time decay'),
    ('position_based', 'Position based (U-shape)'),
    ('data_driven',    'Data driven (Shapley)'),
)


class AttributionModelRun(models.Model):
    """One evaluation run of a multi-touch model over a window.
    Channel credits sum to total conversions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    model = models.CharField(max_length=20, choices=ATTRIBUTION_MODEL_CHOICES)
    window_start = models.DateField()
    window_end = models.DateField()
    total_conversions = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    channel_credits = models.JSONField(default=dict, blank=True)
    channel_roi = models.JSONField(default=dict, blank=True)
    computed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('model', 'window_start', 'window_end')]


# ─────────────────────────────────────────────────────────────────
# CH16 — Data catalogue
# ─────────────────────────────────────────────────────────────────

class DataCatalogueEntry(models.Model):
    id = models.BigAutoField(primary_key=True)
    dataset_name = models.CharField(max_length=160, unique=True)
    layer = models.CharField(
        max_length=12, default='operational',
        choices=(('operational', 'Operational DB'),
                 ('staging', 'Staging'),
                 ('warehouse', 'Warehouse'),
                 ('mart', 'Data mart'),
                 ('stream', 'Stream topic')),
    )
    description = models.TextField(blank=True, default='')
    owner_team = models.CharField(max_length=64, blank=True, default='')
    pii_classification = models.CharField(
        max_length=12, default='none',
        choices=(('none', 'None'), ('internal', 'Internal'),
                 ('pii', 'PII'), ('sensitive', 'Sensitive PII')),
    )
    retention_days = models.PositiveIntegerField(default=365)
    upstream_datasets = models.JSONField(default=list, blank=True)
    schema_fields = models.JSONField(default=list, blank=True)
    last_reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH17 — Data quality
# ─────────────────────────────────────────────────────────────────

DQ_CHECK_KIND_CHOICES = (
    ('row_count_anomaly', 'Row count anomaly'),
    ('null_rate',         'Null rate threshold'),
    ('freshness',         'Freshness SLA'),
    ('uniqueness',        'Uniqueness violation'),
    ('referential',       'Referential integrity'),
    ('distribution_drift','Distribution drift'),
)


class DataQualityCheck(models.Model):
    id = models.BigAutoField(primary_key=True)
    dataset_name = models.CharField(max_length=160, db_index=True)
    check_kind = models.CharField(max_length=24, choices=DQ_CHECK_KIND_CHOICES)
    config = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    last_status = models.CharField(
        max_length=8, default='unknown',
        choices=(('pass', 'Pass'), ('warn', 'Warn'),
                 ('fail', 'Fail'), ('unknown', 'Unknown')),
    )


class DataQualityIncident(models.Model):
    id = models.BigAutoField(primary_key=True)
    # NOTE: named quality_check, NOT check — a field named `check`
    # shadows Django's Model.check() classmethod and fails E020.
    quality_check = models.ForeignKey(DataQualityCheck, on_delete=models.CASCADE, related_name='incidents')
    severity = models.CharField(
        max_length=8, default='warn',
        choices=(('warn', 'Warn'), ('error', 'Error'),
                 ('critical', 'Critical')),
    )
    observed_value = models.JSONField(default=dict, blank=True)
    expected_range = models.JSONField(default=dict, blank=True)
    resolved = models.BooleanField(default=False)
    resolution_notes = models.TextField(blank=True, default='')
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)
    resolved_at = models.DateTimeField(null=True, blank=True)


# ─────────────────────────────────────────────────────────────────
# CH18 — Governance
# ─────────────────────────────────────────────────────────────────

class DataGovernancePolicy(models.Model):
    code = models.CharField(max_length=40, primary_key=True)
    name = models.CharField(max_length=160)
    applies_to_classification = models.CharField(max_length=12)
    retention_days = models.PositiveIntegerField()
    requires_approval_to_access = models.BooleanField(default=False)
    masking_required = models.BooleanField(default=False)
    description = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)


class DataAccessGrant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grantee = models.ForeignKey(User, on_delete=models.CASCADE, related_name='data_access_grants')
    dataset_name = models.CharField(max_length=160, db_index=True)
    access_level = models.CharField(
        max_length=12, default='read',
        choices=(('read', 'Read'), ('read_pii', 'Read incl. PII'),
                 ('write', 'Write'), ('admin', 'Admin')),
    )
    justification = models.TextField()
    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='data_grants_approved',
    )
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    granted_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH19 — PII registry
# ─────────────────────────────────────────────────────────────────

class PiiFieldRegistry(models.Model):
    """Every PII field in every dataset, with the masking rule that
    applies when it leaves the operational boundary."""

    id = models.BigAutoField(primary_key=True)
    dataset_name = models.CharField(max_length=160, db_index=True)
    field_name = models.CharField(max_length=120)
    pii_kind = models.CharField(
        max_length=20,
        choices=(('name', 'Name'), ('email', 'Email'),
                 ('phone', 'Phone'), ('address', 'Address'),
                 ('national_id', 'National ID'),
                 ('payment_token', 'Payment token'),
                 ('ip_address', 'IP address'),
                 ('device_id', 'Device ID'),
                 ('dob', 'Date of birth'),
                 ('location', 'Geo location')),
    )
    masking_strategy = models.CharField(
        max_length=20, default='hash',
        choices=(('hash', 'SHA-256 hash'),
                 ('redact', 'Full redaction'),
                 ('partial', 'Partial mask (a***@b.com)'),
                 ('tokenise', 'Tokenisation'),
                 ('generalise', 'Generalisation (city only)'),
                 ('none', 'No masking (restricted access)')),
    )
    encrypted_at_rest = models.BooleanField(default=False)
    notes = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        unique_together = [('dataset_name', 'field_name')]


# ─────────────────────────────────────────────────────────────────
# CH20 — Event streaming
# ─────────────────────────────────────────────────────────────────

class EventStreamTopic(models.Model):
    topic_name = models.CharField(max_length=120, primary_key=True)
    description = models.TextField(blank=True, default='')
    partitions = models.PositiveSmallIntegerField(default=6)
    retention_hours = models.PositiveIntegerField(default=168)
    schema_def = models.JSONField(default=dict, blank=True)
    producers = models.JSONField(default=list, blank=True)
    consumers = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)


class ConsumerGroupLag(models.Model):
    """Lag snapshot per consumer group per topic — the streaming
    health dashboard reads this."""

    id = models.BigAutoField(primary_key=True)
    topic = models.ForeignKey(EventStreamTopic, on_delete=models.CASCADE, related_name='lags')
    consumer_group = models.CharField(max_length=120)
    total_lag = models.PositiveBigIntegerField(default=0)
    max_partition_lag = models.PositiveBigIntegerField(default=0)
    is_healthy = models.BooleanField(default=True)
    measured_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ─────────────────────────────────────────────────────────────────
# CH21 — Feature store
# ─────────────────────────────────────────────────────────────────

class FeatureDefinition(models.Model):
    code = models.CharField(max_length=64, primary_key=True)
    description = models.TextField(blank=True, default='')
    entity = models.CharField(
        max_length=16, default='user',
        choices=(('user', 'User'), ('product', 'Product'),
                 ('seller', 'Seller'), ('order', 'Order')),
    )
    dtype = models.CharField(
        max_length=12, default='float',
        choices=(('float', 'Float'), ('int', 'Int'),
                 ('string', 'String'), ('bool', 'Bool'),
                 ('embedding', 'Embedding')),
    )
    freshness_sla_minutes = models.PositiveIntegerField(default=1440)
    owner_team = models.CharField(max_length=64, blank=True, default='')
    consuming_models = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)


class FeatureValue(models.Model):
    """Online feature store row — (feature, entity) → latest value."""

    id = models.BigAutoField(primary_key=True)
    feature = models.ForeignKey(FeatureDefinition, on_delete=models.CASCADE, related_name='feature_values')
    entity_id = models.CharField(max_length=64, db_index=True)
    value = models.JSONField()
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('feature', 'entity_id')]


# ─────────────────────────────────────────────────────────────────
# CH22 — Bandit experiments
# ─────────────────────────────────────────────────────────────────

class BanditExperiment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, max_length=80)
    name = models.CharField(max_length=160)
    algorithm = models.CharField(
        max_length=20, default='thompson',
        choices=(('thompson', 'Thompson sampling'),
                 ('ucb1', 'UCB1'),
                 ('epsilon_greedy', 'Epsilon greedy')),
    )
    epsilon = models.FloatField(default=0.1)
    status = models.CharField(
        max_length=12, default='running',
        choices=(('running', 'Running'), ('paused', 'Paused'),
                 ('concluded', 'Concluded')),
    )
    winning_arm = models.CharField(max_length=64, blank=True, default='')
    started_at = models.DateTimeField(auto_now_add=True)
    concluded_at = models.DateTimeField(null=True, blank=True)


class BanditArm(models.Model):
    id = models.BigAutoField(primary_key=True)
    experiment = models.ForeignKey(BanditExperiment, on_delete=models.CASCADE, related_name='arms')
    arm_key = models.CharField(max_length=64)
    pulls = models.PositiveIntegerField(default=0)
    rewards = models.PositiveIntegerField(default=0)
    alpha = models.FloatField(default=1.0, help_text='Beta prior α (successes+1).')
    beta = models.FloatField(default=1.0, help_text='Beta prior β (failures+1).')

    class Meta:
        unique_together = [('experiment', 'arm_key')]


# ─────────────────────────────────────────────────────────────────
# CH23 — Customer 360
# ─────────────────────────────────────────────────────────────────

class Customer360Profile(models.Model):
    """Unified buyer profile — denormalised joins from across the
    platform refreshed nightly so support / marketing / ML read one
    row instead of 12 joins."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='c360')
    lifetime_orders = models.PositiveIntegerField(default=0)
    lifetime_gmv = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    avg_order_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    first_order_at = models.DateTimeField(null=True, blank=True)
    last_order_at = models.DateTimeField(null=True, blank=True)
    favourite_categories = models.JSONField(default=list, blank=True)
    loyalty_tier = models.CharField(max_length=24, blank=True, default='')
    ltv_segment = models.CharField(max_length=20, blank=True, default='')
    dormancy_band = models.CharField(max_length=24, blank=True, default='')
    churn_risk_band = models.CharField(max_length=12, blank=True, default='')
    trust_band = models.CharField(max_length=20, blank=True, default='')
    open_tickets = models.PositiveSmallIntegerField(default=0)
    open_disputes = models.PositiveSmallIntegerField(default=0)
    device_count = models.PositiveSmallIntegerField(default=0)
    marketing_consents = models.JSONField(default=dict, blank=True)
    refreshed_at = models.DateTimeField(auto_now=True)


# ─────────────────────────────────────────────────────────────────
# CH24 — Platform KPI
# ─────────────────────────────────────────────────────────────────

class DataPlatformKpiSnapshot(models.Model):
    snapshot_date = models.DateField(primary_key=True)
    etl_runs = models.PositiveIntegerField(default=0)
    etl_success_pct = models.FloatField(default=0)
    etl_rows_loaded = models.PositiveBigIntegerField(default=0)
    dq_checks_run = models.PositiveIntegerField(default=0)
    dq_pass_pct = models.FloatField(default=0)
    dq_open_incidents = models.PositiveIntegerField(default=0)
    avg_consumer_lag = models.FloatField(default=0)
    feature_count = models.PositiveIntegerField(default=0)
    stale_features = models.PositiveIntegerField(default=0)
    catalogued_datasets = models.PositiveIntegerField(default=0)
    pii_fields_registered = models.PositiveIntegerField(default=0)
    active_experiments = models.PositiveIntegerField(default=0)
    gdpr_requests_open = models.PositiveIntegerField(default=0)
    c360_profiles = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# Audit
# ─────────────────────────────────────────────────────────────────

class DataAnalyticsEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    kind = models.CharField(max_length=64, db_index=True)
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='da_audit_events',
    )
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    @staticmethod
    def log(*, kind, actor=None, payload=None):
        try:
            return DataAnalyticsEvent.objects.create(
                kind=kind, actor=actor, payload=payload or {},
            )
        except Exception:
            return None
