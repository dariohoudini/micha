from django.urls import path

from . import views

app_name = 'mobile_app'

urlpatterns = [
    # CH11 biometrics
    path('biometrics/register/', views.BiometricRegisterView.as_view(),
         name='biometric-register'),
    path('biometrics/challenge/', views.BiometricChallengeView.as_view(),
         name='biometric-challenge'),
    path('biometrics/verify/', views.BiometricVerifyView.as_view(),
         name='biometric-verify'),
    path('biometrics/status/', views.BiometricStatusView.as_view(),
         name='biometric-status'),
    # CH4 offline sync replay audit
    path('sync/replay/', views.SyncReplayView.as_view(), name='sync-replay'),
    # CH19 crash reporting
    path('crashes/', views.CrashIngestView.as_view(), name='crash-ingest'),
    path('crashes/groups/', views.CrashGroupListView.as_view(),
         name='crash-groups'),
    # CH20 analytics batch
    path('events/batch/', views.EventBatchView.as_view(), name='event-batch'),
    # CH21 experiments (client-side eval)
    path('experiments/config/', views.ExperimentConfigView.as_view(),
         name='experiment-config'),
    path('experiments/exposure/', views.ExperimentExposureView.as_view(),
         name='experiment-exposure'),
    # CH22 deferred deep links
    path('deeplinks/deferred/', views.DeferredLinkCreateView.as_view(),
         name='deeplink-create'),
    path('deeplinks/claim/', views.DeferredLinkClaimView.as_view(),
         name='deeplink-claim'),
    # CH24 releases + RUM + KPIs
    path('releases/latest/', views.ReleaseLatestView.as_view(),
         name='release-latest'),
    path('releases/', views.ReleaseRegisterView.as_view(),
         name='release-register'),
    path('perf/batch/', views.PerfBatchView.as_view(), name='perf-batch'),
    path('kpis/', views.MobileKpiView.as_view(), name='kpis'),
]
