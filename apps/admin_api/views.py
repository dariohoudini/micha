"""
apps/admin_api/views.py

Admin dashboard API — serves real data to the frontend admin panel.
All endpoints require is_staff=True.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django.utils import timezone
from django.db.models import Count, Sum, Avg, Q
from datetime import timedelta, date


class AdminDashboardStatsView(APIView):
    """GET /api/admin/stats/ — Platform overview for admin dashboard."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)

        stats = {}

        # Users
        try:
            stats['users'] = {
                'total': User.objects.count(),
                'today': User.objects.filter(date_joined__date=today).count(),
                'this_week': User.objects.filter(date_joined__date__gte=week_ago).count(),
                'sellers': User.objects.filter(is_seller=True).count(),
                'active': User.objects.filter(is_active=True).count(),
                'suspended': User.objects.filter(is_active=False).count(),
            }
        except Exception:
            stats['users'] = {}

        # Orders
        try:
            from apps.orders.models import Order
            orders_today = Order.objects.filter(created_at__date=today)
            orders_yesterday = Order.objects.filter(created_at__date=yesterday)

            gmv_today = orders_today.filter(
                status='delivered'
            ).aggregate(total=Sum('total'))['total'] or 0

            gmv_yesterday = orders_yesterday.filter(
                status='delivered'
            ).aggregate(total=Sum('total'))['total'] or 1

            stats['orders'] = {
                'today': orders_today.count(),
                'yesterday': orders_yesterday.count(),
                'this_week': Order.objects.filter(created_at__date__gte=week_ago).count(),
                'pending': Order.objects.filter(status='pending').count(),
                'disputes': Order.objects.filter(status='dispute').count(),
                'gmv_today': float(gmv_today),
                'gmv_yesterday': float(gmv_yesterday),
                'gmv_change_pct': round(((float(gmv_today) - float(gmv_yesterday)) / float(gmv_yesterday)) * 100, 1),
            }
        except Exception:
            stats['orders'] = {}

        # Products
        try:
            from apps.products.models import Product
            stats['products'] = {
                'total': Product.objects.count(),
                'active': Product.objects.filter(is_active=True).count(),
                'pending_review': Product.objects.filter(
                    is_active=False, is_approved=False
                ).count() if hasattr(Product, 'is_approved') else 0,
            }
        except Exception:
            stats['products'] = {}

        # Revenue (platform commission)
        try:
            from apps.payments.models import Payment
            commission_today = Payment.objects.filter(
                created_at__date=today,
                status='completed'
            ).aggregate(total=Sum('platform_fee'))['total'] or 0
            stats['revenue'] = {
                'commission_today': float(commission_today),
            }
        except Exception:
            stats['revenue'] = {}

        # AI stats
        try:
            from apps.ai_engine.models import UserTasteProfile, SearchQuery, AIConversation
            stats['ai'] = {
                'profiles_with_quiz': UserTasteProfile.objects.filter(quiz_completed=True).count(),
                'searches_today': SearchQuery.objects.filter(created_at__date=today).count(),
                'ai_chats_today': AIConversation.objects.filter(created_at__date=today).count(),
            }
        except Exception:
            stats['ai'] = {}

        return Response(stats)


