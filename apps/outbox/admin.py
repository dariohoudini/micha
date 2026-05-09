from django.contrib import admin
from django.utils import timezone

from .models import OutboxEvent, EventStatus


@admin.register(OutboxEvent)
class OutboxEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'topic', 'status', 'attempts', 'next_attempt_at',
                    'dispatched_at', 'ref_type', 'ref_id', 'created_at')
    list_filter = ('status', 'topic')
    search_fields = ('dedupe_key', 'topic', 'ref_id', 'last_error')
    readonly_fields = (
        'topic', 'payload', 'dedupe_key', 'ref_type', 'ref_id',
        'attempts', 'max_attempts', 'dispatched_at', 'last_error',
        'created_at', 'updated_at',
    )
    actions = ['requeue_now']

    @admin.action(description='Requeue selected events for immediate dispatch')
    def requeue_now(self, request, queryset):
        updated = queryset.exclude(status=EventStatus.DISPATCHED).update(
            status=EventStatus.PENDING,
            next_attempt_at=timezone.now(),
            last_error='',
        )
        self.message_user(request, f'Requeued {updated} event(s).')
