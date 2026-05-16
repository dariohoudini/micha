"""
apps/admin_api/views.py

Admin dashboard API — serves real data to the frontend admin panel.
All endpoints require is_staff=True.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from django.utils import timezone
from django.db.models import Sum, Q
from datetime import timedelta

from apps.admin_actions.decorators import audit_admin_action


# ─── Dynamic action resolvers ─────────────────────────────────────────────
def _user_action_name(request, kwargs):
    a = (request.data.get('action') or '').strip()
    return {
        'suspend':     'suspend_user',
        'activate':    'activate_user',
        'make_seller': 'assign_role',
    }.get(a, '')


def _product_action_name(request, kwargs):
    a = (request.data.get('action') or '').strip()
    return {'approve': 'feature_product', 'reject': 'remove_product'}.get(a, '')


def _ops_queue_action_name(request, kwargs):
    kind = kwargs.get('kind', '')
    a = (request.data.get('action') or '').strip()
    return f'ops_{kind}_{a}' if (kind and a) else ''


def _lookup_user(user_id):
    from django.contrib.auth import get_user_model
    return get_user_model().objects.filter(pk=user_id).first()


def _lookup_order(order_id):
    from apps.orders.models import Order
    return Order.objects.filter(pk=order_id).first()


def _lookup_product(product_id):
    from apps.products.models import Product
    return Product.objects.filter(pk=product_id).first()


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

    @audit_admin_action(_user_action_name, target_kwarg='user_id',
                        target_lookup=_lookup_user)
    def post(self, request, user_id):
        from django.contrib.auth import get_user_model
        User = get_user_model()

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'Não encontrado'}, status=404)

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

    @audit_admin_action(
        lambda req, kw: f'resolve_dispute_{(req.data.get("favour") or "").strip()}'
                        if (req.data.get('favour') or '').strip() in ('buyer', 'seller') else '',
        target_kwarg='order_id', target_lookup=_lookup_order,
    )
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

    @audit_admin_action(_product_action_name, target_kwarg='product_id',
                        target_lookup=_lookup_product)
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

                try:
                    from apps.users.models import User
                    users = User.objects.filter(date_joined__date=day).count()
                except Exception:
                    users = 0

                data.append({
                    'date': day.isoformat(),
                    'day': day.strftime('%a'),
                    'gmv': float(gmv),
                    'orders': orders,
                    'users': users,
                })
        except Exception:
            pass

        return Response({'data': data, 'period': period})


# ──────────────────────────────────────────────────────────────────────
# Operational Queue — single pane of glass for things needing humans
# ──────────────────────────────────────────────────────────────────────
class OpsQueueView(APIView):
    """GET /api/v1/admin-api/ops-queue/

    Aggregates every queue across the platform that automated systems
    can't close on their own. Designed to be the operator's home page:
    one screen, every escalation, every action accessible.

    Sections:
      fraud_holds     — RiskAssessment rows with action='hold' (recent)
      dead_events     — OutboxEvent rows whose handler exhausted retries
      pending_returns — ReturnRequest rows still in 'pending' state, with SLA
      ledger_drift    — currencies whose Σ credits ≠ Σ debits
      recent_alerts   — last 10 ops.alert outbox events
      webhook_failures — Seller webhooks auto-disabled by failure threshold
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        # Each section is fault-isolated — a missing table or query bug in
        # one queue must never blank the whole ops dashboard.
        def _safe(fn):
            try:
                return fn()
            except Exception:
                return []
        out = {
            'fraud_holds':       _safe(self._fraud_holds),
            'dead_events':       _safe(self._dead_events),
            'pending_returns':   _safe(self._pending_returns),
            'ledger_drift':      _safe(self._ledger_drift),
            'recent_alerts':     _safe(self._recent_alerts),
            'webhook_failures':  _safe(self._webhook_failures),
            'stuck_sagas':       _safe(self._stuck_sagas),
            'spoofed_webhooks':  _safe(self._spoofed_webhooks),
            'overdue_data_requests': _safe(self._overdue_data_requests),
        }
        out['totals'] = {k: len(v) for k, v in out.items()}
        return Response(out)

    def _overdue_data_requests(self):
        """Data-subject requests still in-flight past their SLA. Erase
        requests carry a 30-day regulatory deadline."""
        try:
            from apps.data_rights.models import DataSubjectRequest, RequestStatus
        except Exception:
            return []
        now = timezone.now()
        rows = (
            DataSubjectRequest.objects
            .filter(
                status__in=(RequestStatus.PENDING, RequestStatus.RUNNING,
                            RequestStatus.FAILED),
            )
            .order_by('sla_deadline_at')[:25]
        )
        out = []
        for r in rows:
            overdue = (
                r.sla_deadline_at is not None and r.sla_deadline_at < now
            )
            # Only surface OVERDUE requests OR failures (humans needed)
            if not overdue and r.status != RequestStatus.FAILED:
                continue
            out.append({
                'id': r.id, 'kind': r.kind, 'status': r.status,
                'user_email': r.user_email_at_request,
                'sla_deadline_at': r.sla_deadline_at,
                'created_at': r.created_at,
                'error': (r.error or '')[:200],
            })
        return out

    def _spoofed_webhooks(self):
        """Inbound webhook attempts rejected by signature/timestamp checks in
        the last 24h. Spike here = someone trying to forge provider callbacks."""
        try:
            from apps.inbound_webhooks.models import InboundWebhookEvent, WebhookStatus
        except Exception:
            return []
        from datetime import timedelta
        cutoff = timezone.now() - timedelta(hours=24)
        rows = (
            InboundWebhookEvent.objects
            .filter(
                received_at__gte=cutoff,
                status__in=(
                    WebhookStatus.SIGNATURE_INVALID,
                    WebhookStatus.MISSING_SIGNATURE,
                    WebhookStatus.STALE_TIMESTAMP,
                ),
            )
            .order_by('-received_at')[:25]
        )
        return [{
            'id': r.id, 'provider': r.provider, 'status': r.status,
            'source_ip': r.source_ip,
            'user_agent': (r.user_agent or '')[:120],
            'signature_excerpt': (r.signature_header or '')[:24],
            'received_at': r.received_at,
        } for r in rows]

    def _stuck_sagas(self):
        """Sagas in NEEDS_ATTENTION — compensation itself failed; humans must look."""
        try:
            from apps.sagas.models import Saga, SagaStatus
        except Exception:
            return []
        rows = (
            Saga.objects
            .filter(status=SagaStatus.NEEDS_ATTENTION)
            .order_by('-updated_at')[:25]
        )
        return [{
            'id': s.id, 'name': s.name,
            'ref_type': s.ref_type, 'ref_id': s.ref_id,
            'current_step': s.current_step,
            'error': (s.error or '')[:300],
            'created_at': s.created_at, 'updated_at': s.updated_at,
        } for s in rows]

    def _webhook_failures(self):
        try:
            from apps.webhooks.models import SellerWebhook
        except Exception:
            return []
        # Hooks auto-disabled by the failure-threshold guard, or active hooks
        # with a recent failure streak — both are worth a human's attention.
        rows = (
            SellerWebhook.objects
            .filter(consecutive_failures__gte=3)
            .select_related('seller')
            .order_by('-consecutive_failures', '-last_failure_at')[:25]
        )
        return [{
            'id': h.id,
            'seller_email': h.seller.email if h.seller_id else None,
            'url': h.url,
            'is_active': h.is_active,
            'consecutive_failures': h.consecutive_failures,
            'last_failure_at': h.last_failure_at,
            'last_success_at': h.last_success_at,
        } for h in rows]

    def _fraud_holds(self):
        try:
            from apps.risk.models import RiskAssessment, RiskAction
        except Exception:
            return []
        rows = (
            RiskAssessment.objects
            .filter(action__in=(RiskAction.HOLD, RiskAction.BLOCK))
            .select_related('user')
            .order_by('-created_at')[:25]
        )
        return [{
            'id': r.id,
            'user_id': r.user_id,
            'user_email': r.user.email if r.user_id else None,
            'ref_type': r.ref_type, 'ref_id': r.ref_id,
            'score': r.score, 'action': r.action,
            'reasons': r.reasons,
            'created_at': r.created_at,
        } for r in rows]

    def _dead_events(self):
        try:
            from apps.outbox.models import OutboxEvent, EventStatus
        except Exception:
            return []
        rows = (
            OutboxEvent.objects
            .filter(status=EventStatus.DEAD)
            .order_by('-updated_at')[:25]
        )
        return [{
            'id': r.id, 'topic': r.topic,
            'ref_type': r.ref_type, 'ref_id': r.ref_id,
            'attempts': r.attempts,
            'last_error': (r.last_error or '')[:300],
            'created_at': r.created_at, 'updated_at': r.updated_at,
        } for r in rows]

    def _pending_returns(self):
        """Returns that need a human now: escalated (buyer disputed a rejection),
        plus pending ones approaching their seller-SLA deadline."""
        try:
            from apps.orders.return_models import ReturnRequest, ReturnStatus
        except Exception:
            return []
        # Escalated returns: top priority. Plus any pending ones whose deadline
        # is within the next 6h (so ops can nudge sellers before auto-approve).
        from datetime import timedelta
        now = timezone.now()
        cutoff = now + timedelta(hours=6)
        rows = (
            ReturnRequest.objects
            .filter(
                status__in=(ReturnStatus.ESCALATED, ReturnStatus.PENDING),
            )
            .select_related('order', 'buyer')
            .order_by('seller_response_deadline_at')[:25]
        )
        # Filter in Python (small N) — escalated always shown; pending shown only
        # if within the urgency cutoff. Avoids a complex OR query.
        out = []
        for r in rows:
            if r.status == ReturnStatus.ESCALATED:
                priority = 'escalated'
            elif r.seller_response_deadline_at and r.seller_response_deadline_at <= cutoff:
                priority = 'sla_warning'
            else:
                continue
            out.append({
                'id': r.id, 'order_id': str(r.order_id),
                'buyer_email': r.buyer.email if r.buyer_id else None,
                'reason': r.reason,
                'description': (r.description or '')[:200],
                'status': r.status,
                'priority': priority,
                'seller_deadline_at': r.seller_response_deadline_at,
                'created_at': r.created_at,
                'age_hours': round((now - r.created_at).total_seconds() / 3600, 1),
            })
        return out

    def _ledger_drift(self):
        try:
            from apps.ledger.models import LedgerEntry
            from collections import defaultdict
        except Exception:
            return []
        per_currency = defaultdict(lambda: {'d': 0, 'c': 0})
        rows = (
            LedgerEntry.objects
            .values('account__currency')
            .annotate(d=Sum('debit_cents'), c=Sum('credit_cents'))
        )
        drift = []
        for row in rows:
            cur = row['account__currency'] or 'AOA'
            d, c = row['d'] or 0, row['c'] or 0
            diff = c - d
            if diff != 0:
                drift.append({
                    'currency': cur,
                    'imbalance_cents': diff,
                    'imbalance_human': f'{diff/100:+.2f}',
                    'credits': c, 'debits': d,
                })
        return drift

    def _recent_alerts(self):
        try:
            from apps.outbox.models import OutboxEvent
        except Exception:
            return []
        rows = (
            OutboxEvent.objects
            .filter(topic='ops.alert')
            .order_by('-created_at')[:10]
        )
        return [{
            'id': r.id,
            'metric': r.payload.get('metric'),
            'severity': r.payload.get('severity'),
            'message': r.payload.get('message', ''),
            'details': r.payload.get('details', {}),
            'created_at': r.created_at,
            'status': r.status,
        } for r in rows]


