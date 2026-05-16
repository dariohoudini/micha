from django.contrib import admin
from .models import BulkJob, BulkJobItem


@admin.register(BulkJob)
class BulkJobAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'status', 'total', 'processed',
                    'failed', 'skipped', 'created_at', 'finished_at')
    list_filter = ('name', 'status')
    search_fields = ('name',)
    readonly_fields = tuple(f.name for f in BulkJob._meta.fields)


@admin.register(BulkJobItem)
class BulkJobItemAdmin(admin.ModelAdmin):
    list_display = ('id', 'job', 'item_ref', 'status', 'processed_at')
    list_filter = ('status',)
    search_fields = ('item_ref',)
    readonly_fields = tuple(f.name for f in BulkJobItem._meta.fields)