class AdminUsersListView(APIView):
    """GET /api/admin/users/?page=1&status=active&role=buyer&search=..."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        qs = User.objects.all().order_by('-date_joined')

        # Filters
        search = request.query_params.get('search', '')
        if search:
            qs = qs.filter(
                Q(email__icontains=search) |
                Q(username__icontains=search) |
                Q(phone__icontains=search)
            )

        status = request.query_params.get('status', '')
        if status == 'active':
            qs = qs.filter(is_active=True)
        elif status == 'suspended':
            qs = qs.filter(is_active=False)

        role = request.query_params.get('role', '')
        if role == 'seller':
            qs = qs.filter(is_seller=True)
        elif role == 'buyer':
            qs = qs.filter(is_seller=False, is_staff=False)
        elif role == 'admin':
            qs = qs.filter(is_staff=True)

        # Pagination
        page = int(request.query_params.get('page', 1))
        per_page = 20
        total = qs.count()
        users = qs[(page-1)*per_page:page*per_page]

        data = []
        for u in users:
            data.append({
                'id': str(u.id),
                'email': u.email,
                'username': getattr(u, 'username', u.email.split('@')[0]),
                'phone': getattr(u, 'phone', ''),
                'is_active': u.is_active,
                'is_seller': getattr(u, 'is_seller', False),
                'is_staff': u.is_staff,
                'is_email_verified': getattr(u, 'is_email_verified', False),
                'date_joined': u.date_joined.isoformat(),
                'last_login': u.last_login.isoformat() if u.last_login else None,
            })

        return Response({
            'results': data,
            'total': total,
            'page': page,
            'pages': (total + per_page - 1) // per_page,
        })


class AdminUserActionView(APIView):
    """POST /api/admin/users/<id>/action/ — suspend/activate/ban a user."""
    permission_classes = [IsAdminUser]

    def post(self, request, user_id):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

        action = request.data.get('action')
        if action == 'suspend':
            user.is_active = False
            user.save()
            return Response({'status': 'suspended'})
        elif action == 'activate':
            user.is_active = True
            user.save()
            return Response({'status': 'activated'})
        elif action == 'make_seller':
            user.is_seller = True
            user.save()
            return Response({'status': 'seller_enabled'})

        return Response({'error': 'Invalid action'}, status=400)


class AdminOrdersListView(APIView):
    """GET /api/admin/orders/?page=1&status=dispute&search=..."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        try:
            from apps.orders.models import Order

            qs = Order.objects.select_related('user', 'seller').order_by('-created_at')

            search = request.query_params.get('search', '')
            if search:
                qs = qs.filter(
                    Q(id__icontains=search) |
                    Q(user__email__icontains=search)
                )

            status = request.query_params.get('status', '')
            if status:
                qs = qs.filter(status=status)

            page = int(request.query_params.get('page', 1))
            per_page = 20
            total = qs.count()
            orders = qs[(page-1)*per_page:page*per_page]

            data = []
            for o in orders:
                data.append({
                    'id': str(o.id),
                    'buyer_email': o.user.email if o.user else '',
                    'seller_email': o.seller.email if hasattr(o, 'seller') and o.seller else '',
                    'total': float(o.total),
                    'status': o.status,
                    'created_at': o.created_at.isoformat(),
                    'has_dispute': o.status == 'dispute',
                })

            return Response({
                'results': data,
                'total': total,
                'page': page,
                'pages': (total + per_page - 1) // per_page,
            })
        except Exception as e:
            return Response({'results': [], 'total': 0, 'error': str(e)})


class AdminOrderDisputeView(APIView):
    """POST /api/admin/orders/<id>/resolve/ — resolve a dispute."""
    permission_classes = [IsAdminUser]

    def post(self, request, order_id):
        try:
            from apps.orders.models import Order
            order = Order.objects.get(id=order_id)
            favour = request.data.get('favour')  # 'buyer' or 'seller'

            if favour == 'buyer':
                order.status = 'cancelled'
            elif favour == 'seller':
                order.status = 'delivered'
            else:
                return Response({'error': 'favour must be buyer or seller'}, status=400)

            order.save()

            # Record trust event for seller
            try:
                from apps.trust.services import TrustScoreService
                if favour == 'buyer' and hasattr(order, 'seller'):
                    TrustScoreService.record_event(
                        seller=order.seller,
                        event_type='dispute_lost',
                        order_id=order.id,
                    )
                elif favour == 'seller' and hasattr(order, 'seller'):
                    TrustScoreService.record_event(
                        seller=order.seller,
                        event_type='dispute_won',
                        order_id=order.id,
                    )
            except Exception:
                pass

            return Response({'status': 'resolved', 'favour': favour})
        except Exception as e:
            return Response({'error': str(e)}, status=400)


