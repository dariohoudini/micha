from django.contrib import admin
from .models import SavedSearch, AlertDelivery


@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'name', 'query_normalized',
                    'is_active', 'last_run_at', 'last_notified_at')
    list_filter = ('is_active',)
    search_fields = ('user__email', 'name', 'query_normalized')
    readonly_fields = ('last_run_at', 'last_notified_at', 'created_at',
                       'updated_at')


@admin.register(AlertDelivery)
class AlertDeliveryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'kind', 'channel',
                    'saved_search', 'delivered_at')
    list_filter = ('kind', 'channel')
    search_fields = ('user__email',)
    readonly_fields = tuple(f.name for f in AlertDelivery._meta.fields)
