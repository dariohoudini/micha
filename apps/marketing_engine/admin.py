from django.contrib import admin

from .models import (
    AdCampaign, AdClick, AdGroup, AdImpression, AdKeyword,
    AdSpendLog, BundleDeal, CoMarketingCampaign, CoMarketingPartner,
    CreatorAccount, CreatorCampaign, EmailMarketingCampaign,
    FlashSaleApplication, FlashSaleItem, FlashSaleReservation,
    FreeGiftPromotion, MarketingEvent, MarketingKpiSnapshot,
    MarketingSegment, MePromotion, PixelEvent, PromoGame,
    PromoGamePrize, PromoGameSpin, PromotionAbuseSignal,
    PromotionLift, PromotionUsage, PushCampaignVariant,
    PushMarketingCampaign, SegmentMembership, ShareScratchEvent,
    SmsCampaign, SmsOptIn, SuperDealsCampaign, SuperDealsEnrolment,
    VolumeDiscount,
)


@admin.register(MePromotion)
class MePromotionAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'status', 'discount_type',
                    'discount_value', 'valid_until', 'uses_count')
    list_filter = ('type', 'status', 'funded_by')


@admin.register(PromotionUsage)
class PromotionUsageAdmin(admin.ModelAdmin):
    list_display = ('promotion', 'user', 'order_id',
                    'discount_amount', 'used_at')


@admin.register(FlashSaleApplication)
class FlashSaleApplicationAdmin(admin.ModelAdmin):
    list_display = ('event_slug', 'seller', 'status',
                    'auto_validation_passed', 'submitted_at')
    list_filter = ('status', 'auto_validation_passed')


@admin.register(FlashSaleItem)
class FlashSaleItemAdmin(admin.ModelAdmin):
    list_display = ('event_slug', 'product_id', 'allocated_qty',
                    'sold_qty', 'reserved_qty', 'flash_price')


@admin.register(FlashSaleReservation)
class FlashSaleReservationAdmin(admin.ModelAdmin):
    list_display = ('item', 'user', 'quantity', 'status', 'expires_at')
    list_filter = ('status',)


@admin.register(BundleDeal)
class BundleDealAdmin(admin.ModelAdmin):
    list_display = ('name', 'seller', 'bundle_type', 'status',
                    'claims_count', 'valid_until')
    list_filter = ('bundle_type', 'status')


@admin.register(VolumeDiscount)
class VolumeDiscountAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'seller', 'status', 'valid_until')
    list_filter = ('status',)


@admin.register(FreeGiftPromotion)
class FreeGiftPromotionAdmin(admin.ModelAdmin):
    list_display = ('seller', 'qualifying_product_id',
                    'gift_product_id', 'gift_stock_remaining',
                    'status')
    list_filter = ('status',)


@admin.register(PromoGame)
class PromoGameAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'event_slug', 'status',
                    'spins_per_user_per_day', 'valid_until')
    list_filter = ('type', 'status')


@admin.register(PromoGamePrize)
class PromoGamePrizeAdmin(admin.ModelAdmin):
    list_display = ('game', 'prize_type', 'label', 'probability',
                    'stock', 'stock_remaining')


@admin.register(PromoGameSpin)
class PromoGameSpinAdmin(admin.ModelAdmin):
    list_display = ('user', 'game', 'outcome_label',
                    'was_extra_spin', 'spun_at')


@admin.register(ShareScratchEvent)
class ShareScratchEventAdmin(admin.ModelAdmin):
    list_display = ('sharer', 'game', 'share_token',
                    'referee', 'converted_at')


@admin.register(CreatorAccount)
class CreatorAccountAdmin(admin.ModelAdmin):
    list_display = ('handle', 'tier', 'followers_count',
                    'engagement_rate', 'status')
    list_filter = ('tier', 'status')


@admin.register(CreatorCampaign)
class CreatorCampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'creator', 'tracking_code',
                    'clicks', 'conversions', 'gmv_generated')


