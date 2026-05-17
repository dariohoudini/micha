from django.contrib import admin
from .models import GiftCard, GiftCardTransaction


@admin.register(GiftCard)
class GiftCardAdmin(admin.ModelAdmin):
    list_display = ('code_prefix', 'currency', 'initial_value',
                    'current_balance', 'status',
                    'purchased_by', 'claimed_by', 'expires_at', 'created_at')
    list_filter = ('status', 'currency')
    search_fields = ('code_prefix', 'purchased_by__email', 'claimed_by__email')
    readonly_fields = ('code_hash', 'code_prefix', 'created_at', 'updated_at',
                       'claimed_at')


@admin.register(GiftCardTransaction)
class GiftCardTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'card', 'kind', 'amount', 'balance_after',
                    'ref_type', 'ref_id', 'actor', 'created_at')
    list_filter = ('kind',)
    search_fields = ('card__code_prefix', 'ref_id', 'actor__email')
    readonly_fields = tuple(f.name for f in GiftCardTransaction._meta.fields)
