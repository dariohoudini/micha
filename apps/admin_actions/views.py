from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import generics, permissions, serializers
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.users.permissions import IsAdminOrSuperuser
from .models import AdminActionLog, AdminAction, ProductModeration

User = get_user_model()


class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'email', 'phone', 'is_seller', 'is_verified_seller',
                  'status', 'date_joined', 'is_active', 'loyalty_points']
        read_only_fields = fields


class AdminUserListView(generics.ListAPIView):
    """GET /api/admin-actions/users/ — list all users"""
    serializer_class = AdminUserSerializer
    permission_classes = [IsAdminOrSuperuser]

    def get_queryset(self):
        qs = User.objects.all().order_by('-date_joined')
        status = self.request.query_params.get('status')
        if status:
            qs = qs.filter(status=status)
        search = self.request.query_params.get('search')
        if search:
            qs = qs.filter(email__icontains=search)
        return qs


class AdminUserDetailView(APIView):
    """GET/PATCH /api/admin-actions/users/<id>/ — view or moderate user"""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        return Response(AdminUserSerializer(user).data)

    def patch(self, request, pk):
        user = get_object_or_404(User, pk=pk)
        action = request.data.get('action')
        note = request.data.get('note', '')

        if action == 'suspend':
            old_status = user.status
            user.status = 'suspended'
            user.save(update_fields=['status'])
            AdminActionLog.log(request, 'suspend_user', user, note,
                               metadata={'previous_status': old_status})
            return Response({'detail': f'User {user.email} suspended.'})

        elif action == 'ban':
            user.status = 'banned'
            user.is_active = False
            user.save(update_fields=['status', 'is_active'])
            AdminActionLog.log(request, 'ban_user', user, note)
            return Response({'detail': f'User {user.email} banned.'})

        elif action == 'activate':
            user.status = 'active'
            user.is_active = True
            user.save(update_fields=['status', 'is_active'])
            AdminActionLog.log(request, 'activate_user', user, note)
            return Response({'detail': f'User {user.email} activated.'})

        return Response({'error': 'validation_error',
                         'detail': 'action must be: suspend, ban, or activate'}, status=400)


class AdminProductListView(APIView):
    """GET /api/admin-actions/products/ — all products with moderation status"""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        from apps.products.models import Product
        qs = Product.objects.select_related('store', 'category').order_by('-created_at')
        status = request.query_params.get('status')
        if status == 'flagged':
            from apps.trust.models import ContentFlag
            flagged_ids = ContentFlag.objects.filter(reviewed=False).values_list('product_id', flat=True)
            qs = qs.filter(id__in=flagged_ids)
        from middleware.pagination import StandardPagination
        paginator = StandardPagination()
        page = paginator.paginate_queryset(qs, request)
        data = [{'id': p.id, 'title': p.title, 'store': p.store.name,
                 'is_active': p.is_active, 'created_at': str(p.created_at)} for p in page]
        return paginator.get_paginated_response(data)


class AdminAnalyticsView(APIView):
    """GET /api/admin-actions/analytics/ — platform-wide stats"""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        from apps.orders.models import Order
        from apps.products.models import Product
        from django.db.models import Sum, Count

        today = timezone.now().date()
        orders_today = Order.objects.filter(created_at__date=today)

        return Response({
            'users': {
                'total': User.objects.count(),
                'sellers': User.objects.filter(is_seller=True).count(),
                'verified_sellers': User.objects.filter(is_verified_seller=True).count(),
                'suspended': User.objects.filter(status='suspended').count(),
            },
            'products': {
                'total': Product.objects.count(),
                'active': Product.objects.filter(is_active=True).count(),
            },
            'orders': {
                'total': Order.objects.count(),
                'today': orders_today.count(),
                'revenue_today': str(
                    orders_today.filter(payment_status='paid').aggregate(
                        total=Sum('total')
                    )['total'] or 0
                ),
            },
            'admin_actions': {
                'total_today': AdminActionLog.objects.filter(
                    created_at__date=today
                ).count(),
            },
        })


class AdminPayoutListView(generics.ListAPIView):
    """GET /api/admin-actions/payouts/ — pending payout requests"""
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        from apps.payments.models import PayoutRequest
        status = request.query_params.get('status', 'pending')
        payouts = PayoutRequest.objects.filter(status=status).select_related('seller', 'bank_account')
        return Response([{
            'id': str(p.id),
            'seller': p.seller.email,
            'amount': str(p.amount),
            'status': p.status,
            'created_at': str(p.created_at),
        } for p in payouts])


class AdminPayoutActionView(APIView):
    """PATCH /api/admin-actions/payouts/<id>/ — approve or reject payout"""
    permission_classes = [IsAdminOrSuperuser]

    def patch(self, request, pk):
        from apps.payments.models import PayoutRequest, SellerWallet, WalletTransaction
        from django.db import transaction

        payout = get_object_or_404(PayoutRequest, pk=pk)
        action = request.data.get('action')
        note = request.data.get('note', '')

        if action not in ('approved', 'processing', 'completed', 'rejected'):
            return Response({'error': 'validation_error',
                             'detail': 'action must be: approved, processing, completed, rejected'}, status=400)

        with transaction.atomic():
            payout.status = action
            payout.admin_note = note
            if action == 'completed':
                payout.processed_at = timezone.now()
            elif action == 'rejected':
                wallet, _ = SellerWallet.objects.get_or_create(seller=payout.seller)
                wallet.credit(float(payout.amount), f'Payout rejected — refunded', reference=str(payout.id))
            payout.save()

        AdminActionLog.log(request, f'{"approve" if action == "approved" else action}_payout',
                           payout.seller, note, metadata={'payout_id': str(payout.id), 'amount': str(payout.amount)})

        return Response({'detail': f'Payout {action}.'})
