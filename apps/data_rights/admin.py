from django.contrib import admin
from .models import DataSubjectRequest


@admin.register(DataSubjectRequest)
class DataSubjectRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'user_email_at_request', 'kind',
                    'status', 'created_at', 'completed_at', 'sla_deadline_at')
    list_filter = ('kind', 'status')
    search_fields = ('user__email', 'user_email_at_request')
    readonly_fields = ('user', 'user_email_at_request', 'kind', 'status',
                       'source_ip', 'user_agent', 'payload', 'error',
                       'sla_deadline_at', 'created_at', 'started_at',
                       'completed_at')
    ordering = ('-created_at',)
