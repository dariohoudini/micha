from django.contrib import admin

from .models import (
    AcquisitionChannelSpend, BuyerAttributionTouch, BirthdayReward,
    BrowseAbandonmentSignal, BuyerKpiSnapshot, BuyerLTV,
    DormancyState, EmailLifecycleLog, EngagementEvent,
    FirstPurchaseTrigger, HomeFeedPersonalisation,
    MembershipBillingLog, MessageTemplate, PremiumMembership,
    PushDecision, RecoverySequenceState, ReferralActivation,
    SeasonalCampaign, SeasonalCampaignParticipant, SocialShareEvent,
    ViralLoopAttribution, WelcomeIncentive, WinBackCampaignRun,
)


@admin.register(MessageTemplate)
class MessageTemplateAdmin(admin.ModelAdmin):
    list_display = ('key', 'kind', 'locale', 'subject',
                    'is_active', 'updated_at')
    list_filter = ('kind', 'locale', 'is_active')
    search_fields = ('key', 'subject')


@admin.register(AcquisitionChannelSpend)
class AcquisitionChannelSpendAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'channel', 'country',
                    'spend_usd', 'clicks', 'installs', 'first_purchases')
    list_filter = ('channel', 'country')


@admin.register(BuyerAttributionTouch)
class BuyerAttributionTouchAdmin(admin.ModelAdmin):
    list_display = ('attribution_id', 'stage', 'user', 'channel',
                    'utm_campaign', 'occurred_at')
    list_filter = ('stage', 'channel')
    search_fields = ('attribution_id', 'utm_source', 'utm_campaign')


@admin.register(WelcomeIncentive)
class WelcomeIncentiveAdmin(admin.ModelAdmin):
    list_display = ('user', 'coupon_code', 'amount', 'currency',
                    'status', 'expires_at')
    list_filter = ('status', 'currency')


@admin.register(FirstPurchaseTrigger)
class FirstPurchaseTriggerAdmin(admin.ModelAdmin):
    list_display = ('user', 'order_id', 'status',
                    'purchased_at', 'verified_at')
    list_filter = ('status',)


@admin.register(ReferralActivation)
class ReferralActivationAdmin(admin.ModelAdmin):
    list_display = ('referrer_user', 'referee_user', 'stage',
                    'referral_code', 'fraud_score', 'occurred_at')
    list_filter = ('stage',)


@admin.register(PremiumMembership)
class PremiumMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'status', 'auto_renew',
                    'current_period_end', 'failed_charge_count')
    list_filter = ('plan', 'status', 'auto_renew')


@admin.register(MembershipBillingLog)
class MembershipBillingLogAdmin(admin.ModelAdmin):
    list_display = ('membership', 'amount', 'currency',
                    'status', 'failure_code', 'attempted_at')
    list_filter = ('status',)


@admin.register(RecoverySequenceState)
class RecoverySequenceStateAdmin(admin.ModelAdmin):
    list_display = ('user', 'kind', 'current_step', 'total_steps',
                    'status', 'next_message_at')
    list_filter = ('kind', 'status')


@admin.register(BrowseAbandonmentSignal)
class BrowseAbandonmentSignalAdmin(admin.ModelAdmin):
    list_display = ('user', 'primary_category_id',
                    'high_intent', 'notified', 'created_at')
    list_filter = ('high_intent', 'notified')


@admin.register(DormancyState)
class DormancyStateAdmin(admin.ModelAdmin):
    list_display = ('user', 'band', 'days_since_last_purchase',
                    'lifetime_orders', 'lifetime_gmv', 'updated_at')
    list_filter = ('band',)


@admin.register(WinBackCampaignRun)
class WinBackCampaignRunAdmin(admin.ModelAdmin):
    list_display = ('user', 'band', 'template_key',
                    'outcome', 'sent_at')
    list_filter = ('band', 'outcome', 'template_key')


@admin.register(PushDecision)
class PushDecisionAdmin(admin.ModelAdmin):
    list_display = ('user', 'push_type', 'decision', 'reason', 'occurred_at')
    list_filter = ('decision', 'push_type')


@admin.register(EmailLifecycleLog)
class EmailLifecycleLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'stage', 'template_key',
                    'status', 'queued_at')
    list_filter = ('stage', 'status')


@admin.register(HomeFeedPersonalisation)
class HomeFeedPersonalisationAdmin(admin.ModelAdmin):
    list_display = ('user', 'experiment_id', 'created_at')


@admin.register(BirthdayReward)
class BirthdayRewardAdmin(admin.ModelAdmin):
    list_display = ('user', 'birthday_year', 'coupon_code',
                    'coins_granted', 'sent_at', 'used_at')


@admin.register(SeasonalCampaign)
class SeasonalCampaignAdmin(admin.ModelAdmin):
    list_display = ('slug', 'name', 'status',
                    'starts_at', 'ends_at', 'discount_pct')
    list_filter = ('status',)


@admin.register(SeasonalCampaignParticipant)
class SeasonalCampaignParticipantAdmin(admin.ModelAdmin):
    list_display = ('campaign', 'user', 'auto_enrolled',
                    'orders_during_campaign', 'gmv_during_campaign')


@admin.register(SocialShareEvent)
class SocialShareEventAdmin(admin.ModelAdmin):
    list_display = ('sharer', 'share_target', 'shared_entity',
                    'entity_id', 'short_code', 'clicks', 'conversions')
    list_filter = ('share_target', 'shared_entity')


@admin.register(ViralLoopAttribution)
class ViralLoopAttributionAdmin(admin.ModelAdmin):
    list_display = ('share_event', 'converted_user',
                    'conversion_kind', 'occurred_at')


@admin.register(BuyerLTV)
class BuyerLTVAdmin(admin.ModelAdmin):
    list_display = ('user', 'segment', 'realised_lifetime',
                    'predicted_next_12m', 'confidence',
                    'rfm_recency', 'rfm_frequency', 'rfm_monetary')
    list_filter = ('segment',)


@admin.register(BuyerKpiSnapshot)
class BuyerKpiSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'new_users', 'new_buyers',
                    'activation_rate', 'repeat_buyer_rate',
                    'dormant_population')


@admin.register(EngagementEvent)
class EngagementEventAdmin(admin.ModelAdmin):
    list_display = ('kind', 'user', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'payload', 'created_at', 'user')
    search_fields = ('kind',)
