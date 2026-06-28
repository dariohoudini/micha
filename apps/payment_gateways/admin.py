from django.contrib import admin

from .models import GatewayTransaction, GatewayWebhookEvent, PaymentIntent


@admin.register(PaymentIntent)
class PaymentIntentAdmin(admin.ModelAdmin):
    list_display = ('id', 'gateway', 'purpose', 'amount', 'currency',
                    'status', 'user', 'created_at')
    list_filter = ('gateway', 'status', 'currency')
    search_fields = ('idempotency_key', 'gateway_intent_id')
    readonly_fields = ('id', 'created_at', 'updated_at', 'completed_at')


@admin.register(GatewayTransaction)
class GatewayTransactionAdmin(admin.ModelAdmin):
    list_display = ('intent', 'kind', 'gateway', 'direction',
                    'success', 'occurred_at')
    list_filter = ('kind', 'gateway', 'success')


@admin.register(GatewayWebhookEvent)
class GatewayWebhookEventAdmin(admin.ModelAdmin):
    list_display = ('provider_event_id', 'gateway', 'event_type',
                    'signature_valid', 'processed_ok', 'received_at')
    list_filter = ('gateway', 'event_type', 'signature_valid', 'processed_ok')