class AdminSellersListView(APIView):
    """GET /api/admin/sellers/?status=pending"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        qs = User.objects.filter(is_seller=True).order_by('-date_joined')

        status = request.query_params.get('status', '')
        search = request.query_params.get('search', '')

        if search:
            qs = qs.filter(Q(email__icontains=search) | Q(username__icontains=search))

        page = int(request.query_params.get('page', 1))
        per_page = 20
        total = qs.count()
        sellers = qs[(page-1)*per_page:page*per_page]

        data = []
        for s in sellers:
            # Get trust score
            trust_data = {}
            try:
                score = s.trust_score
                trust_data = {
                    'overall_score': score.overall_score,
                    'badge_level': score.badge_level,
                    'badge_label': score.badge_label,
                    'total_orders': score.total_orders,
                    'avg_rating': score.avg_rating,
                }
            except Exception:
                pass

            data.append({
                'id': str(s.id),
                'email': s.email,
                'username': getattr(s, 'username', ''),
                'is_active': s.is_active,
                'date_joined': s.date_joined.isoformat(),
                'trust': trust_data,
            })

        return Response({
            'results': data,
            'total': total,
            'page': page,
            'pages': (total + per_page - 1) // per_page,
        })


class AdminProductsListView(APIView):
    """GET /api/admin/products/?status=pending"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        try:
            from apps.products.models import Product
            from django.db.models import Q

            qs = Product.objects.select_related('seller').order_by('-created_at')

            search = request.query_params.get('search', '')
            if search:
                qs = qs.filter(Q(name__icontains=search))

            status = request.query_params.get('status', '')
            if status == 'pending':
                qs = qs.filter(is_active=False)
            elif status == 'active':
                qs = qs.filter(is_active=True)

            page = int(request.query_params.get('page', 1))
            per_page = 20
            total = qs.count()
            products = qs[(page-1)*per_page:page*per_page]

            data = [{
                'id': str(p.id),
                'name': p.name,
                'price': float(p.price),
                'category': str(p.category),
                'is_active': p.is_active,
                'seller_email': p.seller.email if hasattr(p, 'seller') and p.seller else '',
                'created_at': p.created_at.isoformat(),
            } for p in products]

            return Response({
                'results': data,
                'total': total,
                'page': page,
                'pages': (total + per_page - 1) // per_page,
            })
        except Exception as e:
            return Response({'results': [], 'total': 0, 'error': str(e)})


class AdminProductActionView(APIView):
    """POST /api/admin/products/<id>/action/ — approve/reject product."""
    permission_classes = [IsAdminUser]

    def post(self, request, product_id):
        try:
            from apps.products.models import Product
            product = Product.objects.get(id=product_id)
            action = request.data.get('action')

            if action == 'approve':
                product.is_active = True
                product.save()
                # Trigger AI embedding
                try:
                    from apps.ai_engine.tasks import embed_single_product
                    embed_single_product.delay(str(product.id))
                except Exception:
                    pass
                return Response({'status': 'approved'})

            elif action == 'reject':
                product.is_active = False
                product.save()
                return Response({'status': 'rejected'})

            return Response({'error': 'Invalid action'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=400)


class AdminRevenueChartView(APIView):
    """GET /api/admin/revenue/?period=7 — Revenue chart data."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        period = int(request.query_params.get('period', 7))
        today = timezone.now().date()

        data = []
        try:
            from apps.orders.models import Order
            for i in range(period - 1, -1, -1):
                day = today - timedelta(days=i)
                gmv = Order.objects.filter(
                    created_at__date=day,
                    status='delivered'
                ).aggregate(total=Sum('total'))['total'] or 0

                orders = Order.objects.filter(created_at__date=day).count()

                data.append({
                    'date': day.isoformat(),
                    'day': day.strftime('%a'),
                    'gmv': float(gmv),
                    'orders': orders,
                })
        except Exception:
            pass

        return Response({'data': data, 'period': period})
