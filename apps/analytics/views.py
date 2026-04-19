from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from django.db.models import Count, Sum, Avg
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from django.utils import timezone
from datetime import timedelta
from .models import FunnelEvent, SellerPerformance, GeoSalesData
from apps.users.permissions import IsAdminOrSuperuser, IsSellerOrSuperuser, IsNotSuspended

class TrackFunnelEventView(APIView):
    permission_classes=[permissions.AllowAny]
    def post(self,request):
        event=request.data.get('event')
        product_id=request.data.get('product_id')
        session_id=request.data.get('session_id','')
        if event not in('view','add_cart','checkout','purchase'): return Response({"detail":"Invalid event."},status=400)
        FunnelEvent.objects.create(
            user=request.user if request.user.is_authenticated else None,
            session_id=session_id, event=event,
            product_id=product_id,
        )
        return Response({"detail":"Tracked."})

class FunnelAnalyticsView(APIView):
    permission_classes=[IsAdminOrSuperuser]
    def get(self,request):
        period_days=int(request.query_params.get('days',30))
        since=timezone.now()-timedelta(days=period_days)
        funnel={}
        for event in('view','add_cart','checkout','purchase'):
            funnel[event]=FunnelEvent.objects.filter(event=event,created_at__gte=since).count()
        conversion=round(funnel['purchase']/funnel['view']*100,2) if funnel['view']>0 else 0
        return Response({'funnel':funnel,'conversion_rate':f"{conversion}%",'period_days':period_days})

class SellerPerformanceView(APIView):
    permission_classes=[permissions.IsAuthenticated,IsSellerOrSuperuser,IsNotSuspended]
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
    permission_classes=[IsAdminOrSuperuser]
    def get(self,request):
        data=GeoSalesData.objects.values('city','province').annotate(
            total_orders=Sum('order_count'),total_revenue=Sum('total_revenue')
        ).order_by('-total_revenue')[:20]
        return Response(list(data))

class AdminRealTimeView(APIView):
    permission_classes=[IsAdminOrSuperuser]
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
