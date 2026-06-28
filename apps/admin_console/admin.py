from django.contrib import admin

from .models import (
    AdminBanner, AdminConsoleEvent, AdminExperiment, AdminKpiSnapshot,
    AdminRoleAssignment, AdminAuditEntry, ApprovalRequest, DataExportRequest,
    FeeSchedule, KillSwitch, LawEnforcementRequest, LegalHold,
    PayoutAdjustment, PayoutHold, PersonalisationConfig, PlatformAlert,
    PlatformIncident, PlatformSetting, PlatformSettingHistory, ServiceStatus,
)


@admin.register(AdminRoleAssignment)
class AdminRoleAssignmentAdmin(admin.ModelAdmin):
    list_display = ('admin', 'level', 'function', 'is_active', 'updated_at')
    list_filter = ('level', 'is_active', 'function')


@admin.register(ApprovalRequest)
class ApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ('kind', 'submitted_by', 'reviewed_by', 'status',
                    'created_at', 'expires_at')
    list_filter = ('kind', 'status')


@admin.register(AdminAuditEntry)
class AdminAuditEntryAdmin(admin.ModelAdmin):
    list_display = ('action_type', 'admin', 'admin_level', 'target_type',
                    'target_id', 'result', 'created_at')
    list_filter = ('result', 'action_type')
    readonly_fields = [f.name for f in AdminAuditEntry._meta.fields]

    def has_delete_permission(self, request, obj=None):
        return False  # immutable

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PersonalisationConfig)
class PersonalisationConfigAdmin(admin.ModelAdmin):
    list_display = ('version', 'is_live', 'created_by', 'deployed_at')
    list_filter = ('is_live',)


@admin.register(AdminExperiment)
class AdminExperimentAdmin(admin.ModelAdmin):
    list_display = ('name', 'status', 'decision', 'traffic_allocation_pct',
                    'primary_metric', 'created_at')
    list_filter = ('status', 'decision')


@admin.register(FeeSchedule)
class FeeScheduleAdmin(admin.ModelAdmin):
    list_display = ('category_name', 'current_rate_pct', 'new_rate_pct',
                    'change_type', 'effective_date', 'status')
    list_filter = ('change_type', 'status', 'is_emergency')


@admin.register(PlatformSetting)
class PlatformSettingAdmin(admin.ModelAdmin):
    list_display = ('key', 'version', 'updated_by', 'updated_at')


@admin.register(PlatformSettingHistory)
class PlatformSettingHistoryAdmin(admin.ModelAdmin):
    list_display = ('setting_key', 'version', 'changed_by', 'changed_at')


@admin.register(KillSwitch)
class KillSwitchAdmin(admin.ModelAdmin):
    list_display = ('key', 'is_engaged', 'engaged_by', 'engaged_at')
    list_filter = ('is_engaged',)


@admin.register(DataExportRequest)
class DataExportRequestAdmin(admin.ModelAdmin):
    list_display = ('dataset', 'requested_by', 'is_pii', 'status',
                    'created_at')
    list_filter = ('dataset', 'is_pii', 'status')


@admin.register(LegalHold)
class LegalHoldAdmin(admin.ModelAdmin):
    list_display = ('hold_ref', 'subject_type', 'subject_id', 'legal_basis',
                    'status', 'placed_by', 'expires_at')
    list_filter = ('subject_type', 'legal_basis', 'status')


@admin.register(LawEnforcementRequest)
class LawEnforcementRequestAdmin(admin.ModelAdmin):
    list_display = ('request_ref', 'request_type', 'authority', 'status',
                    'received_at')
    list_filter = ('request_type', 'status')


@admin.register(PayoutHold)
class PayoutHoldAdmin(admin.ModelAdmin):
    list_display = ('payout_request_id', 'seller', 'reason', 'status',
                    'placed_by', 'placed_at')
    list_filter = ('reason', 'status')


@admin.register(PayoutAdjustment)
class PayoutAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('seller', 'kind', 'amount_cents', 'created_by',
                    'created_at')
    list_filter = ('kind',)


@admin.register(AdminBanner)
class AdminBannerAdmin(admin.ModelAdmin):
    list_display = ('slot', 'headline', 'status', 'priority',
                    'is_paid_placement', 'go_live_at')
    list_filter = ('slot', 'status', 'is_paid_placement')


@admin.register(PlatformAlert)
class PlatformAlertAdmin(admin.ModelAdmin):
    list_display = ('alert_type', 'severity', 'status', 'audience',
                    'published_at')
    list_filter = ('alert_type', 'severity', 'status')


@admin.register(ServiceStatus)
class ServiceStatusAdmin(admin.ModelAdmin):
    list_display = ('service_name', 'state', 'latency_p99_ms',
                    'error_rate_pct', 'updated_at')
    list_filter = ('state',)


@admin.register(PlatformIncident)
class PlatformIncidentAdmin(admin.ModelAdmin):
    list_display = ('title', 'severity', 'affected_service', 'status',
                    'started_at', 'resolved_at')
    list_filter = ('severity', 'status')


@admin.register(AdminKpiSnapshot)
class AdminKpiSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'take_rate_pct', 'active_experiments',
                    'pending_approvals', 'active_incidents',
                    'dual_approval_compliance_pct')


@admin.register(AdminConsoleEvent)
class AdminConsoleEventAdmin(admin.ModelAdmin):
    list_display = ('kind', 'actor', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'actor', 'payload', 'created_at')
