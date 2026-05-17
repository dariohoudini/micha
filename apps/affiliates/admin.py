from django.contrib import admin
from .models import (AffiliateProgram, AffiliateAccount, AffiliateClick,
                       AffiliateConversion, AffiliatePayout)


@admin.register(AffiliateProgram)
class AffiliateProgramAdmin(admin.ModelAdmin):
    list_display = ('name', 'default_commission_rate',
                    'attribution_window_days', 'hold_period_days',
                    'min_payout_aoa', 'is_active')
    list_filter = ('is_active',)


@admin.register(AffiliateAccount)
class AffiliateAccountAdmin(admin.ModelAdmin):
    list_display = ('user', 'program', 'code', 'tier_multiplier',
                    'is_active', 'total_earned_aoa')
    search_fields = ('user__email', 'code')
    list_filter = ('program', 'is_active')


@admin.register(AffiliateClick)
class AffiliateClickAdmin(admin.ModelAdmin):
    list_display = ('id', 'account', 'user', 'created_at')
    search_fields = ('account__code', 'session_token')


@admin.register(AffiliateConversion)
class AffiliateConversionAdmin(admin.ModelAdmin):
    list_display = ('id', 'account', 'order_id', 'commission_amount',
                    'status', 'created_at', 'confirmed_at', 'paid_at')
    list_filter = ('status',)
    search_fields = ('account__code', 'order_id')
    readonly_fields = tuple(f.name for f in AffiliateConversion._meta.fields)


@admin.register(AffiliatePayout)
class AffiliatePayoutAdmin(admin.ModelAdmin):
    list_display = ('id', 'account', 'amount_aoa', 'conversion_count',
                    'status', 'paid_at', 'created_at')
    list_filter = ('status',)
