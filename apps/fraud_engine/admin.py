from django.contrib import admin
from .models import (
    ActionLog, DeviceFingerprint, DeviceUserLink, FraudDecision,
    IpReputation, VelocityRule,
)


@admin.register(DeviceFingerprint)
class DeviceFingerprintAdmin(admin.ModelAdmin):
    list_display = ('fingerprint_hash', 'platform', 'first_seen_at',
                    'last_seen_at', 'seen_count')


@admin.register(DeviceUserLink)
class DeviceUserLinkAdmin(admin.ModelAdmin):
    list_display = ('device', 'user', 'first_seen_at', 'last_seen_at',
                    'seen_count')


@admin.register(IpReputation)
class IpReputationAdmin(admin.ModelAdmin):
    list_display = ('ip_address', 'score', 'external_score',
                    'is_tor', 'is_datacenter', 'is_manual_block', 'country')
    list_filter = ('is_tor', 'is_datacenter', 'is_proxy', 'is_manual_block')


@admin.register(VelocityRule)
class VelocityRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'action', 'scope', 'window_seconds',
                    'max_count', 'on_exceed', 'score_weight', 'is_active')
    list_filter = ('action', 'scope', 'is_active', 'on_exceed')


@admin.register(FraudDecision)
class FraudDecisionAdmin(admin.ModelAdmin):
    list_display = ('action', 'user', 'ip_address', 'score',
                    'decision', 'created_at')
    list_filter = ('action', 'decision')


@admin.register(ActionLog)
class ActionLogAdmin(admin.ModelAdmin):
    list_display = ('action', 'user', 'ip_address', 'occurred_at')
    list_filter = ('action',)
