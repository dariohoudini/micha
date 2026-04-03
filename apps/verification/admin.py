from django.contrib import admin
from .models import SellerVerification


@admin.register(SellerVerification)
class SellerVerificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'status', 'id_expiry_date', 'created_at')
    list_filter = ('status',)
    search_fields = ('user__phone', 'id_number')
