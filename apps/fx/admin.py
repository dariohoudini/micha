from django.contrib import admin
from .models import FXRate, ConversionEvent


@admin.register(FXRate)
class FXRateAdmin(admin.ModelAdmin):
    list_display = ('source_currency', 'target_currency', 'rate', 'source',
                    'valid_from', 'valid_until', 'recorded_at')
    list_filter = ('source', 'source_currency', 'target_currency')
    search_fields = ('source_currency', 'target_currency')
    readonly_fields = ('recorded_at',)


@admin.register(ConversionEvent)
class ConversionEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'from_currency', 'to_currency', 'amount_from',
                    'amount_to', 'rate_applied', 'ref_type', 'ref_id',
                    'created_at')
    list_filter = ('from_currency', 'to_currency', 'ref_type')
    search_fields = ('ref_id', 'ref_type')
    readonly_fields = tuple(f.name for f in ConversionEvent._meta.fields)
