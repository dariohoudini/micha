"""Buyer experience — REST endpoints under /api/v1/buyer-experience/."""
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import (
    BulkInquiry, BuyerExperienceKpiSnapshot, PrePurchaseQuestion,
    ProductSubscription,
)


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.is_staff)


# ── CH2 gift options ──────────────────────────────────────────────────

class GiftOptionsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        opts = services.set_gift_options(
            request.user, order_id=request.data.get('order_id'),
            is_gift=bool(request.data.get('is_gift')),
            gift_message=request.data.get('gift_message', ''),
            hide_price=bool(request.data.get('hide_price', True)),
            gift_wrap=request.data.get('gift_wrap', 'none'))
        return Response({'id': opts.id, 'wrap_fee_cents': opts.gift_wrap_fee_cents},
                        status=status.HTTP_201_CREATED)


# ── CH3 subscriptions ─────────────────────────────────────────────────

class SubscriptionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({'subscriptions': [
            {'id': str(s.id), 'product_id': s.product_id,
             'frequency_days': s.frequency_days, 'next_order_date': s.next_order_date,
             'discount_pct': str(s.discount_pct), 'status': s.status,
             'total_orders': s.total_orders}
            for s in ProductSubscription.objects.filter(buyer=request.user)]})

    def post(self, request):
        try:
            sub = services.create_subscription(
                request.user, product_id=request.data.get('product_id'),
                sku_id=request.data.get('sku_id', ''),
                quantity=int(request.data.get('quantity', 1)),
                frequency_days=int(request.data.get('frequency_days', 30)),
                discount_pct=request.data.get('discount_pct', 8),
                payment_method=request.data.get('payment_method', 'wallet'))
        except ValueError as exc:
            return Response({'error': str(exc)},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({'id': str(sub.id), 'next_order_date': sub.next_order_date},
                        status=status.HTTP_201_CREATED)


class SubscriptionActionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, sub_id):
        sub = ProductSubscription.objects.filter(
            id=sub_id, buyer=request.user).first()
        if not sub:
            return Response({'error': 'not found'},
                            status=status.HTTP_404_NOT_FOUND)
        action = request.data.get('action')
        if action == 'pause':
            services.pause_subscription(sub)
        elif action == 'resume':
            services.resume_subscription(sub)
        elif action == 'skip':
            services.skip_next(sub)
        elif action == 'change_frequency':
            services.change_frequency(sub, int(request.data.get(
                'frequency_days', 30)))
        elif action == 'cancel':
            services.cancel_subscription(sub)
        else:
            return Response({'error': 'invalid action'},
                            status=status.HTTP_400_BAD_REQUEST)
        sub.refresh_from_db()
        return Response({'status': sub.status,
                         'next_order_date': sub.next_order_date})


# ── CH4 price history ─────────────────────────────────────────────────

class PriceHistoryView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request, product_id):
        return Response(services.price_history(
            product_id, days=int(request.query_params.get('days', 90)),
            sku_id=request.query_params.get('sku_id', '')))


# ── CH7 pre-purchase questions ────────────────────────────────────────

class QuestionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from django.contrib.auth import get_user_model
        seller = get_user_model().objects.filter(
            id=request.data.get('seller_id')).first()
        if not seller:
            return Response({'error': 'seller not found'},
                            status=status.HTTP_404_NOT_FOUND)
        q = services.ask_question(
            request.user, product_id=request.data.get('product_id'),
            seller=seller, question_text=request.data.get('question_text', ''),
            attachment_key=request.data.get('attachment_key', ''))
        return Response({'id': str(q.id), 'status': q.status},
                        status=status.HTTP_201_CREATED)


class QuestionAnswerView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, question_id):
        q = PrePurchaseQuestion.objects.filter(
            id=question_id, seller=request.user).first()
        if not q:
            return Response({'error': 'not found'},
                            status=status.HTTP_404_NOT_FOUND)
        services.answer_question(q, answer_text=request.data.get(
            'answer_text', ''))
        return Response({'status': 'answered'})


# ── CH8 bulk inquiry ──────────────────────────────────────────────────

class BulkInquiryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        from django.contrib.auth import get_user_model
        seller = get_user_model().objects.filter(
            id=request.data.get('seller_id')).first()
        if not seller:
            return Response({'error': 'seller not found'},
                            status=status.HTTP_404_NOT_FOUND)
        inq = services.create_bulk_inquiry(
            request.user, seller=seller,
            product_id=request.data.get('product_id'),
            quantity=int(request.data.get('quantity', 1)),
            delivery_province=request.data.get('delivery_province', ''),
            purpose=request.data.get('purpose', 'resale'),
            buyer_message=request.data.get('buyer_message', ''),
            company_name=request.data.get('company_name', ''),
            nif=request.data.get('nif', ''))
        return Response({'id': str(inq.id)}, status=status.HTTP_201_CREATED)


class BulkQuoteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, inquiry_id):
        inq = BulkInquiry.objects.filter(id=inquiry_id).first()
        if not inq:
            return Response({'error': 'not found'},
                            status=status.HTTP_404_NOT_FOUND)
        if inq.seller_id == request.user.id:
            services.quote_inquiry(
                inq,
                price_per_unit_cents=int(request.data.get(
                    'price_per_unit_cents', 0)),
                message=request.data.get('message', ''))
            return Response({'status': 'quoted'})
        if inq.buyer_id == request.user.id and request.data.get('accept'):
            result = services.accept_quote(
                inq, order_id=request.data.get('order_id', ''))
            return Response(result)
        return Response({'error': 'forbidden'},
                        status=status.HTTP_403_FORBIDDEN)


# ── CH10 saved comparison ─────────────────────────────────────────────

class ComparisonView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        comp = services.save_comparison(
            request.user, product_ids=request.data.get('product_ids', []),
            name=request.data.get('name', ''))
        return Response({'id': comp.id, 'share_code': comp.share_code},
                        status=status.HTTP_201_CREATED)


# ── CH12 quick reorder ────────────────────────────────────────────────

class ReorderCheckView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, order_id):
        return Response(services.reorder_check(request.user, order_id))


# ── CH14 price watch ──────────────────────────────────────────────────

class PriceWatchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        w = services.watch_price(
            request.user, product_id=request.data.get('product_id'),
            sku_id=request.data.get('sku_id', ''),
            threshold_pct=request.data.get('threshold_pct', 5))
        return Response({'id': w.id, 'price_at_add_cents': w.price_at_add_cents},
                        status=status.HTTP_201_CREATED)


# ── CH18 age gate ─────────────────────────────────────────────────────

class AgeGateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({'cleared': services.is_age_cleared(request.user)})

    def post(self, request):
        return Response(services.verify_age(
            request.user, confirmed=bool(request.data.get('confirmed'))))


# ── CH23 dashboard ────────────────────────────────────────────────────

class AccountSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(services.account_summary(request.user))


# ── CH24 KPIs ─────────────────────────────────────────────────────────

class KpiView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        return Response({'snapshots': [
            {'date': s.snapshot_date,
             'subscribe_save_retention_pct': str(s.subscribe_save_retention_pct),
             'review_photo_pct': str(s.review_photo_pct),
             'active_subscriptions': s.active_subscriptions,
             'pending_bulk_inquiries': s.pending_bulk_inquiries,
             'pending_questions': s.pending_questions}
            for s in BuyerExperienceKpiSnapshot.objects.order_by(
                '-snapshot_date')[:30]]})

    def post(self, request):
        snap = services.snapshot_kpis()
        return Response({'date': snap.snapshot_date},
                        status=status.HTTP_201_CREATED)
