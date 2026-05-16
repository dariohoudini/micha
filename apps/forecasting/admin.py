from django.contrib import admin
from .models import DailyDemand, DemandForecast, ReorderRecommendation


@admin.register(DailyDemand)
class DailyDemandAdmin(admin.ModelAdmin):
    list_display = ('product', 'day', 'units', 'revenue')
    list_filter = ('day',)
    search_fields = ('product__title',)


@admin.register(DemandForecast)
class DemandForecastAdmin(admin.ModelAdmin):
    list_display = ('product', 'horizon_days', 'predicted_units',
                    'daily_mean', 'daily_stddev', 'method',
                    'sample_size', 'generated_at')
    list_filter = ('method',)
    search_fields = ('product__title',)


@admin.register(ReorderRecommendation)
class ReorderRecommendationAdmin(admin.ModelAdmin):
    list_display = ('product', 'current_stock', 'reorder_point',
                    'recommended_qty', 'action', 'generated_at')
    list_filter = ('action',)
    search_fields = ('product__title',)
