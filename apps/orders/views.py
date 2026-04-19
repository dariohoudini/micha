"""
Orders Views — Invoice PDF + Packing Slip added
All IDOR protection maintained from previous fix
"""
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.http import HttpResponse
from rest_framework import generics, permissions, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from apps.users.permissions import IsNotSuspended, IsBuyerOfOrder, IsSellerOrSuperuser
from middleware.security import log_security_event
from .models import Order, OrderItem, OrderStatusLog, Payment, Refund


class CheckoutThrottle(UserRateThrottle):
    scope = "payment"


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ["id", "product", "product_title", "product_sku", "unit_price", "quantity", "total_price"]
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    buyer_email = serializers.EmailField(source="buyer.email", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id", "buyer_email", "status", "payment_status",
            "shipping_name", "shipping_phone", "shipping_address",
            "shipping_city", "shipping_province", "shipping_country",
            "subtotal", "shipping_cost", "discount", "total",
            "coupon_code", "tracking_number", "carrier", "estimated_delivery",
            "notes", "gift_wrap", "created_at", "updated_at", "items",
        ]
        read_only_fields = [
            "id", "buyer_email", "payment_status",
            "subtotal", "shipping_cost", "discount", "total",
            "created_at", "updated_at",
        ]


class RefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = Refund
        fields = ["id", "amount", "reason", "status", "admin_note", "created_at"]
        read_only_fields = ["id", "status", "admin_note", "created_at"]


class CheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]
    throttle_classes = [CheckoutThrottle]

    def post(self, request):
        from .checkout import CheckoutService, CheckoutError
        try:
            service = CheckoutService(user=request.user, data=request.data)
            orders = service.execute()
            return Response({"detail": "Order placed.", "orders": [str(o.id) for o in orders]}, status=201)
        except CheckoutError as e:
            return Response({"error": "checkout_failed", "detail": str(e)}, status=400)
        except Exception as e:
            log_security_event("checkout_error", request=request, details={"error": str(e)[:200]})
            return Response({"error": "server_error", "detail": "Checkout failed."}, status=500)


class MyOrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get_queryset(self):
        return Order.objects.filter(
            buyer=self.request.user
        ).select_related("buyer").prefetch_related("items").order_by("-created_at")


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended, IsBuyerOfOrder]

    def get_queryset(self):
        from django.db.models import Q
        return Order.objects.filter(Q(buyer=self.request.user) | Q(seller=self.request.user))

    def get_object(self):
        obj = get_object_or_404(self.get_queryset(), pk=self.kwargs["pk"])
        self.check_object_permissions(self.request, obj)
        return obj


class CancelOrderView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, buyer=request.user)
        if order.status not in ("pending", "confirmed"):
            return Response({"error": "cannot_cancel", "detail": f"Cannot cancel a {order.status} order."}, status=400)
        with transaction.atomic():
            order.update_status("cancelled", changed_by=request.user, note="Cancelled by buyer")
            for item in order.items.all():
                from django.db.models import F
                item.product.quantity = F("quantity") + item.quantity
                item.product.save(update_fields=["quantity"])
        return Response({"detail": "Order cancelled."})


class ConfirmDeliveryView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, buyer=request.user)
        if order.status != "shipped":
            return Response({"error": "invalid_status", "detail": "Order must be shipped first."}, status=400)
        with transaction.atomic():
            order.update_status("delivered", changed_by=request.user, note="Confirmed by buyer")
            from apps.orders.tasks import release_order_escrow
            release_order_escrow.delay(str(order.id))
        return Response({"detail": "Delivery confirmed."})


class SellerOrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended, IsSellerOrSuperuser]

    def get_queryset(self):
        qs = Order.objects.filter(seller=self.request.user)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs.order_by("-created_at")


class UpdateOrderStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended, IsSellerOrSuperuser]
    VALID_TRANSITIONS = {"confirmed": ["processing"], "processing": ["shipped"], "shipped": ["delivered"]}

    def patch(self, request, pk):
        order = get_object_or_404(Order, pk=pk, seller=request.user)
        new_status = request.data.get("status")
        allowed = self.VALID_TRANSITIONS.get(order.status, [])
        if new_status not in allowed:
            return Response({"error": "invalid_transition",
                             "detail": f"Cannot go from {order.status} to {new_status}."}, status=400)
        with transaction.atomic():
            tracking = request.data.get("tracking_number", "")
            if tracking:
                order.tracking_number = tracking
                order.save(update_fields=["tracking_number"])
            order.update_status(new_status, changed_by=request.user)
            if new_status == "shipped":
                from apps.orders.tasks import send_shipping_notification
                send_shipping_notification.delay(str(order.id))
        return Response({"detail": f"Order updated to {new_status}."})


