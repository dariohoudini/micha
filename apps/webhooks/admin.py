from django.contrib import admin
from .models import SellerWebhook, WebhookDelivery


@admin.register(SellerWebhook)
class SellerWebhookAdmin(admin.ModelAdmin):
    list_display = ('id', 'seller', 'url', 'is_active',
                    'consecutive_failures', 'last_success_at', 'last_failure_at',
                    'created_at')
    list_filter = ('is_active',)
    search_fields = ('url', 'seller__email')
    readonly_fields = ('secret', 'consecutive_failures',
                       'last_success_at', 'last_failure_at',
                       'created_at', 'updated_at')


@admin.register(WebhookDelivery)
class WebhookDeliveryAdmin(admin.ModelAdmin):
    list_display = ('id', 'webhook', 'topic', 'status',
                    'attempts', 'response_status',
                    'created_at', 'delivered_at')
    list_filter = ('status', 'topic')
    search_fields = ('topic', 'webhook__url', 'dedupe_key')
    readonly_fields = ('webhook', 'topic', 'payload', 'dedupe_key',
                       'attempts', 'response_status', 'response_body',
                       'last_error', 'created_at', 'delivered_at',
                       'updated_at', 'next_attempt_at')
    ordering = ('-created_at',)
