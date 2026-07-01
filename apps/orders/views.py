"""
Orders Views — Invoice PDF + Packing Slip added
All IDOR protection maintained from previous fix
"""
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from rest_framework import generics, permissions, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.parsers import MultiPartParser

from apps.users.permissions import IsNotSuspended, IsBuyerOfOrder, IsSellerOrSuperuser, IsNotAdminStaff
from apps.idempotency.decorators import idempotent
from middleware.security import log_security_event
from .models import Order, OrderItem, Refund, OrderTrackingEvent


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
    # IsNotAdminStaff: admins are management-only and cannot buy (checkout).
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended, IsNotAdminStaff]
    throttle_classes = [CheckoutThrottle]

    # Idempotency-Key is MANDATORY on checkout.
    #
    # Why required=True now: the prior comment said "flipping
    # required=True is a frontend-coordinated change." This commit
    # makes that flip together with the frontend interceptor that
    # auto-attaches Idempotency-Key on every POST.
    #
    # Threat scenario without this:
    #   1. Buyer clicks 'Place order' on flaky Luanda 4G.
    #   2. Browser submits POST; checkout starts; payment gateway
    #      call is sent.
    #   3. Network drops mid-response. Buyer sees a timeout.
    #   4. Buyer clicks 'Place order' again.
    #   5. WITHOUT idempotency: two orders are created, two
    #      payments charged, two stock decrements. Buyer disputes.
    #      Refund pipeline activates. Platform eats the cost.
    #
    # WITH idempotency: the second POST carries the same key
    # (frontend hook persists it for the duration of the checkout
    # intent). Backend sees the key, replays the cached response
    # from the first attempt. Single charge, single order.
    @idempotent(required=True)
    def post(self, request):
        from .checkout import CheckoutService, CheckoutError
        from apps.risk.service import assess as risk_assess, record_fingerprint, is_blocking
        from apps.risk.models import RiskAction

        # ── 1. Risk pre-assessment ─────────────────────────────────────
        # Compute the proposed total from the user's cart so the rules see
        # the real order_amount before we even create the Order rows.
        try:
            from apps.cart.models import Cart
            cart = Cart.objects.filter(user=request.user).prefetch_related('items').first()
            cart_total = float(cart.total) if cart else 0
        except Exception:
            cart_total = 0

        fingerprint = (request.data.get('fingerprint') or '').strip()[:128]
        ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', ''))
        if ',' in ip:
            ip = ip.split(',')[0].strip()
        ip = ip[:45] if ip else None

        if fingerprint:
            try:
                record_fingerprint(user=request.user, fingerprint=fingerprint, ip=ip)
            except Exception:
                pass

        try:
            assessment = risk_assess(
                'order',
                ref_type='order', ref_id='pending',
                user=request.user,
                context={
                    'order_amount': cart_total,
                    'fingerprint': fingerprint,
                    'ip': ip,
                    'user_agent': (request.META.get('HTTP_USER_AGENT') or '')[:200],
                    'payment_method': request.data.get('payment_method', ''),
                },
            )
        except Exception as e:
            # Risk system must never crash checkout. Log + proceed at default ALLOW.
            log_security_event('risk_assess_error', request=request, details={'error': str(e)[:200]})
            assessment = None

        if assessment and assessment.action == RiskAction.BLOCK:
            log_security_event('checkout_blocked_by_risk', request=request, details={
                'score': assessment.score,
                'reasons': assessment.reasons,
            })
            try:
                from apps.telemetry.metrics import checkout_blocked_by_risk
                checkout_blocked_by_risk.inc()
            except Exception:
                pass
            return Response({
                'error': 'risk_blocked',
                'detail': 'Não conseguimos processar este pedido. Contacte o suporte.',
            }, status=403)

        # ── 2. Run checkout ────────────────────────────────────────────
        try:
            service = CheckoutService(user=request.user, data=request.data)
            orders = service.execute()
        except CheckoutError as e:
            return Response({'error': 'checkout_failed', "detail": str(e)}, status=400)
        except Exception as e:
            log_security_event("checkout_error", request=request, details={"error": str(e)[:200]})
            return Response({'error': 'server_error', "detail": "Checkout failed."}, status=500)

        # Telemetry: orders_created (count) + gmv_kz (value) — the pair
        # that catches a silent "Buy button broken / orders at zero value"
        # failure tech metrics miss (Monitoring doc CH6).
        try:
            from apps.telemetry.metrics import orders_created, gmv_kz
            for o in orders:
                pm = getattr(o, 'payment_method', '') or 'unknown'
                orders_created.labels(payment_method=pm).inc()
                total = getattr(o, 'total', None)
                if total is not None:
                    gmv_kz.labels(payment_method=pm).inc(float(total))
        except Exception:
            pass

        # ── 3. Stamp the score on every created order + emit fraud event
        if assessment and orders:
            try:
                from .models import Order as _Order
                from apps.outbox.service import publish
                first_id = str(orders[0].id)
                # Link the assessment to the first order for forensic traceability
                assessment.ref_id = first_id
                assessment.save(update_fields=['ref_id'])
                # Stamp on all orders
                _Order.objects.filter(pk__in=[o.pk for o in orders]).update(
                    fraud_score=assessment.score,
                    fraud_action=assessment.action,
                )
                # Notify ops queue for non-allow outcomes
                if assessment.action != RiskAction.ALLOW:
                    publish(
                        topic='fraud.flagged',
                        payload={
                            'order_ids': [str(o.id) for o in orders],
                            'user_id': request.user.id,
                            'score': assessment.score,
                            'action': assessment.action,
                            'reasons': assessment.reasons,
                        },
                        dedupe_key=f'fraud.flagged:{first_id}',
                        ref_type='order', ref_id=first_id,
                    )
            except Exception as e:
                log_security_event('risk_persist_error', request=request, details={'error': str(e)[:200]})

        return Response({
            "detail": "Order placed.",
            "orders": [str(o.id) for o in orders],
            **({"risk_score": assessment.score, "risk_action": assessment.action} if assessment else {}),
        }, status=201)


class MyOrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]
    # Cursor pagination — buyer order histories grow without bound for
    # repeat buyers; OFFSET 5000 on page 250 scans 5000 rows we don't need.
    # ordered by -created_at (which already has an index via Order.Meta).
    from middleware.pagination import LargeListCursorPagination
    pagination_class = LargeListCursorPagination

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
    """POST /api/v1/orders/<pk>/cancel/

    Idempotency REQUIRED. A duplicate cancel inside the same retry window
    would re-enter the atomic block, re-credit stock with F-expressions,
    and double-restock inventory — visible-to-buyers stock count would
    silently double for every product in the order.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    @idempotent(required=True)
    def post(self, request, pk):
        from apps.orders.stock_restore import (
            restore_order, StockRestoreError,
        )
        order = get_object_or_404(Order, pk=pk, buyer=request.user)
        if order.status not in ("pending", "confirmed"):
            return Response(
                {'error': 'cannot_cancel',
                 "detail": f"Cannot cancel a {order.status} order."},
                status=400,
            )
        # All restock + store-credit + coupon-release logic lives in
        # restore_order so cancel, payment-fail, and the abandoned-checkout
        # saga behave IDENTICALLY. Previously this view's inline restock
        # only handled products (not variants), didn't refund store credit,
        # and didn't release coupons.
        try:
            restore_order(
                order_id=str(order.pk), source='manual_cancel',
                reason=f'buyer:{request.user.id}',
            )
        except StockRestoreError as e:
            return Response(
                {'error': 'cannot_cancel', 'detail': str(e)},
                status=400,
            )
        with transaction.atomic():
            order.update_status(
                "cancelled", changed_by=request.user,
                note="Cancelled by buyer",
            )
        return Response({"detail": "Order cancelled."})


class ConfirmDeliveryView(APIView):
    """POST /api/v1/orders/<pk>/confirm-delivery/

    Idempotency REQUIRED. Each call mints cashback points via
    ledger.transfer AND releases seller escrow via the outbox. The
    ledger transfer has its own journal_key dedupe, but the
    user.add_loyalty_points() cached counter call does NOT — a retry
    would double-credit the cached counter while the source-of-truth
    ledger correctly dedupes, leaving the two views inconsistent.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    @idempotent(required=True)
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, buyer=request.user)
        if order.status != "shipped":
            return Response({'error': 'invalid_status', "detail": "Order must be shipped first."}, status=400)
        with transaction.atomic():
            order.update_status("delivered", changed_by=request.user, note="Confirmed by buyer")
            # Outbox: durable intent. The handler kicks release_order_escrow.
            from apps.outbox.service import publish as _ob_publish
            _ob_publish(
                topic='order.delivery_confirmed',
                payload={'order_id': str(order.id)},
                dedupe_key=f'order.delivery_confirmed:{order.id}',
                ref_type='order', ref_id=str(order.id),
            )
            # Loyalty cashback: 1 point per Kz spent (= 1% back, since 100 pts = 1 Kz),
            # capped at 50 000 pts (500 Kz) per order to limit fraud impact.
            try:
                points = min(50000, int(order.total))
                if points > 0:
                    request.user.add_loyalty_points(points)  # cached counter
                    # Source of truth: ledger
                    from apps.ledger.service import transfer
                    from apps.ledger.models import Account, AccountType
                    transfer(
                        from_account=Account.platform(AccountType.PLATFORM_LOYALTY_FUND, currency='PTS'),
                        to_account=Account.for_user(request.user, AccountType.USER_LOYALTY_POINTS, currency='PTS'),
                        amount_cents=points,
                        journal_key=f'order:{order.id}:cashback',
                        ref_type='order',
                        ref_id=str(order.id),
                        description=f'Cashback ({points} pts) for order {order.id}',
                        user=request.user,
                    )
            except Exception:
                pass
        return Response({"detail": "Delivery confirmed."})