@admin.register(AdCampaign)
class AdCampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'seller', 'status', 'daily_budget',
                    'daily_spend', 'total_spend', 'pacing_multiplier')
    list_filter = ('status', 'objective')


@admin.register(AdGroup)
class AdGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'campaign', 'product_id',
                    'bid_amount', 'quality_score', 'status')


@admin.register(AdKeyword)
class AdKeywordAdmin(admin.ModelAdmin):
    list_display = ('ad_group', 'keyword', 'match_type', 'bid_override')


@admin.register(AdImpression)
class AdImpressionAdmin(admin.ModelAdmin):
    list_display = ('ad_group', 'user', 'placement', 'cpm_cost',
                    'occurred_at')


@admin.register(AdClick)
class AdClickAdmin(admin.ModelAdmin):
    list_display = ('ad_group', 'user', 'cpc_cost',
                    'converted', 'conversion_value', 'occurred_at')


@admin.register(AdSpendLog)
class AdSpendLogAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'kind', 'amount',
                    'currency', 'occurred_at')


@admin.register(PixelEvent)
class PixelEventAdmin(admin.ModelAdmin):
    list_display = ('provider', 'event_name', 'user',
                    'status', 'attempt_count', 'occurred_at')
    list_filter = ('provider', 'status', 'event_name')


@admin.register(MarketingSegment)
class MarketingSegmentAdmin(admin.ModelAdmin):
    list_display = ('slug', 'name', 'estimated_size',
                    'last_materialised_at')


@admin.register(SegmentMembership)
class SegmentMembershipAdmin(admin.ModelAdmin):
    list_display = ('segment', 'user', 'snapshot_at')


@admin.register(EmailMarketingCampaign)
class EmailMarketingCampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'segment', 'template_key',
                    'status', 'sent_count', 'opened_count')


@admin.register(SmsOptIn)
class SmsOptInAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'opted_in',
                    'opted_in_at', 'opted_out_at')


@admin.register(SmsCampaign)
class SmsCampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'segment', 'status',
                    'sent_count', 'suppressed_count')


@admin.register(PushMarketingCampaign)
class PushMarketingCampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'segment', 'ab_split_pct', 'status',
                    'sent_count', 'winner_variant')


@admin.register(PushCampaignVariant)
class PushCampaignVariantAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'variant_key',
                    'sent_count', 'opened_count')


@admin.register(SuperDealsCampaign)
class SuperDealsCampaignAdmin(admin.ModelAdmin):
    list_display = ('slug', 'name', 'status',
                    'starts_at', 'ends_at', 'discount_floor_pct')


@admin.register(SuperDealsEnrolment)
class SuperDealsEnrolmentAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'seller', 'status', 'created_at')


@admin.register(CoMarketingPartner)
class CoMarketingPartnerAdmin(admin.ModelAdmin):
    list_display = ('name', 'industry', 'country',
                    'contact_email', 'is_active')


@admin.register(CoMarketingCampaign)
class CoMarketingCampaignAdmin(admin.ModelAdmin):
    list_display = ('name', 'partner', 'status',
                    'starts_at', 'ends_at', 'revenue_attributed')


@admin.register(PromotionLift)
class PromotionLiftAdmin(admin.ModelAdmin):
    list_display = ('promotion', 'window_start', 'window_end',
                    'incremental_gmv', 'roi')


@admin.register(PromotionAbuseSignal)
class PromotionAbuseSignalAdmin(admin.ModelAdmin):
    list_display = ('user', 'promotion', 'kind',
                    'severity', 'action_taken', 'detected_at')
    list_filter = ('kind',)


@admin.register(MarketingKpiSnapshot)
class MarketingKpiSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'total_promotions_active',
                    'total_promo_redemptions', 'total_discount_given',
                    'ad_spend', 'creator_gmv')


@admin.register(MarketingEvent)
class MarketingEventAdmin(admin.ModelAdmin):
    list_display = ('kind', 'user', 'actor', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'payload', 'created_at', 'user', 'actor')
