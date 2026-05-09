from django.contrib import admin
from .models import DeviceFingerprint, RiskAssessment


@admin.register(RiskAssessment)
class RiskAssessmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'ref_type', 'ref_id', 'score', 'action', 'created_at')
    list_filter = ('action', 'ref_type')
    search_fields = ('user__email', 'ref_id')
    readonly_fields = (
        'user', 'ref_type', 'ref_id', 'score', 'action',
        'reasons', 'context', 'created_at',
    )
    ordering = ('-created_at',)


@admin.register(DeviceFingerprint)
class DeviceFingerprintAdmin(admin.ModelAdmin):
    list_display = ('fingerprint_short', 'user', 'use_count', 'last_seen_ip', 'last_seen_at')
    search_fields = ('fingerprint', 'user__email')
    readonly_fields = ('fingerprint', 'user', 'first_seen_at', 'last_seen_at', 'use_count')

    @admin.display(description='Fingerprint', ordering='fingerprint')
    def fingerprint_short(self, obj):
        return f'{obj.fingerprint[:12]}…'