class ExtendProtectionView(APIView):
    """POST /api/v1/orders/<pk>/extend-protection/

    AliExpress Complete 2025 CH 13.2 — buyer one-time +15 day
    extension of the Buyer Protection window. Allowed only in the
    last 5 days of the existing deadline and only once per order
    (``Order.protection_extended`` flag enforces single-use).
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request, pk):
        from django.utils import timezone as _tz
        from datetime import timedelta as _td
        order = get_object_or_404(Order, pk=pk, buyer=request.user)
        if order.protection_extended:
            return Response({'error': 'already_extended', 'detail': 'Já estendeu esta protecção.'}, status=400)
        if order.status not in ('shipped', 'delivered'):
            return Response({'error': 'invalid_status', 'detail': 'Estado do pedido não permite extensão.'}, status=400)
        deadline = order.protection_deadline_at or (_tz.now() + _td(days=30))
        days_left = (deadline - _tz.now()).days
        if days_left > 5:
            return Response({'error': 'too_early', 'detail': f'Só pode estender nos últimos 5 dias ({days_left} restantes).'}, status=400)
        order.protection_deadline_at = deadline + _td(days=15)
        order.protection_extended = True
        order.save(update_fields=['protection_deadline_at', 'protection_extended'])
        # User Process Flow §20.8 audit.
        try:
            from apps.analytics.models import UserEvent
            UserEvent.objects.create(user=request.user, event='order.protection_extended',
                properties={'order_id': str(order.id), 'new_deadline': order.protection_deadline_at.isoformat()})
        except Exception:
            pass
        return Response({'detail': 'Protecção estendida em 15 dias.', 'new_deadline': order.protection_deadline_at})


class SellerOrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended, IsSellerOrSuperuser]
    # Cursor pagination — high-volume sellers can accrue 100k+ orders.
    # OFFSET pagination on page 4000 = 100,000 scanned rows per request.
    from middleware.pagination import LargeListCursorPagination
    pagination_class = LargeListCursorPagination

    def get_queryset(self):
        qs = Order.objects.filter(seller=self.request.user)
        status_filter = self.request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs.order_by("-created_at")


class UpdateOrderStatusView(APIView):
    """PATCH /api/v1/orders/<pk>/status/

    Idempotency REQUIRED. Each accepted transition publishes outbox
    events (e.g. order.shipped → notification + carrier webhooks).
    A duplicate retry would fire those events twice, sending the
    buyer two "your order has shipped" emails.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended, IsSellerOrSuperuser]
    VALID_TRANSITIONS = {"confirmed": ["processing"], "processing": ["shipped"], "shipped": ["delivered"]}

    @idempotent(required=True)
    def patch(self, request, pk):
        order = get_object_or_404(Order, pk=pk, seller=request.user)
        new_status = request.data.get("status")
        allowed = self.VALID_TRANSITIONS.get(order.status, [])
        if new_status not in allowed:
            return Response({'error': 'invalid_transition',
                             "detail": f"Cannot go from {order.status} to {new_status}."}, status=400)
        with transaction.atomic():
            tracking = request.data.get("tracking_number", "")
            if tracking:
                order.tracking_number = tracking
                order.save(update_fields=["tracking_number"])
            order.update_status(new_status, changed_by=request.user)
            if new_status == "shipped":
                from apps.outbox.service import publish as _ob_publish
                _ob_publish(
                    topic='order.shipped',
                    payload={'order_id': str(order.id), 'tracking_number': tracking or ''},
                    dedupe_key=f'order.shipped:{order.id}',
                    ref_type='order', ref_id=str(order.id),
                )
        return Response({"detail": f"Order updated to {new_status}."})


