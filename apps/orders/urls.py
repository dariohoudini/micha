from django.urls import path
from .views import (
    CheckoutView, MyOrderListView, OrderDetailView,
    CancelOrderView, ConfirmDeliveryView,
    SellerOrderListView, UpdateOrderStatusView,
    RequestRefundView, InvoiceView, PackingSlipView,
)


urlpatterns = [
    path("checkout/", CheckoutView.as_view(), name="checkout"),
    path("my/", MyOrderListView.as_view(), name="my-orders"),
    path("<uuid:pk>/", OrderDetailView.as_view(), name="order-detail"),
    path("<uuid:pk>/cancel/", CancelOrderView.as_view(), name="cancel-order"),
    path("<uuid:pk>/confirm-delivery/", ConfirmDeliveryView.as_view(), name="confirm-delivery"),
    path("<uuid:pk>/status/", UpdateOrderStatusView.as_view(), name="update-status"),
    path("<uuid:pk>/refund/", RequestRefundView.as_view(), name="request-refund"),
    path("<uuid:pk>/invoice/", InvoiceView.as_view(), name="invoice"),
    path("<uuid:pk>/packing-slip/", PackingSlipView.as_view(), name="packing-slip"),
    path("seller/", SellerOrderListView.as_view(), name="seller-orders"),
]
