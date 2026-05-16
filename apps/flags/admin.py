from django.contrib import admin
from .models import Flag, FlagOverride, ExperimentExposure


@admin.register(Flag)
class FlagAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'is_active', 'updated_at')
    list_filter = ('kind', 'is_active')
    search_fields = ('name', 'description')


@admin.register(FlagOverride)
class FlagOverrideAdmin(admin.ModelAdmin):
    list_display = ('flag', 'user', 'value', 'created_at')
    search_fields = ('flag__name', 'user__email')


@admin.register(ExperimentExposure)
class ExperimentExposureAdmin(admin.ModelAdmin):
    list_display = ('flag_name', 'variant', 'user_id', 'created_at')
    list_filter = ('flag_name', 'variant')
    search_fields = ('flag_name', 'anon_token')
    readonly_fields = tuple(f.name for f in ExperimentExposure._meta.fields)