class RequestRefundView(APIView):
    """POST /api/v1/orders/<pk>/refund/  — buyer requests a refund.

    Idempotency-Key REQUIRED. A retried refund request from a flaky network
    must not create two Refund rows for the same order — the duplicate-
    refund check below catches the obvious case, but a concurrent retry
    inside the same millisecond can slip past it. The idempotency layer
    is the belt-and-braces guard.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    @idempotent(required=True)
    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, buyer=request.user)
        if order.status not in ("delivered", "completed"):
            return Response({'error': 'refund_not_available', "detail": "Refunds only after delivery."}, status=400)
        if Refund.objects.filter(order=order, status__in=["pending", "approved"]).exists():
            return Response({'error': 'refund_exists', "detail": "Refund already requested."}, status=409)
        reason = request.data.get("reason", "").strip()
        if not reason:
            return Response({'error': 'validation_error', "detail": "Reason required."}, status=400)
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
            return Response({'error': 'pdf_unavailable', "detail": "Install weasyprint for PDF generation."})


class ReturnRequestCreateView(APIView):
    """GET /api/v1/orders/<uuid>/return/  — read existing return request.
    POST /api/v1/orders/<uuid>/return/  — submit a return request (multipart for photo).
    """
    from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    VALID_REASONS = {'wrong_item', 'damaged', 'not_as_described', 'missing_parts', 'changed_mind'}
    VALID_PICKUPS = {'pickup', 'dropoff'}

    def _serialize(self, ret, request):
        photo_url = None
        if ret.photo:
            try:
                photo_url = request.build_absolute_uri(ret.photo.url)
            except Exception:
                photo_url = ret.photo.url
        return {
            'id': ret.id,
            'status': ret.status,
            'reason': ret.reason,
            'description': ret.description,
            'pickup_method': ret.pickup_method,
            'photo_url': photo_url,
            'admin_note': ret.admin_note,
            'created_at': ret.created_at,
            'updated_at': ret.updated_at,
        }

    @idempotent(required=True)
    def post(self, request, pk):
        # Idempotency REQUIRED. The unique-row check below catches the
        # already-submitted case but a concurrent retry can slip past it.
        order = get_object_or_404(Order, pk=pk, buyer=request.user)
        if order.status not in ('delivered', 'completed'):
            return Response({'error': 'invalid_status', 'detail': 'Só pode pedir devolução de pedidos entregues.'}, status=400)
        from apps.orders.return_models import ReturnRequest
        if ReturnRequest.objects.filter(order=order, buyer=request.user).exists():
            return Response({'error': 'duplicate', 'detail': 'Pedido de devolução já submetido.'}, status=400)

        reason = (request.data.get('reason') or '').strip()
        if reason not in self.VALID_REASONS:
            return Response({'error': 'validation_error', 'detail': 'Motivo inválido.'}, status=400)

        pickup_method = (request.data.get('pickup_method') or 'pickup').strip()
        if pickup_method not in self.VALID_PICKUPS:
            pickup_method = 'pickup'

        description = (request.data.get('description') or '').strip()[:2000]
        photo = request.FILES.get('photo')

        ret = ReturnRequest.objects.create(
            order=order,
            buyer=request.user,
            reason=reason,
            description=description,
            pickup_method=pickup_method,
            photo=photo,
        )
        return Response({
            **self._serialize(ret, request),
            'detail': 'Pedido de devolução submetido. Entraremos em contacto em até 24h.'
        }, status=201)

    def get(self, request, pk):
        order = get_object_or_404(Order, pk=pk, buyer=request.user)
        from apps.orders.return_models import ReturnRequest
        try:
            ret = ReturnRequest.objects.get(order=order, buyer=request.user)
            return Response(self._serialize(ret, request))
        except ReturnRequest.DoesNotExist:
            return Response({'error': 'not_found', 'detail': 'Sem pedido de devolução.'}, status=404)


class OrderTrackingEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderTrackingEvent
        fields = ['id', 'code', 'description', 'location', 'occurred_at']
        read_only_fields = ['id', 'occurred_at']


class OrderTrackingView(APIView):
    """GET  /api/v1/orders/<uuid:pk>/tracking/  — buyer or seller views events.
    POST /api/v1/orders/<uuid:pk>/tracking/  — seller adds a manual checkpoint.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def _get_order(self, request, pk):
        from django.db.models import Q
        return get_object_or_404(
            Order.objects.filter(Q(buyer=request.user) | Q(seller=request.user)),
            pk=pk,
        )

    def get(self, request, pk):
        order = self._get_order(request, pk)
        qs = order.tracking_events.all()
        if order.buyer_id == request.user.id and order.seller_id != request.user.id:
            qs = qs.filter(is_visible_to_buyer=True)
        serializer = OrderTrackingEventSerializer(qs, many=True)
        return Response({
            'order_id': str(order.id),
            'status': order.status,
            'tracking_number': order.tracking_number or '',
            'events': serializer.data,
        })

    def post(self, request, pk):
        order = self._get_order(request, pk)
        # Only the seller (or staff) can add manual events
        if order.seller_id != request.user.id and not request.user.is_staff:
            return Response({'error': 'forbidden', 'detail': 'Apenas o vendedor pode adicionar eventos.'}, status=403)
        code = (request.data.get('code') or '').strip()[:30]
        description = (request.data.get('description') or '').strip()[:300]
        location = (request.data.get('location') or '').strip()[:120]
        if not (code or description):
            return Response({'error': 'validation_error', 'detail': 'code or description is required.'}, status=400)
        event = OrderTrackingEvent.objects.create(
            order=order,
            code=code or 'update',
            description=description,
            location=location,
            is_visible_to_buyer=bool(request.data.get('is_visible_to_buyer', True)),
            created_by=request.user,
        )
        return Response(OrderTrackingEventSerializer(event).data, status=201)


