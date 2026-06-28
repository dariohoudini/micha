from django.urls import path

from .views import (
    CohortMatrixView, DataCatalogueView, MetricDefinitionView,
    PiiRegistryView, PlatformKpiView, QueryAnalyticsView,
    RealtimeDashboardView, ab_evaluate, access_grant,
    attribution_run, bandit_create, bandit_reward, bandit_select,
    c360_profile, churn_predict, cohort_compute,
    delivery_performance_report, dq_check_create, dq_run_all,
    etl_finish, etl_start, feature_define, feature_read,
    feature_write, fraud_loss_report, gdpr_audit_log,
    gmv_decompose, seller_report_generate,
)


urlpatterns = [
    # CH2 — realtime
    path('realtime/',                RealtimeDashboardView.as_view(), name='da-realtime'),
    # CH3 — seller reports
    path('seller-reports/generate/', seller_report_generate, name='da-seller-report'),
    # CH4 — cohorts
    path('cohorts/compute/',         cohort_compute, name='da-cohort-compute'),
    path('cohorts/matrix/',          CohortMatrixView.as_view(), name='da-cohort-matrix'),
    # CH5 — GMV decomposition
    path('gmv/decompose/',           gmv_decompose, name='da-gmv'),
    # CH6/7 — loss + delivery
    path('reports/fraud-loss/',      fraud_loss_report, name='da-fraud-loss'),
    path('reports/delivery/',        delivery_performance_report, name='da-delivery'),
    # CH8 — query analytics
    path('query-analytics/',         QueryAnalyticsView.as_view(), name='da-queries'),
    # CH9 — A/B
    path('ab/evaluate/',             ab_evaluate, name='da-ab'),
    # CH10 — ETL
    path('etl/start/',               etl_start, name='da-etl-start'),
    path('etl/finish/',              etl_finish, name='da-etl-finish'),
    # CH11 — semantic layer
    path('metrics/definitions/',     MetricDefinitionView.as_view(), name='da-metrics'),
    # CH12 — GDPR audit
    path('gdpr/audit/',              gdpr_audit_log, name='da-gdpr'),
    # CH13 — churn
    path('churn/predict/',           churn_predict, name='da-churn'),
    # CH15 — attribution
    path('attribution/run/',         attribution_run, name='da-attribution'),
    # CH16 — catalogue
    path('catalogue/',               DataCatalogueView.as_view(), name='da-catalogue'),
    # CH17 — data quality
    path('dq/checks/',               dq_check_create, name='da-dq-create'),
    path('dq/run/',                  dq_run_all, name='da-dq-run'),
    # CH18 — governance
    path('access/grant/',            access_grant, name='da-access'),
    # CH19 — PII registry
    path('pii/registry/',            PiiRegistryView.as_view(), name='da-pii'),
    # CH21 — feature store
    path('features/define/',         feature_define, name='da-feat-define'),
    path('features/write/',          feature_write, name='da-feat-write'),
    path('features/read/',           feature_read, name='da-feat-read'),
    # CH22 — bandit
    path('bandit/create/',           bandit_create, name='da-bandit-create'),
    path('bandit/select/',           bandit_select, name='da-bandit-select'),
    path('bandit/reward/',           bandit_reward, name='da-bandit-reward'),
    # CH23 — C360
    path('c360/',                    c360_profile, name='da-c360'),
    # CH24 — KPI
    path('admin/kpi/',               PlatformKpiView.as_view(), name='da-kpi'),
]
