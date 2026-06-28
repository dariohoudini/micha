from django.contrib import admin

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


@admin.register(RealtimeMetricSnapshot)
class RealtimeMetricSnapshotAdmin(admin.ModelAdmin):
    list_display = ('bucket_minute', 'gmv', 'orders_count',
                    'active_users', 'payments_succeeded')


@admin.register(SellerAnalyticsReport)
class SellerAnalyticsReportAdmin(admin.ModelAdmin):
    list_display = ('seller', 'period', 'period_start',
                    'period_end', 'status')
    list_filter = ('period', 'status')


@admin.register(BuyerCohort)
class BuyerCohortAdmin(admin.ModelAdmin):
    list_display = ('cohort_month', 'cohort_size', 'computed_at')


@admin.register(CohortCell)
class CohortCellAdmin(admin.ModelAdmin):
    list_display = ('cohort', 'month_offset', 'active_users',
                    'retention_pct')


@admin.register(GmvDecomposition)
class GmvDecompositionAdmin(admin.ModelAdmin):
    list_display = ('period_start', 'period_end', 'gmv_current',
                    'gmv_delta_pct')


@admin.register(FraudLossReport)
class FraudLossReportAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'chargeback_loss',
                    'refund_abuse_loss', 'total_loss')


@admin.register(DeliveryPerformanceReport)
class DeliveryPerformanceReportAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'shipments_delivered',
                    'avg_transit_days', 'on_time_pct')


@admin.register(QueryAnalyticsRollup)
class QueryAnalyticsRollupAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'query', 'search_count',
                    'ctr', 'conversions')


@admin.register(AbTestEvaluation)
class AbTestEvaluationAdmin(admin.ModelAdmin):
    list_display = ('experiment_slug', 'metric', 'lift_pct',
                    'p_value', 'significant', 'recommendation')
    list_filter = ('significant', 'recommendation')


@admin.register(EtlPipelineRun)
class EtlPipelineRunAdmin(admin.ModelAdmin):
    list_display = ('pipeline_name', 'run_kind', 'status',
                    'rows_loaded', 'started_at', 'finished_at')
    list_filter = ('status', 'run_kind')


@admin.register(EtlTableSync)
class EtlTableSyncAdmin(admin.ModelAdmin):
    list_display = ('source_table', 'last_synced_at',
                    'sync_frequency_minutes', 'is_active')


@admin.register(MetricDefinition)
class MetricDefinitionAdmin(admin.ModelAdmin):
    list_display = ('code', 'display_name', 'grain',
                    'owner_team', 'is_certified')
    list_filter = ('is_certified',)


@admin.register(ScheduledReport)
class ScheduledReportAdmin(admin.ModelAdmin):
    list_display = ('name', 'cadence', 'delivery_channel',
                    'last_sent_at', 'is_active')


@admin.register(DataRequestAuditLog)
class DataRequestAuditLogAdmin(admin.ModelAdmin):
    list_display = ('request_id', 'request_kind', 'step',
                    'actor', 'occurred_at')
    list_filter = ('request_kind',)


@admin.register(ChurnPrediction)
class ChurnPredictionAdmin(admin.ModelAdmin):
    list_display = ('user', 'snapshot_date', 'churn_probability',
                    'risk_band', 'intervention_recommended')
    list_filter = ('risk_band',)


@admin.register(FeatureUsageRollup)
class FeatureUsageRollupAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'feature_key',
                    'unique_users', 'adoption_pct')


@admin.register(AttributionModelRun)
class AttributionModelRunAdmin(admin.ModelAdmin):
    list_display = ('model', 'window_start', 'window_end',
                    'total_conversions')
    list_filter = ('model',)


@admin.register(DataCatalogueEntry)
class DataCatalogueEntryAdmin(admin.ModelAdmin):
    list_display = ('dataset_name', 'layer', 'owner_team',
                    'pii_classification', 'retention_days')
    list_filter = ('layer', 'pii_classification')


@admin.register(DataQualityCheck)
class DataQualityCheckAdmin(admin.ModelAdmin):
    list_display = ('dataset_name', 'check_kind', 'is_active',
                    'last_status', 'last_run_at')
    list_filter = ('check_kind', 'last_status')


@admin.register(DataQualityIncident)
class DataQualityIncidentAdmin(admin.ModelAdmin):
    list_display = ('quality_check', 'severity', 'resolved', 'detected_at')
    list_filter = ('severity', 'resolved')


@admin.register(DataGovernancePolicy)
class DataGovernancePolicyAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'applies_to_classification',
                    'retention_days', 'is_active')


@admin.register(DataAccessGrant)
class DataAccessGrantAdmin(admin.ModelAdmin):
    list_display = ('grantee', 'dataset_name', 'access_level',
                    'approved_by', 'expires_at', 'revoked_at')
    list_filter = ('access_level',)


@admin.register(PiiFieldRegistry)
class PiiFieldRegistryAdmin(admin.ModelAdmin):
    list_display = ('dataset_name', 'field_name', 'pii_kind',
                    'masking_strategy', 'encrypted_at_rest')
    list_filter = ('pii_kind', 'masking_strategy')


@admin.register(EventStreamTopic)
class EventStreamTopicAdmin(admin.ModelAdmin):
    list_display = ('topic_name', 'partitions',
                    'retention_hours', 'is_active')


@admin.register(ConsumerGroupLag)
class ConsumerGroupLagAdmin(admin.ModelAdmin):
    list_display = ('topic', 'consumer_group', 'total_lag',
                    'is_healthy', 'measured_at')
    list_filter = ('is_healthy',)


@admin.register(FeatureDefinition)
class FeatureDefinitionAdmin(admin.ModelAdmin):
    list_display = ('code', 'entity', 'dtype',
                    'freshness_sla_minutes', 'is_active')
    list_filter = ('entity', 'dtype')


@admin.register(FeatureValue)
class FeatureValueAdmin(admin.ModelAdmin):
    list_display = ('feature', 'entity_id', 'computed_at')


@admin.register(BanditExperiment)
class BanditExperimentAdmin(admin.ModelAdmin):
    list_display = ('slug', 'name', 'algorithm', 'status',
                    'winning_arm')
    list_filter = ('algorithm', 'status')


@admin.register(BanditArm)
class BanditArmAdmin(admin.ModelAdmin):
    list_display = ('experiment', 'arm_key', 'pulls',
                    'rewards', 'alpha', 'beta')


@admin.register(Customer360Profile)
class Customer360ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'lifetime_orders', 'lifetime_gmv',
                    'ltv_segment', 'dormancy_band',
                    'churn_risk_band', 'trust_band')


@admin.register(DataPlatformKpiSnapshot)
class DataPlatformKpiSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'etl_runs', 'etl_success_pct',
                    'dq_pass_pct', 'feature_count', 'c360_profiles')


@admin.register(DataAnalyticsEvent)
class DataAnalyticsEventAdmin(admin.ModelAdmin):
    list_display = ('kind', 'actor', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'actor', 'payload', 'created_at')
