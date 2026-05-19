"""Admin URL routing. Mounted at /api/v1/admin/inbound-webhooks/."""
from django.urls import path
from .admin_views import (
    EventListView, EventDetailView, RecentFailuresView,
    StatsView, ReplayView,
)


urlpatterns = [
    path('events/', EventListView.as_view(), name='wh-events'),
    path('events/<int:event_id>/', EventDetailView.as_view(),
         name='wh-event-detail'),
    path('events/<int:event_id>/replay/', ReplayView.as_view(),
         name='wh-event-replay'),
    path('failures/', RecentFailuresView.as_view(), name='wh-failures'),
    path('stats/', StatsView.as_view(), name='wh-stats'),
]
