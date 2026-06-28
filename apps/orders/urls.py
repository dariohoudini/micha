from django.urls import path
from .views import (
    ReturnRequestCreateView,
    CheckoutView, MyOrderListView, OrderDetailView,
    CancelOrderView, ConfirmDeliveryView, ExtendProtectionView,
    BatchShipView, OrderMessagesView,
    SellerOrderListView, UpdateOrderStatusView,
    RequestRefundView, InvoiceView, PackingSlipView,
    OrderTrackingView,
    SellerReturnListView, SellerReturnActionView,
    BuyerReturnActionView, AdminReturnOverrideView,
)


urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("my/", MyOrderListView.as_view(), name="my-orders"),
    path("<uuid:pk>/", OrderDetailView.as_view(), name="order-detail"),
    path("<uuid:pk>/cancel/", CancelOrderView.as_view(), name="cancel-order"),
    path("<uuid:pk>/confirm-delivery/", ConfirmDeliveryView.as_view(), name="confirm-delivery"),
    # AliExpress Complete 2025 CH 13.2 — buyer one-time +15 day extension
    path("<uuid:pk>/extend-protection/", ExtendProtectionView.as_view(), name="extend-protection"),
    path("<uuid:pk>/status/", UpdateOrderStatusView.as_view(), name="update-status"),
    path("<uuid:pk>/refund/", RequestRefundView.as_view(), name="request-refund"),
    path("<uuid:pk>/invoice/", InvoiceView.as_view(), name="invoice"),
    path("<uuid:pk>/packing-slip/", PackingSlipView.as_view(), name="packing-slip"),
    path("seller/", SellerOrderListView.as_view(), name="seller-orders"),
    # AliExpress Complete 2025 CH 21.2 + CH 11.3
    path("seller/batch-ship/", BatchShipView.as_view(), name="seller-batch-ship"),
    path("<uuid:pk>/buyer-message/", OrderMessagesView.as_view(), name="order-buyer-message"),
    path("returns/seller/", SellerReturnListView.as_view(), name="seller-returns"),
    path("returns/<int:pk>/", SellerReturnActionView.as_view(), name="seller-return-action"),
    path("returns/<int:pk>/buyer-action/", BuyerReturnActionView.as_view(), name="buyer-return-action"),
    path("returns/<int:pk>/admin-override/", AdminReturnOverrideView.as_view(), name="admin-return-override"),
    path("<uuid:pk>/return/", ReturnRequestCreateView.as_view(), name="return-request"),
    path("<uuid:pk>/tracking/", OrderTrackingView.as_view(), name="order-tracking"),
]
