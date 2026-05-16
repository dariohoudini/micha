from django.contrib import admin
from .models import UserTOTP, BackupCode, TrustedDevice, ChallengeAttempt


@admin.register(UserTOTP)
class UserTOTPAdmin(admin.ModelAdmin):
    list_display = ('user', 'enabled_at', 'last_used_at',
                    'failed_attempts', 'locked_until')
    search_fields = ('user__email',)
    readonly_fields = ('secret', 'created_at', 'updated_at')


@admin.register(BackupCode)
class BackupCodeAdmin(admin.ModelAdmin):
    list_display = ('user', 'code_hash', 'used_at', 'created_at')
    search_fields = ('user__email',)
    readonly_fields = ('user', 'code_hash', 'used_at', 'created_at')


@admin.register(TrustedDevice)
class TrustedDeviceAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'ip', 'last_used_at', 'expires_at')
    search_fields = ('user__email', 'ip')


@admin.register(ChallengeAttempt)
class ChallengeAttemptAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'outcome', 'purpose', 'ip', 'created_at')
    list_filter = ('outcome', 'purpose')
    search_fields = ('user__email', 'ip')
    readonly_fields = tuple(f.name for f in ChallengeAttempt._meta.fields)
