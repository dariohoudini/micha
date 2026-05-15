from django.contrib import admin
from .models import IdempotencyKey


@admin.register(IdempotencyKey)
class IdempotencyKeyAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'key', 'status', 'status_code',
                    'created_at', 'completed_at', 'expires_at')
    list_filter = ('status',)
    search_fields = ('key', 'user__email')
    readonly_fields = ('user', 'key', 'request_hash', 'status', 'status_code',
                       'response_body', 'created_at', 'completed_at', 'expires_at')
    ordering = ('-created_at',)
