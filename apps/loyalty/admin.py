from django.contrib import admin
from .models import Tier, TierBenefit, UserTier, PointsTransaction


@admin.register(Tier)
class TierAdmin(admin.ModelAdmin):
    list_display = ('rank', 'code', 'name', 'spend_threshold',
                    'points_multiplier', 'is_active')
    list_filter = ('is_active',)
    ordering = ('rank',)


@admin.register(TierBenefit)
class TierBenefitAdmin(admin.ModelAdmin):
    list_display = ('tier', 'kind', 'value', 'is_active')
    list_filter = ('kind', 'is_active', 'tier')


@admin.register(UserTier)
class UserTierAdmin(admin.ModelAdmin):
    list_display = ('user', 'tier', 'qualifying_spend',
                    'achieved_at', 'last_recomputed_at')
    list_filter = ('tier',)
    search_fields = ('user__email',)


@admin.register(PointsTransaction)
class PointsTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'delta', 'reason', 'balance_after',
                    'ref_type', 'ref_id', 'created_at')
    list_filter = ('reason',)
    search_fields = ('user__email', 'ref_id')
    readonly_fields = tuple(f.name for f in PointsTransaction._meta.fields)
