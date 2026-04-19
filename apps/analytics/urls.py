from django.urls import path
from .views import *
urlpatterns=[
    path('track/',TrackFunnelEventView.as_view(),name='track'),
    path('funnel/',FunnelAnalyticsView.as_view(),name='funnel'),
    path('seller/performance/',SellerPerformanceView.as_view(),name='seller-performance'),
    path('admin/geo/',AdminGeoAnalyticsView.as_view(),name='geo-analytics'),
    path('admin/realtime/',AdminRealTimeView.as_view(),name='realtime'),
]
