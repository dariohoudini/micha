"""
Central notification utilities.
Every part of the app that needs to notify a user calls send_notification() here.
This keeps notification logic in one place — easy to extend.
"""
from celery import shared_task


def send_notification(user, type, title, message, data=None):
    """
    Create an in-app notification and optionally send FCM push.
    type choices: order, payment, message, review, promotion, system
    """
    try:
        from apps.notifications.models import Notification
        Notification.objects.create(
            user=user,
            type=type,
            title=title,
            message=message,
            data=data or {},
        )
    except Exception as e:
        import logging
        logging.getLogger('micha').error(f"send_notification failed: {e}")


@shared_task(name='notifications.send_push')
def send_push(token, title, body, data=None):
    """
    Fire-and-forget FCM push notification.
    Requires: pip install firebase-admin
    Requires: FIREBASE_CREDENTIALS_PATH in settings pointing to service account JSON.
    """
    if not token:
        return "No token provided"

    try:
        import firebase_admin
        from firebase_admin import messaging, credentials
        from django.conf import settings

        cred_path = getattr(settings, 'FIREBASE_CREDENTIALS_PATH', '')
        if not cred_path:
            return "FIREBASE_CREDENTIALS_PATH not configured in settings"

        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)

        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={k: str(v) for k, v in (data or {}).items()},
            token=token,
        )
        response = messaging.send(message)
        return f"FCM push sent: {response}"

    except Exception as e:
        import logging
        logging.getLogger('micha').error(f"FCM push failed for token {token[:20]}...: {e}")
        return f"Push failed: {str(e)}"
