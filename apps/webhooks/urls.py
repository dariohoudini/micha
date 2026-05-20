"""Seller self-service webhook URL routing."""
from django.urls import path
from .views import (
    WebhookListCreateView, WebhookDetailView, WebhookRotateSecretView,
    WebhookTestView, WebhookDeliveriesView,
)


urlpatterns = [
    path('', WebhookListCreateView.as_view(), name='webhooks-list'),
    path('<int:hook_id>/', WebhookDetailView.as_view(), name='webhooks-detail'),
    path('<int:hook_id>/rotate/', WebhookRotateSecretView.as_view(),
         name='webhooks-rotate'),
    path('<int:hook_id>/test/', WebhookTestView.as_view(),
         name='webhooks-test'),
    path('<int:hook_id>/deliveries/', WebhookDeliveriesView.as_view(),
         name='webhooks-deliveries'),
]
