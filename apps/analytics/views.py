from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from django.db.models import Sum
from django.utils import timezone
from datetime import timedelta
from .models import FunnelEvent, SellerPerformance, GeoSalesData, UserEvent
from apps.users.permissions import IsAdminOrSuperuser, IsSellerOrSuperuser, IsNotSuspended

class TrackFunnelEventView(APIView):
    permission_classes = [permissions.AllowAny]
    def post(self,request):
        event=request.data.get('event')
        product_id=request.data.get('product_id')
        session_id=request.data.get('session_id','')
        if event not in('view','add_cart','checkout','purchase'): return Response({'error': 'Invalid event.'}, status=400)
        FunnelEvent.objects.create(
            user=request.user if request.user.is_authenticated else None,
            session_id=session_id, event=event,
            product_id=product_id,
        )
        return Response({"detail":"Tracked."})


def _client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR') or ''
    return (xff.split(',')[0].strip() or request.META.get('REMOTE_ADDR') or '').strip() or None


class TrackUserEventView(APIView):
    """POST /api/v1/analytics/events/ — batched user-touch ingest.

    Accepts either a single event or a batched list under ``events``.
    Each event must have ``event`` (name) and may include
    ``properties`` (dict), ``session_id``, ``ts`` (client timestamp).
    Authentication is optional so anonymous session events still
    persist; the JWT identifies the user when present.
    """
    permission_classes = [permissions.AllowAny]
    throttle_scope = 'event_track'

    def post(self, request):
        payload = request.data
        events = payload if isinstance(payload, list) else payload.get('events')
        if not events:
            events = [payload]
        if not isinstance(events, list):
            return Response({'error': 'events must be a list'}, status=400)
        ip = _client_ip(request)
        ua = (request.META.get('HTTP_USER_AGENT') or '')[:255]
        ref = (request.META.get('HTTP_REFERER') or '')[:255]
        user = request.user if request.user.is_authenticated else None
        rows = []
        # Hard-cap per call to avoid abuse.
        for raw in events[:200]:
            if not isinstance(raw, dict):
                continue
            name = (raw.get('event') or raw.get('name') or '').strip()[:80]
            if not name:
                continue
            rows.append(UserEvent(
                user=user,
                session_id=(raw.get('session_id') or '')[:80],
                event=name,
                properties=UserEvent.scrub_props(raw.get('properties') or {}),
                path=(raw.get('path') or '')[:255],
                ip=ip,
                user_agent=ua,
                referrer=ref,
            ))
        if rows:
            UserEvent.objects.bulk_create(rows, batch_size=200)
        return Response({'accepted': len(rows)})

class FunnelAnalyticsView(APIView):
    permission_classes = [IsAdminOrSuperuser]
    def get(self,request):
        period_days=int(request.query_params.get('days',30))
        since=timezone.now()-timedelta(days=period_days)
        funnel={}
        for event in('view','add_cart','checkout','purchase'):
            funnel[event]=FunnelEvent.objects.filter(event=event,created_at__gte=since).count()
        conversion=round(funnel['purchase']/funnel['view']*100,2) if funnel['view']>0 else 0
        return Response({'funnel':funnel,'conversion_rate':f"{conversion}%",'period_days':period_days})

class SellerPerformanceView(APIView):
    permission_classes = [permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended]
    def get(self,request):
        perf,_=SellerPerformance.objects.get_or_create(seller=request.user)
        return Response({
            'response_rate':f"{perf.response_rate:.1%}",
            'avg_response_time_hours':round(perf.avg_response_time_hours,1),
            'on_time_delivery_rate':f"{perf.on_time_delivery_rate:.1%}",
            'completion_rate':f"{perf.completion_rate:.1%}",
            'return_rate':f"{perf.return_rate:.1%}",
            'overall_score':round(perf.overall_score,2),
            'tier':perf.tier,
            'last_calculated':perf.last_calculated,
        })

class AdminGeoAnalyticsView(APIView):
    permission_classes = [IsAdminOrSuperuser]
    def get(self,request):
        data=GeoSalesData.objects.values('city','province').annotate(
            total_orders=Sum('order_count'),total_revenue=Sum('total_revenue')
        ).order_by('-total_revenue')[:20]
        return Response(list(data))

class AdminRealTimeView(APIView):
    permission_classes = [IsAdminOrSuperuser]
    def get(self,request):
        from apps.users.models import User
        from apps.orders.models import Order
        now=timezone.now()
        today=now.date()
        return Response({
            'live_users_today':User.objects.filter(date_joined__date=today).count(),
            'orders_today':Order.objects.filter(created_at__date=today).count(),
            'revenue_today':str(Order.objects.filter(created_at__date=today,payment_status='paid').aggregate(t=Sum('total'))['t'] or 0),
            'pending_orders':Order.objects.filter(status='pending').count(),
        })


# ─── AliExpress 2025 CH 1.4 + CH 26.3 — App config / maintenance ──

from django.conf import settings as _dj_settings


class AppConfigView(APIView):
    """GET /api/v1/config/app/ — public.

    Returns the minimum-supported app version (drives the §26.3
    "Please update" blocking modal) and maintenance-mode banner
    state. Both are read from Django settings so ops can flip them
    at deploy time without a code release. Defaults are permissive
    so a missing setting NEVER bricks the app.
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return Response({
            'min_app_version': getattr(_dj_settings, 'MIN_APP_VERSION', '0.0.0'),
            'latest_app_version': getattr(_dj_settings, 'LATEST_APP_VERSION', '1.0.0'),
            'maintenance_mode': getattr(_dj_settings, 'MAINTENANCE_MODE', False),
            'maintenance_message': getattr(_dj_settings, 'MAINTENANCE_MESSAGE', ''),
            'maintenance_until': getattr(_dj_settings, 'MAINTENANCE_UNTIL', None),
            'feature_flags': {
                # Surface a small set of boolean feature flags. The
                # full flags system lives in apps.flags; this is a
                # cached read-side projection for client-side gating.
                'live_streaming': getattr(_dj_settings, 'FEATURE_LIVE_STREAMING', False),
                'coins_enabled': getattr(_dj_settings, 'FEATURE_COINS', True),
                'choice_programme': getattr(_dj_settings, 'FEATURE_CHOICE', True),
            },
        })
