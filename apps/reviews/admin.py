from django.contrib import admin
from .models import Review

@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "seller",    # was "store" before
        "reviewer",  # correct field
        "rating",
        "comment",
        "created_at",
    )
    list_filter = ("seller", "rating", "created_at")  # match actual fields
    search_fields = ("reviewer__email", "seller__email", "comment")
    ordering = ("-created_at",)
