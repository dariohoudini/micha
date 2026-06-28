from django.contrib import admin

from .models import (
    ApiQuotaUsage, BroadcastDelivery, CommissionStatement,
    ListingQualityScore, PriceCompetitivenessSnapshot, ProductComplianceLabel,
    ProductQaVote, SellerBroadcast, SellerBulkEditJob,
    SellerBulkImportJob, SellerDisputeAppeal, SellerHolidayMode,
    SellerPayoutSchedule, SellerReturnPolicy, SellerToolsEvent,
    SellerToolsKpiSnapshot, SellerVatRegistration, StoreAccountLink,
    StoreFollower,
)


@admin.register(SellerBulkImportJob)
class SellerBulkImportJobAdmin(admin.ModelAdmin):
    list_display = ('seller', 'status', 'rows_total', 'rows_succeeded',
                    'rows_failed', 'created_at')
    list_filter = ('status',)


@admin.register(SellerBulkEditJob)
class SellerBulkEditJobAdmin(admin.ModelAdmin):
    list_display = ('seller', 'action_type', 'status', 'total', 'succeeded',
                    'failed', 'revertible_until', 'created_at')
    list_filter = ('action_type', 'status')


@admin.register(SellerReturnPolicy)
class SellerReturnPolicyAdmin(admin.ModelAdmin):
    list_display = ('seller', 'policy_name', 'applicable_to',
                    'return_window_days', 'return_shipping_paid_by',
                    'is_active')
    list_filter = ('applicable_to', 'return_shipping_paid_by', 'is_active')


@admin.register(SellerHolidayMode)
class SellerHolidayModeAdmin(admin.ModelAdmin):
    list_display = ('seller', 'enabled', 'start_date', 'end_date',
                    'auto_resumed')
    list_filter = ('enabled', 'auto_resumed')


@admin.register(ProductQaVote)
class ProductQaVoteAdmin(admin.ModelAdmin):
    list_display = ('qa_id', 'user', 'helpful', 'created_at')


@admin.register(StoreFollower)
class StoreFollowerAdmin(admin.ModelAdmin):
    list_display = ('seller', 'user', 'opt_out_broadcasts', 'followed_at')
    list_filter = ('opt_out_broadcasts',)


@admin.register(SellerBroadcast)
class SellerBroadcastAdmin(admin.ModelAdmin):
    list_display = ('seller', 'subject', 'status', 'recipients_count',
                    'delivered_count', 'open_count', 'click_count', 'sent_at')
    list_filter = ('status',)


@admin.register(BroadcastDelivery)
class BroadcastDeliveryAdmin(admin.ModelAdmin):
    list_display = ('broadcast', 'user', 'delivered', 'opened_at',
                    'clicked_at', 'reported_spam')
    list_filter = ('delivered', 'reported_spam')


@admin.register(CommissionStatement)
class CommissionStatementAdmin(admin.ModelAdmin):
    list_display = ('seller', 'reference_number', 'period_year',
                    'period_month', 'net_payout_cents', 'status')
    list_filter = ('status', 'period_year')


@admin.register(ListingQualityScore)
class ListingQualityScoreAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'seller', 'total_score', 'title_score',
                    'image_score', 'description_score', 'attribute_score',
                    'pricing_score', 'computed_at')


@admin.register(PriceCompetitivenessSnapshot)
class PriceCompetitivenessSnapshotAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'seller', 'seller_price_cents',
                    'market_median_cents', 'position_label', 'sample_size',
                    'computed_at')
    list_filter = ('position_label',)


@admin.register(SellerVatRegistration)
class SellerVatRegistrationAdmin(admin.ModelAdmin):
    list_display = ('seller', 'country', 'tax_type', 'registration_number',
                    'validation_status', 'price_display_mode', 'is_active')
    list_filter = ('validation_status', 'tax_type', 'price_display_mode')


@admin.register(StoreAccountLink)
class StoreAccountLinkAdmin(admin.ModelAdmin):
    list_display = ('owner', 'store_seller', 'role', 'approved', 'created_at')
    list_filter = ('role', 'approved')


@admin.register(SellerDisputeAppeal)
class SellerDisputeAppealAdmin(admin.ModelAdmin):
    list_display = ('dispute_id', 'seller', 'status', 'submitted_at',
                    'reviewed_at')
    list_filter = ('status',)


@admin.register(SellerPayoutSchedule)
class SellerPayoutScheduleAdmin(admin.ModelAdmin):
    list_display = ('seller', 'mode', 'weekday', 'min_amount_cents',
                    'express_release_eligible')
    list_filter = ('mode', 'express_release_eligible')


@admin.register(ProductComplianceLabel)
class ProductComplianceLabelAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'seller', 'label_type', 'label_value',
                    'verification_status', 'expiry_date')
    list_filter = ('label_type', 'verification_status')


@admin.register(ApiQuotaUsage)
class ApiQuotaUsageAdmin(admin.ModelAdmin):
    list_display = ('seller', 'usage_date', 'tier', 'calls_today',
                    'daily_quota', 'throttled_count')
    list_filter = ('tier',)


@admin.register(SellerToolsKpiSnapshot)
class SellerToolsKpiSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'bulk_import_success_pct',
                    'bulk_edit_success_pct', 'avg_listing_quality',
                    'qa_answer_rate_pct', 'price_competitive_pct')


@admin.register(SellerToolsEvent)
class SellerToolsEventAdmin(admin.ModelAdmin):
    list_display = ('kind', 'actor', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'actor', 'payload', 'created_at')