class OpsQueueActionView(APIView):
    """POST /api/v1/admin-api/ops-queue/<kind>/<id>/action/

    Operator actions on a queue item. Supported kinds:
      dead_event    body {action: "requeue"|"discard"}
      fraud_hold    body {action: "approve"|"reject"}
    """
    permission_classes = [IsAdminUser]

    @audit_admin_action(_ops_queue_action_name, target_kwarg='item_id')
    def post(self, request, kind, item_id):
        action = (request.data.get('action') or '').strip()
        if kind == 'dead_event':
            return self._dead_event(item_id, action)
        if kind == 'fraud_hold':
            return self._fraud_hold(item_id, action, request)
        return Response({'error': 'unknown_kind'}, status=400)

    def _dead_event(self, item_id, action):
        from apps.outbox.models import OutboxEvent, EventStatus
        ev = OutboxEvent.objects.filter(pk=item_id).first()
        if not ev:
            return Response({'error': 'not_found'}, status=404)
        if action == 'requeue':
            ev.status = EventStatus.PENDING
            ev.attempts = 0
            ev.last_error = ''
            ev.next_attempt_at = timezone.now()
            ev.save(update_fields=['status', 'attempts', 'last_error', 'next_attempt_at', 'updated_at'])
            return Response({'detail': f'Event {ev.id} requeued.'})
        if action == 'discard':
            ev.status = EventStatus.DISPATCHED
            ev.dispatched_at = timezone.now()
            ev.save(update_fields=['status', 'dispatched_at', 'updated_at'])
            return Response({'detail': f'Event {ev.id} discarded.'})
        return Response({'error': 'invalid_action'}, status=400)

    def _fraud_hold(self, item_id, action, request):
        try:
            from apps.risk.models import RiskAssessment, RiskAction
        except Exception:
            return Response({'error': 'risk_unavailable'}, status=500)
        ra = RiskAssessment.objects.filter(pk=item_id).first()
        if not ra:
            return Response({'error': 'not_found'}, status=404)
        if action == 'approve':
            ra.action = RiskAction.ALLOW
            ra.reasons = (ra.reasons or []) + [{
                'rule': 'manual_override', 'delta': -ra.score,
                'reason': f'Approved by operator {request.user.email}',
            }]
            ra.save(update_fields=['action', 'reasons'])
            return Response({'detail': f'Risk assessment {ra.id} approved.'})
        if action == 'reject':
            ra.action = RiskAction.BLOCK
            ra.reasons = (ra.reasons or []) + [{
                'rule': 'manual_override', 'delta': 100 - ra.score,
                'reason': f'Blocked by operator {request.user.email}',
            }]
            ra.save(update_fields=['action', 'reasons'])
            return Response({'detail': f'Risk assessment {ra.id} blocked.'})
        return Response({'error': 'invalid_action'}, status=400)
