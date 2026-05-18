from django.contrib import admin
from .models import WaitlistEntry


@admin.register(WaitlistEntry)
class WaitlistEntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'product', 'status', 'position',
                    'joined_at', 'notified_at', 'converted_at')
    list_filter = ('status',)
    search_fields = ('user__email', 'product__title',
                     'converted_order_id')
    readonly_fields = ('joined_at', 'notified_at', 'converted_at',
                       'converted_order_id')
