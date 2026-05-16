from django.contrib import admin
from .models import TaxJurisdiction, TaxRate, TaxCategoryRule, TaxCalculation


@admin.register(TaxJurisdiction)
class TaxJurisdictionAdmin(admin.ModelAdmin):
    list_display = ('id', 'country_code', 'province_code', 'name', 'is_active')
    list_filter = ('country_code', 'is_active')
    search_fields = ('country_code', 'province_code', 'name')


@admin.register(TaxRate)
class TaxRateAdmin(admin.ModelAdmin):
    list_display = ('jurisdiction', 'name', 'rate', 'source',
                    'valid_from', 'valid_until')
    list_filter = ('source',)
    search_fields = ('jurisdiction__country_code', 'jurisdiction__name')


@admin.register(TaxCategoryRule)
class TaxCategoryRuleAdmin(admin.ModelAdmin):
    list_display = ('jurisdiction', 'category', 'multiplier')
    list_filter = ('category',)


@admin.register(TaxCalculation)
class TaxCalculationAdmin(admin.ModelAdmin):
    list_display = ('id', 'ref_type', 'ref_id', 'jurisdiction',
                    'rate_applied', 'total_tax', 'created_at')
    list_filter = ('ref_type',)
    search_fields = ('ref_id',)
    readonly_fields = tuple(f.name for f in TaxCalculation._meta.fields)
