from django.contrib import admin

from .models import (
    AppRelease, BiometricChallenge, BiometricCredential,
    BiometricPaymentToken, ClientPerfMetric, CrashEvent, CrashGroup,
    DeferredDeepLink, MobileAnalyticsEvent, MobileEngineeringEvent,
    MobileEventBatch, MobileExperiment, MobileKpiSnapshot,
    OfflineSyncReplay, SilentPushDispatch,
)


@admin.register(BiometricCredential)
class BiometricCredentialAdmin(admin.ModelAdmin):
    list_display = ('user', 'device_fingerprint', 'algorithm', 'platform',
                    'biometry_type', 'status', 'last_used_at')
    list_filter = ('algorithm', 'platform', 'status')


@admin.register(BiometricChallenge)
class BiometricChallengeAdmin(admin.ModelAdmin):
    list_display = ('user', 'purpose', 'status', 'attempts', 'issued_at',
                    'expires_at')
    list_filter = ('purpose', 'status')


@admin.register(BiometricPaymentToken)
class BiometricPaymentTokenAdmin(admin.ModelAdmin):
    list_display = ('user', 'order_ref', 'consumed', 'expires_at')
    list_filter = ('consumed',)


@admin.register(OfflineSyncReplay)
class OfflineSyncReplayAdmin(admin.ModelAdmin):
    list_display = ('user', 'action_type', 'status', 'retry_count',
                    'replayed_at')
    list_filter = ('action_type', 'status')


@admin.register(SilentPushDispatch)
class SilentPushDispatchAdmin(admin.ModelAdmin):
    list_display = ('user', 'push_type', 'status', 'devices_sent',
                    'created_at', 'sent_at')
    list_filter = ('push_type', 'status')


@admin.register(CrashGroup)
class CrashGroupAdmin(admin.ModelAdmin):
    list_display = ('error_type', 'error_message', 'platform',
                    'events_count', 'users_affected', 'status', 'last_seen')
    list_filter = ('status', 'platform')


@admin.register(CrashEvent)
class CrashEventAdmin(admin.ModelAdmin):
    list_display = ('group', 'user', 'platform', 'app_version',
                    'device_model', 'received_at')
    list_filter = ('platform',)


@admin.register(MobileAnalyticsEvent)
class MobileAnalyticsEventAdmin(admin.ModelAdmin):
    list_display = ('event_name', 'user', 'platform', 'app_version',
                    'network_type', 'event_time')
    list_filter = ('platform', 'network_type')
    search_fields = ('event_name', 'session_id')


@admin.register(MobileEventBatch)
class MobileEventBatchAdmin(admin.ModelAdmin):
    list_display = ('user', 'events_received', 'events_accepted',
                    'events_duplicate', 'events_rejected', 'received_at')


@admin.register(MobileExperiment)
class MobileExperimentAdmin(admin.ModelAdmin):
    list_display = ('slug', 'name', 'status', 'traffic_allocation',
                    'platform', 'updated_at')
    list_filter = ('status', 'platform')


@admin.register(DeferredDeepLink)
class DeferredDeepLinkAdmin(admin.ModelAdmin):
    list_display = ('token', 'target_path', 'campaign', 'status',
                    'claimed_by', 'expires_at')
    list_filter = ('status',)


@admin.register(AppRelease)
class AppReleaseAdmin(admin.ModelAdmin):
    list_display = ('platform', 'version', 'build_number', 'js_bundle_kb',
                    'binary_size_mb', 'rollout_pct', 'is_mandatory',
                    'released_at')
    list_filter = ('platform',)


@admin.register(ClientPerfMetric)
class ClientPerfMetricAdmin(admin.ModelAdmin):
    list_display = ('metric', 'value', 'platform', 'app_version',
                    'device_class', 'screen', 'recorded_at')
    list_filter = ('metric', 'platform', 'device_class')


@admin.register(MobileKpiSnapshot)
class MobileKpiSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'cold_start_p95_ms', 'crash_rate_pct',
                    'api_success_pct', 'checkout_completion_pct',
                    'biometric_success_pct', 'offline_sync_success_pct',
                    'dau')


@admin.register(MobileEngineeringEvent)
class MobileEngineeringEventAdmin(admin.ModelAdmin):
    list_display = ('kind', 'actor', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'actor', 'payload', 'created_at')
