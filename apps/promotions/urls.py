from django.urls import path
from .views import (
    ValidateCouponView,
    AdminCouponListCreateView,
    SellerCouponListCreateView,
    LiveFlashSalesView,
    SellerFlashSaleView,
    MyCouponsView,
    CollectCouponView,
    StockNotificationListCreateView,
    LiveSaleEventsView,
    AdminSaleEventListCreateView,
)


urlpatterns = [
    path('coupons/validate/', ValidateCouponView.as_view(), name='validate-coupon'),
    path('coupons/', AdminCouponListCreateView.as_view(), name='admin-coupons'),
    path('seller/coupons/', SellerCouponListCreateView.as_view(), name='seller-coupons'),
    path('flash-sales/', LiveFlashSalesView.as_view(), name='flash-sales'),
    path('seller/flash-sales/', SellerFlashSaleView.as_view(), name='seller-flash-sales'),
    # User Process Flow §16.2 + §7.6 — buyer-facing coupon/stock APIs
    path('coupons/mine/', MyCouponsView.as_view(), name='my-coupons'),
    path('coupons/collect/', CollectCouponView.as_view(), name='collect-coupon'),
    path('stock-notify/', StockNotificationListCreateView.as_view(), name='stock-notify'),
    # AliExpress Complete 2025 CH 17.3 — major sale event calendar.
    path('sale-events/', LiveSaleEventsView.as_view(), name='live-sale-events'),
    path('admin/sale-events/', AdminSaleEventListCreateView.as_view(), name='admin-sale-events'),
]
