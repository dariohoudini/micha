from django.urls import path
from .views import (
    NotificationListView, UnreadCountView, MarkReadView, MarkAllReadView,
    UnsubscribeView, SESWebhookView,
)


urlpatterns = [
    path("", NotificationListView.as_view(), name="list"),
    path("unread-count/", UnreadCountView.as_view(), name="unread-count"),
    path("mark-all-read/", MarkAllReadView.as_view(), name="mark-all-read"),
    path("<int:pk>/read/", MarkReadView.as_view(), name="mark-read"),
    path("read-all/", MarkAllReadView.as_view(), name="notifications-read-all"),
    # RFC 8058 one-click unsubscribe. NO auth — HMAC sig is the auth.
    path("unsubscribe/", UnsubscribeView.as_view(), name="unsubscribe"),
    # SES → SNS bounce + complaint webhook. NO auth — SNS RSA signature
    # is the auth (or IP allowlist fallback when cryptography unavailable).
    path("ses-webhook/", SESWebhookView.as_view(), name="ses-webhook"),
]
