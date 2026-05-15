from django.contrib import admin
from .models import Saga


@admin.register(Saga)
class SagaAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'status', 'ref_type', 'ref_id',
                    'current_step', 'created_at', 'completed_at')
    list_filter = ('name', 'status')
    search_fields = ('name', 'ref_id', 'error')
    readonly_fields = ('name', 'ref_type', 'ref_id', 'payload',
                       'current_step', 'steps_log', 'error', 'wait_until',
                       'created_at', 'updated_at', 'completed_at')
    ordering = ('-created_at',)
