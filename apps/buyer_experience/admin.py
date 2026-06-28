from django.contrib import admin

from .models import (
    AgeVerification, BulkInquiry, BuyerExperienceEvent,
    BuyerExperienceKpiSnapshot, OrderGiftOptions, PrePurchaseQuestion,
    ProductPriceHistory, ProductSubscription, RestrictedCategory,
    SavedComparison, WishlistPriceWatch,
)


@admin.register(OrderGiftOptions)
class OrderGiftOptionsAdmin(admin.ModelAdmin):
    list_display = ('order_id', 'buyer', 'is_gift', 'gift_wrap', 'hide_price',
                    'gift_wrap_fee_cents')
    list_filter = ('is_gift', 'gift_wrap', 'hide_price')


@admin.register(ProductSubscription)
class ProductSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('buyer', 'product_id', 'frequency_days', 'discount_pct',
                    'next_order_date', 'status', 'total_orders')
    list_filter = ('status', 'frequency_days')


@admin.register(ProductPriceHistory)
class ProductPriceHistoryAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'sku_id', 'price_cents', 'change_reason',
                    'recorded_at')
    list_filter = ('change_reason',)
    search_fields = ('product_id', 'sku_id')
    readonly_fields = [f.name for f in ProductPriceHistory._meta.fields]

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(PrePurchaseQuestion)
class PrePurchaseQuestionAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'buyer', 'seller', 'status',
                    'moderation_flag', 'created_at', 'answered_at')
    list_filter = ('status', 'moderation_flag')


@admin.register(BulkInquiry)
class BulkInquiryAdmin(admin.ModelAdmin):
    list_display = ('buyer', 'seller', 'product_id', 'quantity', 'purpose',
                    'status', 'seller_quote_cents', 'created_at')
    list_filter = ('status', 'purpose')


@admin.register(SavedComparison)
class SavedComparisonAdmin(admin.ModelAdmin):
    list_display = ('buyer', 'name', 'share_code', 'created_at')


@admin.register(WishlistPriceWatch)
class WishlistPriceWatchAdmin(admin.ModelAdmin):
    list_display = ('buyer', 'product_id', 'price_at_add_cents',
                    'threshold_pct', 'alert_enabled', 'last_alerted_at')
    list_filter = ('alert_enabled',)


@admin.register(RestrictedCategory)
class RestrictedCategoryAdmin(admin.ModelAdmin):
    list_display = ('category_id', 'category_name', 'restriction_type',
                    'min_age', 'requires_delivery_check', 'is_active')
    list_filter = ('restriction_type', 'is_active')


@admin.register(AgeVerification)
class AgeVerificationAdmin(admin.ModelAdmin):
    list_display = ('buyer', 'age_verified', 'method', 'verified_at',
                    'expires_at')
    list_filter = ('age_verified', 'method')


@admin.register(BuyerExperienceKpiSnapshot)
class BuyerExperienceKpiSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'subscribe_save_retention_pct',
                    'review_photo_pct', 'active_subscriptions',
                    'pending_bulk_inquiries', 'pending_questions')


@admin.register(BuyerExperienceEvent)
class BuyerExperienceEventAdmin(admin.ModelAdmin):
    list_display = ('kind', 'actor', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'actor', 'payload', 'created_at')
