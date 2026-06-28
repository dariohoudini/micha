from django.urls import path
from .views import *
from .seller_dashboard import SellerDashboardView
from .attribution import AttributionTouchView, AttributionReportView
from .cohorts import CohortRetentionView

urlpatterns = [
    path('track/', TrackFunnelEventView.as_view(), name='track'),
    # User Process Flow §20.8 — every-touch telemetry sink.
    path('events/', TrackUserEventView.as_view(), name='track-events'),
    # AliExpress 2025 CH 1.4 + CH 26.3 — public app config (no auth)
    path('config/', AppConfigView.as_view(), name='app-config'),
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
    # R7: cohort retention analysis (admin only).
    path('cohorts/', CohortRetentionView.as_view(), name='cohorts'),
    path('admin/geo/', AdminGeoAnalyticsView.as_view(), name='geo-analytics'),
    path('admin/realtime/', AdminRealTimeView.as_view(), name='realtime'),
]