def _serialize_return(ret, request):
    photo_url = None
    if ret.photo:
        try:
            photo_url = request.build_absolute_uri(ret.photo.url)
        except Exception:
            photo_url = ret.photo.url
    buyer_name = ''
    try:
        buyer_name = (
            getattr(ret.buyer, 'profile', None) and ret.buyer.profile.full_name
        ) or ret.buyer.email.split('@')[0]
    except Exception:
        pass
    return {
        'id': ret.id,
        'order_id': str(ret.order_id),
        'order_number': str(ret.order_id)[:8].upper(),
        'buyer_email': ret.buyer.email,
        'buyer_name': buyer_name,
        'reason': ret.reason,
        'description': ret.description,
        'pickup_method': ret.pickup_method,
        'refund_destination': getattr(ret, 'refund_destination', 'store_credit'),
        'photo_url': photo_url,
        'status': ret.status,
        'admin_note': ret.admin_note,
        'seller_response_deadline_at': getattr(ret, 'seller_response_deadline_at', None),
        'pickup_deadline_at': getattr(ret, 'pickup_deadline_at', None),
        'escalation_deadline_at': getattr(ret, 'escalation_deadline_at', None),
        'refunded_amount': str(getattr(ret, 'refunded_amount', 0) or 0),
        'restocked': bool(getattr(ret, 'restocked', False)),
        'created_at': ret.created_at,
        'updated_at': ret.updated_at,
    }


