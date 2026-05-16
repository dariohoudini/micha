from django.contrib import admin
from .models import ScanRule, ScanResult, UserViolationCounter


@admin.register(ScanRule)
class ScanRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'severity', 'is_active', 'updated_at')
    list_filter = ('category', 'severity', 'is_active')
    search_fields = ('name', 'description', 'pattern')


@admin.register(ScanResult)
class ScanResultAdmin(admin.ModelAdmin):
    list_display = ('id', 'ref_type', 'ref_id', 'actor',
                    'severity', 'action', 'created_at')
    list_filter = ('severity', 'action', 'ref_type')
    search_fields = ('ref_id', 'actor__email')
    readonly_fields = tuple(f.name for f in ScanResult._meta.fields)


@admin.register(UserViolationCounter)
class UserViolationCounterAdmin(admin.ModelAdmin):
    list_display = ('user', 'count_24h', 'last_severity',
                    'last_violation_at', 'last_case_id')
    search_fields = ('user__email',)
