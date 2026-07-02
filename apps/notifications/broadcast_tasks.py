"""
apps/notifications/broadcast_tasks.py
"""
from celery import shared_task
import logging
logger = logging.getLogger(__name__)


@shared_task(name='notifications.send_broadcast_task', queue='ai_medium')
def send_broadcast_task(broadcast_id: str):
    """Sends a broadcast notification to all target users."""
    from .broadcast_service import BroadcastNotification, BroadcastService
    from apps.ai_engine.tasks import send_push_notification
    from django.utils import timezone

    try:
        broadcast = BroadcastNotification.objects.get(id=broadcast_id)
    except BroadcastNotification.DoesNotExist:
        return

    target_users = BroadcastService.get_target_users(
        broadcast.segment, broadcast.segment_value
    )

    # In-app channel: the actual Notification rows the app's sino (bell)
    # lists. This was MISSING — 'inapp'/'both' broadcasts marked
    # themselves sent without any user ever seeing anything. Idempotent
    # via the broadcast_id in data: re-running skips users who already
    # got this broadcast.
    inapp_rows = 0
    if broadcast.channel in ('inapp', 'both'):
        from .models import Notification
        already = set(
            Notification.objects.filter(
                data__broadcast_id=str(broadcast.id)
            ).values_list('user_id', flat=True)
        )
        to_create = [
            Notification(
                user_id=user_id, type='system',
                title=broadcast.title, message=broadcast.body,
                data={'type': 'broadcast', 'broadcast_id': str(broadcast.id),
                      'deep_link': broadcast.deep_link},
            )
            for user_id in target_users if user_id not in already
        ]
        inapp_rows = len(Notification.objects.bulk_create(to_create, batch_size=500))

    sent = 0
    for user_id in target_users:
        if broadcast.channel in ('push', 'both'):
            # Push enqueue failure (e.g. no broker in dev) must not zero
            # the recipient count — the in-app rows above were already
            # delivered to these same users.
            try:
                send_push_notification.delay(
                    user_id=str(user_id),
                    title=broadcast.title,
                    body=broadcast.body,
                    data={
                        'type': 'broadcast',
                        'broadcast_id': str(broadcast.id),
                        'deep_link': broadcast.deep_link,
                    }
                )
            except Exception as e:
                logger.error(f"Broadcast push enqueue failed for user {user_id}: {e}")
        sent += 1

    broadcast.status = 'sent'
    broadcast.sent_at = timezone.now()
    broadcast.recipient_count = sent
    broadcast.save()

    logger.info(f"Broadcast {broadcast_id} sent to {sent} users "
                f"({inapp_rows} in-app rows)")


# ─────────────────────────────────────────────────────────────────────────────
"""
apps/users/social_auth_views.py

Social login — Google + Facebook OAuth.
Credentials plugged in via settings when developer accounts are ready.
"""
# ─────────────────────────────────────────────────────────────────────────────

from rest_framework.views import APIView
from rest_framework.response import Response
import requests
import logging

logger = logging.getLogger(__name__)


class GoogleLoginView(APIView):
    """
    POST /api/v1/auth/social/google/
    Receives Google ID token from frontend, verifies with Google,
    creates/logs in user, returns MICHA JWT tokens.

    Body: { "id_token": "Google ID token from frontend" }

    Frontend setup:
    - Web: @react-oauth/google
    - Mobile: @react-native-google-signin/google-signin
    """

    def post(self, request):
        from django.conf import settings
        id_token = request.data.get('id_token')
        if not id_token:
            return Response({'error': 'id_token obrigatório.'}, status=400)

        # Verify token with Google
        try:
            google_response = requests.get(
                f'https://oauth2.googleapis.com/tokeninfo?id_token={id_token}',
                timeout=10
            )
            if google_response.status_code != 200:
                return Response({'error': 'Token Google inválido.'}, status=401)

            google_data = google_response.json()

            # Verify audience (your Google Client ID)
            google_client_id = getattr(settings, 'GOOGLE_CLIENT_ID', None)
            if google_client_id and google_data.get('aud') != google_client_id:
                return Response({'error': 'Token não autorizado para esta aplicação.'}, status=401)

            email = google_data.get('email')
            name = google_data.get('name', '')
            google_id = google_data.get('sub')

            if not email:
                return Response({'error': 'Email não disponível na conta Google.'}, status=400)

        except requests.RequestException as e:
            logger.error(f"Google token verification failed: {e}")
            return Response({'error': 'Erro ao verificar com Google. Tente novamente.'}, status=503)

        # Get or create user
        user, tokens = self._get_or_create_user(email, name, google_id, 'google')
        return Response(tokens)

    def _get_or_create_user(self, email, name, social_id, provider):
        from django.contrib.auth import get_user_model
        from rest_framework_simplejwt.tokens import RefreshToken

        User = get_user_model()
        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                'username': email.split('@')[0],
                'is_email_verified': True,
                f'{provider}_id': social_id,
            }
        )

        if not created:
            # Update social ID if not set
            if not getattr(user, f'{provider}_id', None):
                setattr(user, f'{provider}_id', social_id)
                user.save(update_fields=[f'{provider}_id'])

        refresh = RefreshToken.for_user(user)
        return user, {
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': str(user.id),
                'email': user.email,
                'is_seller': getattr(user, 'is_seller', False),
                'is_new': created,
            }
        }


class FacebookLoginView(APIView):
    """
    POST /api/v1/auth/social/facebook/
    Receives Facebook access token, verifies, creates/logs in user.

    Body: { "access_token": "Facebook access token from frontend" }

    Frontend setup:
    - Web: react-facebook-login
    - Mobile: react-native-fbsdk-next
    """

    def post(self, request):
        from django.conf import settings
        access_token = request.data.get('access_token')
        if not access_token:
            return Response({'error': 'access_token obrigatório.'}, status=400)

        # Verify token with Facebook Graph API
        try:
            fb_app_id = getattr(settings, 'FACEBOOK_APP_ID', None)
            fb_app_secret = getattr(settings, 'FACEBOOK_APP_SECRET', None)

            # Verify token
            if fb_app_id and fb_app_secret:
                app_token_response = requests.get(
                    f'https://graph.facebook.com/oauth/access_token?client_id={fb_app_id}&client_secret={fb_app_secret}&grant_type=client_credentials',
                    timeout=10
                )
                app_token = app_token_response.json().get('access_token')
                debug_response = requests.get(
                    f'https://graph.facebook.com/debug_token?input_token={access_token}&access_token={app_token}',
                    timeout=10
                )
                debug_data = debug_response.json().get('data', {})
                if not debug_data.get('is_valid'):
                    return Response({'error': 'Token Facebook inválido.'}, status=401)

            # Get user info
            user_response = requests.get(
                f'https://graph.facebook.com/me?fields=id,name,email&access_token={access_token}',
                timeout=10
            )
            if user_response.status_code != 200:
                return Response({'error': 'Erro ao obter dados do Facebook.'}, status=401)

            fb_data = user_response.json()
            email = fb_data.get('email')
            name = fb_data.get('name', '')
            facebook_id = fb_data.get('id')

            if not email:
                return Response({
                    'error': 'Email não disponível. Autorize o acesso ao email nas permissões do Facebook.'
                }, status=400)

        except requests.RequestException as e:
            logger.error(f"Facebook verification failed: {e}")
            return Response({'error': 'Erro ao verificar com Facebook. Tente novamente.'}, status=503)

        user, tokens = GoogleLoginView()._get_or_create_user(email, name, facebook_id, 'facebook')
        return Response(tokens)