class SellerReturnListView(APIView):
    """GET /api/v1/orders/returns/seller/  — all return requests for this seller's orders."""
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended, IsSellerOrSuperuser]

    def get(self, request):
        from apps.orders.return_models import ReturnRequest
        qs = ReturnRequest.objects.filter(
            order__seller=request.user
        ).select_related('order', 'buyer').order_by('-created_at')

        status_filter = request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)

        return Response({
            'results': [_serialize_return(r, request) for r in qs[:100]],
        })


_SELLER_ACTION_MAP = {
    'approved':  'seller_approve',
    'rejected':  'seller_reject',
    'completed': 'seller_complete',
}


class SellerReturnActionView(APIView):
    """PATCH /api/v1/orders/returns/<id>/  — seller approves / rejects / completes a return.

    All transitions go through return_service so the state machine is enforced,
    audit events are recorded, and the completion saga fires (refund + restock
    in one atomic-with-compensation unit).

    Idempotency REQUIRED. ``complete`` fires a saga that performs refund +
    restock. State-machine guards inside return_service would refuse a
    second ``complete`` (already-completed → TransitionError), but a
    concurrent retry inside the same lock window can both pass the guard
    and both attempt the saga.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended, IsSellerOrSuperuser]

    @idempotent(required=True)
    def patch(self, request, pk):
        from apps.orders.return_models import ReturnRequest
        from apps.orders import return_service

        ret = get_object_or_404(
            ReturnRequest.objects.select_related('order'),
            pk=pk, order__seller=request.user,
        )
        new_status = (request.data.get('status') or '').strip()
        action_name = _SELLER_ACTION_MAP.get(new_status)
        if action_name is None:
            return Response(
                {'error': 'validation_error', 'detail': 'Status inválido.'},
                status=400,
            )

        note = (request.data.get('admin_note') or '').strip()[:2000]
        if note:
            ret.admin_note = note
            ret.save(update_fields=['admin_note', 'updated_at'])

        try:
            action = getattr(return_service, action_name)
            ret = action(ret, actor=request.user, note=note)
        except return_service.TransitionError as e:
            return Response(
                {'error': 'invalid_transition', 'detail': str(e)},
                status=400,
            )

        return Response(_serialize_return(ret, request))


class BuyerReturnActionView(APIView):
    """PATCH /api/v1/orders/returns/<id>/buyer-action/  — buyer withdraws or escalates.

    Idempotency REQUIRED. Escalation creates a Case row and notifies
    ops; duplicate retry = duplicate Case row + duplicate ops ping.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    @idempotent(required=True)
    def patch(self, request, pk):
        from apps.orders.return_models import ReturnRequest
        from apps.orders import return_service

        ret = get_object_or_404(
            ReturnRequest.objects.select_related('order'),
            pk=pk, buyer=request.user,
        )
        action = (request.data.get('action') or '').strip()
        note = (request.data.get('note') or '').strip()[:500]

        try:
            if action == 'withdraw':
                ret = return_service.buyer_withdraw(ret, actor=request.user, note=note)
            elif action == 'escalate':
                ret = return_service.buyer_escalate(ret, actor=request.user, note=note)
            else:
                return Response(
                    {'error': 'validation_error',
                     'detail': 'action must be "withdraw" or "escalate".'},
                    status=400,
                )
        except return_service.TransitionError as e:
            return Response(
                {'error': 'invalid_transition', 'detail': str(e)},
                status=400,
            )

        return Response(_serialize_return(ret, request))


