"""DLQ admin URL routing for the outbox.

Mounted at /api/v1/admin/outbox/. All endpoints are admin-only via
IsAdminOrSuperuser in each view.
"""
from django.urls import path
from .dlq_views import (
    DLQDeadListView, DLQStaleRetryingView, DLQStatsView,
    DLQRequeueView, DLQRequeueBulkView, DLQDiscardView,
)


urlpatterns = [
    path('dead/',           DLQDeadListView.as_view(),    name='outbox-dlq-dead'),
    path('stale-retrying/', DLQStaleRetryingView.as_view(), name='outbox-dlq-stale'),
    path('stats/',          DLQStatsView.as_view(),       name='outbox-dlq-stats'),
    path('<int:event_id>/requeue/',
         DLQRequeueView.as_view(), name='outbox-dlq-requeue'),
    path('requeue-bulk/',   DLQRequeueBulkView.as_view(), name='outbox-dlq-requeue-bulk'),
    path('<int:event_id>/discard/',
         DLQDiscardView.as_view(), name='outbox-dlq-discard'),
]
