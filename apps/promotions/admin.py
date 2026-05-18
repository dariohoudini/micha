from django.contrib import admin
from .models import Coupon, FlashSale, CouponRedemption


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ('code', 'discount_type', 'discount_value',
                    'used_count', 'usage_limit', 'is_active',
                    'valid_from', 'valid_until')
    list_filter = ('discount_type', 'is_active')
    search_fields = ('code',)
    readonly_fields = ('used_count', 'created_at')


@admin.register(FlashSale)
class FlashSaleAdmin(admin.ModelAdmin):
    list_display = ('product', 'sale_price', 'original_price',
                    'start_time', 'end_time', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('product__title',)


@admin.register(CouponRedemption)
class CouponRedemptionAdmin(admin.ModelAdmin):
    list_display = ('id', 'coupon', 'user', 'order_id',
                    'applied_amount', 'status', 'applied_at', 'released_at')
    list_filter = ('status',)
    search_fields = ('coupon__code', 'order_id', 'user__email')
    readonly_fields = ('coupon', 'user', 'order_id', 'applied_amount',
                       'subtotal_at_apply', 'applied_at', 'released_at')
