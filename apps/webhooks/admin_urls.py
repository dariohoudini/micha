"""Admin DLQ URL routing for outbound webhooks."""
from django.urls import path
from .admin_views import (
    DeadDeliveriesView, WebhookStatsView,
    RequeueDeliveryView, DisableWebhookView,
)


urlpatterns = [
    path('dead/', DeadDeliveriesView.as_view(), name='ob-wh-dead'),
    path('stats/', WebhookStatsView.as_view(), name='ob-wh-stats'),
    path('<int:delivery_id>/requeue/', RequeueDeliveryView.as_view(),
         name='ob-wh-requeue'),
    path('<int:hook_id>/disable-webhook/', DisableWebhookView.as_view(),
         name='ob-wh-disable'),
]
