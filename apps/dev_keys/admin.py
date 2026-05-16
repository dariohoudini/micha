from django.contrib import admin
from .models import APIKey, APIKeyUsage


@admin.register(APIKey)
class APIKeyAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'name', 'key_prefix', 'is_active',
                    'last_used_at', 'expires_at', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'user__email', 'key_prefix')
    readonly_fields = ('key_hash', 'key_prefix', 'created_at',
                       'last_used_at', 'revoked_at')


@admin.register(APIKeyUsage)
class APIKeyUsageAdmin(admin.ModelAdmin):
    list_display = ('id', 'key', 'method', 'path', 'status',
                    'latency_ms', 'created_at')
    list_filter = ('status', 'method')
    search_fields = ('path',)
    readonly_fields = tuple(f.name for f in APIKeyUsage._meta.fields)