class RequestRefundView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, buyer=request.user)
        if order.status not in ("delivered", "completed"):
            return Response({"error": "refund_not_available", "detail": "Refunds only after delivery."}, status=400)
        if Refund.objects.filter(order=order, status__in=["pending", "approved"]).exists():
            return Response({"error": "refund_exists", "detail": "Refund already requested."}, status=409)
        reason = request.data.get("reason", "").strip()
        if not reason:
            return Response({"error": "validation_error", "detail": "Reason required."}, status=400)
        refund = Refund.objects.create(order=order, requested_by=request.user, amount=order.total, reason=reason)
        return Response(RefundSerializer(refund).data, status=201)


class InvoiceView(APIView):
    """GET /api/orders/<id>/invoice/ — Download invoice PDF"""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def get(self, request, pk):
        from django.db.models import Q
        order = get_object_or_404(Order, Q(buyer=request.user) | Q(seller=request.user), pk=pk)

        try:
            from weasyprint import HTML
            from django.template.loader import render_to_string
            from django.conf import settings

            items = order.items.all()
            html_content = f"""
            <!DOCTYPE html><html><head>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 40px; }}
                h1 {{ color: #333; }} table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
                th, td {{ padding: 10px; border: 1px solid #ddd; text-align: left; }}
                th {{ background: #f5f5f5; }}
                .total {{ font-size: 18px; font-weight: bold; margin-top: 20px; text-align: right; }}
                .header {{ display: flex; justify-content: space-between; margin-bottom: 30px; }}
            </style>
            </head><body>
            <div class="header">
                <div><h1>MICHA Invoice</h1><p>micha.app</p></div>
                <div><p>Order: #{order.id}</p><p>Date: {order.created_at.strftime('%Y-%m-%d')}</p></div>
            </div>
            <p><strong>Bill to:</strong><br>{order.shipping_name}<br>{order.shipping_address}<br>{order.shipping_city}, Angola</p>
            <table>
                <tr><th>Product</th><th>SKU</th><th>Qty</th><th>Unit Price</th><th>Total</th></tr>
                {"".join(f"<tr><td>{i.product_title}</td><td>{i.product_sku}</td><td>{i.quantity}</td><td>{i.unit_price} AOA</td><td>{i.total_price} AOA</td></tr>" for i in items)}
            </table>
            <div class="total">
                <p>Subtotal: {order.subtotal} AOA</p>
                <p>Shipping: {order.shipping_cost} AOA</p>
                {"<p>Discount: -" + str(order.discount) + " AOA</p>" if order.discount else ""}
                <p><strong>Total: {order.total} AOA</strong></p>
            </div>
            </body></html>
            """
            pdf = HTML(string=html_content).write_pdf()
            response = HttpResponse(pdf, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="invoice-{order.id}.pdf"'
            return response

        except ImportError:
            # WeasyPrint not installed — return HTML fallback
            return Response({
                "error": "pdf_unavailable",
                "detail": "PDF generation not available. Install weasyprint.",
                "order": OrderSerializer(order).data,
            })


class PackingSlipView(APIView):
    """GET /api/orders/<id>/packing-slip/ — Download packing slip PDF for seller"""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended, IsSellerOrSuperuser]

    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk, seller=request.user)
        items = order.items.all()

        try:
            from weasyprint import HTML
            html_content = f"""
            <!DOCTYPE html><html><head>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 30px; }}
                h2 {{ border-bottom: 2px solid #333; }}
                table {{ width: 100%; border-collapse: collapse; }}
                td, th {{ padding: 8px; border: 1px solid #ccc; }}
            </style>
            </head><body>
            <h2>Packing Slip — Order #{order.id}</h2>
            <p><strong>Ship to:</strong><br>{order.shipping_name}<br>{order.shipping_phone}<br>{order.shipping_address}<br>{order.shipping_city}, Angola</p>
            <table>
                <tr><th>Product</th><th>SKU</th><th>Qty</th><th class="check">Packed</th></tr>
                {"".join(f"<tr><td>{i.product_title}</td><td>{i.product_sku}</td><td>{i.quantity}</td><td>[ ]</td></tr>" for i in items)}
            </table>
            <p style="margin-top:30px">Notes: {order.notes or "—"}</p>
            {"<p><strong>GIFT WRAP</strong></p>" if order.gift_wrap else ""}
            </body></html>
            """
            pdf = HTML(string=html_content).write_pdf()
            response = HttpResponse(pdf, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="packing-slip-{order.id}.pdf"'
            return response
        except ImportError:
            return Response({"error": "pdf_unavailable", "detail": "Install weasyprint for PDF generation."})
