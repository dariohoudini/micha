from django.contrib import admin
from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "reporter",
        "target_type",
        "target_id",
        "status",
        "created_at",
    )

    list_filter = (
        "target_type",
        "status",
        "created_at",
    )

    search_fields = (
        "reporter__email",
        "reason",
    )

    ordering = ("-created_at",)


    def mark_as_resolved(self, request, queryset):
        queryset.update(is_resolved=True)
    mark_as_resolved.short_description = "Mark selected reports as resolved"
