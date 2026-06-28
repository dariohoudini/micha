from django.contrib import admin

from .models import (
    AutoReplyLog, BulkExportJob, FulfilmentSLARecord, ListingComplianceViolation,
    ListingPublishState, ListingPublishTransition, ManualPriceOverride,
    PaymentHoldDispute, ProductCloneLog, RefundApprovalRequest, RepricingAction,
    RepricingRule, ReturnInspection, SellerActivationState, SellerAutoResponder,
    SellerBulkMessage, SellerCouponStackConfig, SellerIncomeTaxSummary,
    SellerInventoryAlertConfig, SellerMarketBenchmark, SellerOperationsEvent,
    SellerOperationsKpiSnapshot, SellerRecoveryPlan, SellerRefundPolicy,
    SellerSLAExcuse, SellerStaff, SellerStaffAuditLog,
    ShipmentCostReconciliation, StoreDesign,
)


@admin.register(SellerStaff)
class SellerStaffAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'seller', 'role', 'status',
                    'last_login_at')
    list_filter = ('role', 'status')
    search_fields = ('full_name', 'email')


@admin.register(SellerStaffAuditLog)
class SellerStaffAuditLogAdmin(admin.ModelAdmin):
    list_display = ('seller', 'staff', 'action_type', 'target_type',
                    'created_at')
    list_filter = ('action_type',)
    readonly_fields = [f.name for f in SellerStaffAuditLog._meta.fields]

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ListingPublishState)
class ListingPublishStateAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'seller', 'status', 'scheduled_publish_at',
                    'moderation_passed')
    list_filter = ('status', 'moderation_passed')


@admin.register(ListingPublishTransition)
class ListingPublishTransitionAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'from_status', 'to_status', 'reason',
                    'created_at')
    list_filter = ('to_status',)


@admin.register(RepricingRule)
class RepricingRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'seller', 'rule_type', 'enabled', 'priority',
                    'floor_price_cents', 'ceiling_price_cents')
    list_filter = ('rule_type', 'enabled', 'evaluation_frequency')


@admin.register(RepricingAction)
class RepricingActionAdmin(admin.ModelAdmin):
    list_display = ('rule', 'product_id', 'old_price_cents', 'new_price_cents',
                    'reason', 'created_at')


@admin.register(BulkExportJob)
class BulkExportJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'seller', 'kind', 'status', 'row_count', 'created_at')
    list_filter = ('kind', 'status')


@admin.register(ShipmentCostReconciliation)
class ShipmentCostReconciliationAdmin(admin.ModelAdmin):
    list_display = ('shipment_id', 'seller', 'reconciliation_status',
                    'difference_cents', 'seller_adjustment_cents', 'fault',
                    'contested')
    list_filter = ('reconciliation_status', 'fault', 'contested')


@admin.register(SellerAutoResponder)
class SellerAutoResponderAdmin(admin.ModelAdmin):
    list_display = ('seller', 'enabled', 'mode', 'delay_minutes', 'include_faq')
    list_filter = ('enabled', 'mode')


@admin.register(RefundApprovalRequest)
class RefundApprovalRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'seller', 'order_id', 'amount_cents', 'status',
                    'owner_escalated', 'admin_escalated', 'created_at')
    list_filter = ('status', 'owner_escalated', 'admin_escalated')


@admin.register(SellerRefundPolicy)
class SellerRefundPolicyAdmin(admin.ModelAdmin):
    list_display = ('seller', 'refund_approval_required',
                    'approval_threshold_cents', 'auto_approve_below_cents')


@admin.register(SellerIncomeTaxSummary)
class SellerIncomeTaxSummaryAdmin(admin.ModelAdmin):
    list_display = ('seller', 'year', 'gross_sales_cents', 'net_earnings_cents',
                    'iva_collected_cents', 'generated_at')
    list_filter = ('year',)


@admin.register(StoreDesign)
class StoreDesignAdmin(admin.ModelAdmin):
    list_display = ('store_id', 'seller', 'published', 'published_at')
    list_filter = ('published',)


@admin.register(FulfilmentSLARecord)
class FulfilmentSLARecordAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'seller', 'sla_deadline', 'picked_up_at',
                    'on_time', 'is_late', 'excused')
    list_filter = ('on_time', 'is_late', 'excused')


@admin.register(SellerSLAExcuse)
class SellerSLAExcuseAdmin(admin.ModelAdmin):
    list_display = ('seller', 'reason', 'date_from', 'date_to', 'status')
    list_filter = ('status',)


@admin.register(PaymentHoldDispute)
class PaymentHoldDisputeAdmin(admin.ModelAdmin):
    list_display = ('id', 'seller', 'payout_id', 'hold_reason', 'status',
                    'escalated_head_finance', 'created_at')
    list_filter = ('status', 'escalated_head_finance')


@admin.register(ListingComplianceViolation)
class ListingComplianceViolationAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'seller', 'issue_type', 'severity', 'status',
                    'deadline')
    list_filter = ('issue_type', 'severity', 'status')


@admin.register(SellerActivationState)
class SellerActivationStateAdmin(admin.ModelAdmin):
    list_display = ('seller', 'activated', 'activated_at', 'badge_expires_at')
    list_filter = ('activated',)


@admin.register(SellerRecoveryPlan)
class SellerRecoveryPlanAdmin(admin.ModelAdmin):
    list_display = ('id', 'seller', 'suspension_type', 'status', 'created_at',
                    'decided_at')
    list_filter = ('suspension_type', 'status')


@admin.register(SellerMarketBenchmark)
class SellerMarketBenchmarkAdmin(admin.ModelAdmin):
    list_display = ('category_id', 'week_start', 'median_price_cents',
                    'price_min_cents', 'price_max_cents')
    list_filter = ('week_start',)


@admin.register(ReturnInspection)
class ReturnInspectionAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'seller', 'condition', 'action', 'restocked',
                    'created_at')
    list_filter = ('condition', 'action', 'restocked')


@admin.register(SellerBulkMessage)
class SellerBulkMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'seller', 'scope', 'status', 'recipient_count',
                    'created_at')
    list_filter = ('scope', 'status')


@admin.register(SellerOperationsKpiSnapshot)
class SellerOperationsKpiSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'activation_rate_pct',
                    'on_time_fulfilment_pct', 'refund_approval_sla_pct',
                    'open_compliance_violations')


@admin.register(SellerOperationsEvent)
class SellerOperationsEventAdmin(admin.ModelAdmin):
    list_display = ('kind', 'actor', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'actor', 'payload', 'created_at')


admin.site.register(AutoReplyLog)
admin.site.register(ManualPriceOverride)
admin.site.register(ProductCloneLog)
admin.site.register(SellerCouponStackConfig)
admin.site.register(SellerInventoryAlertConfig)
