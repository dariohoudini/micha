from django.contrib import admin
from .models import InboundWebhookEvent


@admin.register(InboundWebhookEvent)
class InboundWebhookEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'provider', 'event_type', 'status',
                    'response_status', 'source_ip', 'received_at')
    list_filter = ('provider', 'status', 'event_type')
    search_fields = ('provider', 'event_type', 'source_ip', 'signature_header')
    readonly_fields = ('provider', 'body_sha256', 'body_excerpt',
                       'signature_header', 'timestamp_header',
                       'source_ip', 'user_agent', 'status', 'event_type',
                       'response_status', 'response_body', 'error',
                       'duration_ms', 'received_at')
    ordering = ('-received_at',)
