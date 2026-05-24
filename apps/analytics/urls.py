from django.urls import path
from .views import *
from .seller_dashboard import SellerDashboardView
from .attribution import AttributionTouchView, AttributionReportView

urlpatterns = [
    path('track/', TrackFunnelEventView.as_view(), name='track'),
    path('funnel/', FunnelAnalyticsView.as_view(), name='funnel'),
    path('seller/performance/', SellerPerformanceView.as_view(),
         name='seller-performance'),
    # R7: seller analytics dashboard — one endpoint covering revenue
    # time series, totals, funnel, top products, geo, repeat-rate.
    path('seller/dashboard/', SellerDashboardView.as_view(),
         name='seller-dashboard'),
    # R7: UTM attribution tracking.
    path('touch/', AttributionTouchView.as_view(), name='attribution-touch'),
    path('attribution/', AttributionReportView.as_view(),
         name='attribution-report'),
    path('admin/geo/', AdminGeoAnalyticsView.as_view(), name='geo-analytics'),
    path('admin/realtime/', AdminRealTimeView.as_view(), name='realtime'),
]
