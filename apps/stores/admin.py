from django.contrib import admin
from .models import Store
from apps.reviews.models import Review
from django.db.models import Avg

@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "owner",
        "name",
        "average_rating",  # computed method
        "city",
        "is_active",
    )
    list_filter = ("is_active", "city", "created_at")
    search_fields = ("owner__email", "name", "city")
    ordering = ("-created_at",)

    def average_rating(self, obj):
        result = Review.objects.filter(seller=obj.owner).aggregate(avg=Avg("rating"))
        return round(result["avg"] or 0, 2)

    average_rating.short_description = "Rating"