class AdminReturnOverrideView(APIView):
    """POST /api/v1/orders/returns/<id>/admin-override/  — force any transition.

    Bypasses the state machine guard but still records the change in the
    audit trail with admin_override=True.
    """
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def post(self, request, pk):
        from apps.orders.return_models import ReturnRequest, ReturnStatus
        from apps.orders import return_service

        ret = get_object_or_404(ReturnRequest, pk=pk)
        new_status = (request.data.get('status') or '').strip()
        valid = {s.value for s in ReturnStatus}
        if new_status not in valid:
            return Response(
                {'error': 'validation_error',
                 'detail': f'status must be one of {sorted(valid)}'},
                status=400,
            )
        note = (request.data.get('note') or '').strip()[:500]
        ret = return_service.transition(
            ret, new_status,
            actor=request.user, actor_role='admin',
            note=note, admin_override=True,
        )
        return Response(_serialize_return(ret, request))


# ─── AliExpress Complete 2025 CH 21.2 — Batch Ship ─────────────────

class BatchShipView(APIView):
    """POST /api/v1/orders/seller/batch-ship/  (multipart)

    Seller uploads a CSV with header: order_id,tracking_number,carrier
    Each row attempts to flip the order to ``shipped`` with the given
    tracking. Failures are reported per-row so the seller can fix &
    re-upload only the rejected rows. Owner-scoped: only the seller's
    own orders can be updated.
    """
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]
    parser_classes = [MultiPartParser]

    def post(self, request):
        import csv as _csv
        f = request.FILES.get('file')
        if not f:
            return Response({'error': 'file required (csv)'}, status=400)
        try:
            text = f.read().decode('utf-8', errors='ignore').splitlines()
        except Exception:
            return Response({'error': 'unreadable file'}, status=400)
        reader = _csv.DictReader(text)
        results = {'ok': [], 'failed': []}
        for i, row in enumerate(reader, start=2):  # 1 = header
            oid = (row.get('order_id') or '').strip()
            track = (row.get('tracking_number') or '').strip()
            carrier = (row.get('carrier') or '').strip() or 'AliExpress Standard'
            if not oid or not track:
                results['failed'].append({'line': i, 'reason': 'missing order_id or tracking'})
                continue
            try:
                order = Order.objects.get(pk=oid, seller=request.user)
            except Order.DoesNotExist:
                results['failed'].append({'line': i, 'order_id': oid, 'reason': 'not_found_or_not_yours'})
                continue
            if order.status != 'confirmed':
                results['failed'].append({'line': i, 'order_id': oid, 'reason': f'status={order.status}'})
                continue
            order.tracking_number = track
            order.carrier = carrier
            order.update_status('shipped', changed_by=request.user, note=f'Batch ship · CSV line {i}')
            order.save(update_fields=['tracking_number', 'carrier'])
            results['ok'].append({'line': i, 'order_id': oid})
        # Log to UserEvent.
        try:
            from apps.analytics.models import UserEvent
            UserEvent.objects.create(user=request.user, event='seller.batch_ship',
                properties={'ok': len(results['ok']), 'failed': len(results['failed'])})
        except Exception:
            pass
        return Response(results)


# ─── AliExpress Complete 2025 CH 21.2 — Per-seller checkout note ──

class OrderMessagesView(APIView):
    """POST /api/v1/orders/<pk>/buyer-message/

    Buyer-attached free-text note to the order seller. Spec CH 11
    "Leave Message" textarea. Stored on `Order.notes`. Length-capped.
    """
    permission_classes = [permissions.IsAuthenticated, IsNotSuspended]

    def post(self, request, pk):
        order = get_object_or_404(Order, pk=pk, buyer=request.user)
        msg = (request.data.get('message') or '').strip()[:500]
        order.notes = msg
        order.save(update_fields=['notes'])
        try:
            from apps.analytics.models import UserEvent
            UserEvent.objects.create(user=request.user, event='order.buyer_message',
                properties={'order_id': str(order.id), 'len': len(msg)})
        except Exception:
            pass
        return Response({'detail': 'Mensagem guardada.'})
