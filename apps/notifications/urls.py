from django.urls import path
from .views import (
    NotificationListView, UnreadCountView, MarkReadView, MarkAllReadView,
    PushTokenRegisterView, PushTokenUnregisterView,
    UnsubscribeView, SESWebhookView,
)
from .whatsapp_webhook import whatsapp_webhook
from .broadcast_service import BroadcastListView, BroadcastSendView


urlpatterns = [
    # Admin platform-wide broadcast (staff-only via IsAdminUser). The views
    # existed but were never wired to a URL, so the admin console had no way
    # to send a message to all users.
    path("admin/broadcasts/", BroadcastListView.as_view(), name="broadcast-list"),
    path("admin/broadcasts/<uuid:broadcast_id>/send/",
         BroadcastSendView.as_view(), name="broadcast-send"),

    path("", NotificationListView.as_view(), name="list"),
    path("unread-count/", UnreadCountView.as_view(), name="unread-count"),
    path("mark-all-read/", MarkAllReadView.as_view(), name="mark-all-read"),
    path("<int:pk>/read/", MarkReadView.as_view(), name="mark-read"),
    path("read-all/", MarkAllReadView.as_view(), name="notifications-read-all"),

    # R5: push token registration. Frontend's usePushNotifications hook
    # POSTs the FCM/APNs token here on app start. Without these endpoints
    # the frontend silently 404s and no pushes ever go out.
    path("push/register/", PushTokenRegisterView.as_view(),
         name="push-register"),
    path("push/unregister/", PushTokenUnregisterView.as_view(),
         name="push-unregister"),

    # RFC 8058 one-click unsubscribe. NO auth — HMAC sig is the auth.
    path("unsubscribe/", UnsubscribeView.as_view(), name="unsubscribe"),
    # SES → SNS bounce + complaint webhook. NO auth — SNS RSA signature
    # is the auth (or IP allowlist fallback when cryptography unavailable).
    path("ses-webhook/", SESWebhookView.as_view(), name="ses-webhook"),

    # R5: WhatsApp Business webhook. GET=Meta subscription verification,
    # POST=event delivery (HMAC-signed via WHATSAPP_APP_SECRET).
    path("whatsapp/webhook/", whatsapp_webhook, name="whatsapp-webhook"),
]
