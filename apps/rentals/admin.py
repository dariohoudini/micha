"""
apps/rentals/admin.py
"""
from django.contrib import admin
from .models import (
    Listing, PropertyDetail, VehicleDetail, OtherRentalDetail,
    ListingLocation, ListingImage, ListingInquiry,
    RentalVerification, SavedListing
)


class ListingImageInline(admin.TabularInline):
    model = ListingImage
    extra = 0
    readonly_fields = ['created_at']


class PropertyDetailInline(admin.StackedInline):
    model = PropertyDetail
    extra = 0


class VehicleDetailInline(admin.StackedInline):
    model = VehicleDetail
    extra = 0


class OtherDetailInline(admin.StackedInline):
    model = OtherRentalDetail
    extra = 0


class ListingLocationInline(admin.StackedInline):
    model = ListingLocation
    extra = 0


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ['title', 'category', 'lister_role', 'purpose', 'price', 'status', 'views_count', 'created_at']
    list_filter = ['category', 'status', 'purpose', 'lister_role']
    search_fields = ['title', 'lister__email']
    readonly_fields = ['views_count', 'inquiries_count', 'saves_count', 'created_at', 'updated_at']
    inlines = [ListingLocationInline, ListingImageInline, PropertyDetailInline, VehicleDetailInline, OtherDetailInline]
    actions = ['approve_listings', 'reject_listings']

    def approve_listings(self, request, queryset):
        for listing in queryset:
            listing.publish()
        self.message_user(request, f"{queryset.count()} listagens aprovadas.")
    approve_listings.short_description = "Aprovar listagens seleccionadas"

    def reject_listings(self, request, queryset):
        queryset.update(status='rejected')
        self.message_user(request, f"{queryset.count()} listagens rejeitadas.")
    reject_listings.short_description = "Rejeitar listagens seleccionadas"


@admin.register(RentalVerification)
class RentalVerificationAdmin(admin.ModelAdmin):
    list_display = ['user', 'id_document_type', 'is_micheiro', 'status', 'submitted_at']
    list_filter = ['status', 'is_micheiro', 'id_document_type']
    search_fields = ['user__email', 'id_document_number']
    readonly_fields = ['submitted_at']
    actions = ['approve_verifications', 'reject_verifications']

    def approve_verifications(self, request, queryset):
        from django.utils import timezone
        queryset.update(status='approved', reviewed_by=request.user, reviewed_at=timezone.now())
        self.message_user(request, f"{queryset.count()} verificações aprovadas.")
    approve_verifications.short_description = "Aprovar verificações seleccionadas"

    def reject_verifications(self, request, queryset):
        queryset.update(status='rejected')
        self.message_user(request, f"{queryset.count()} verificações rejeitadas.")
    reject_verifications.short_description = "Rejeitar verificações seleccionadas"


@admin.register(ListingInquiry)
class ListingInquiryAdmin(admin.ModelAdmin):
    list_display = ['inquirer', 'listing', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['inquirer__email', 'listing__title']
