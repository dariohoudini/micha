from django.urls import path
from .views import (
    ValidateCouponView,
    AdminCouponListCreateView,
    SellerCouponListCreateView,
    LiveFlashSalesView,
    SellerFlashSaleView,
)


urlpatterns = [
    path('coupons/validate/', ValidateCouponView.as_view(), name='validate-coupon'),
    path('coupons/', AdminCouponListCreateView.as_view(), name='admin-coupons'),
    path('seller/coupons/', SellerCouponListCreateView.as_view(), name='seller-coupons'),
    path('flash-sales/', LiveFlashSalesView.as_view(), name='flash-sales'),
    path('seller/flash-sales/', SellerFlashSaleView.as_view(), name='seller-flash-sales'),
]
