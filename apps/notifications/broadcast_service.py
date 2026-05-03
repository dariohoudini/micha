"""
apps/notifications/broadcast_service.py + views.py

Admin broadcast notification system.
Admin can send push/in-app notifications to segmented user groups.

Segments: all_buyers, all_sellers, province, category_interest, inactive_users
"""
from django.db import models
from django.conf import settings
import uuid


class BroadcastNotification(models.Model):
    """Records every broadcast sent for audit and analytics."""
    SEGMENT_TYPES = [
        ('all_buyers',        'Todos os compradores'),
        ('all_sellers',       'Todos os vendedores'),
        ('province',          'Província específica'),
        ('category_interest', 'Interesse de categoria'),
        ('inactive_30',       'Inactivos há 30+ dias'),
        ('new_users',         'Novos utilizadores (últimos 7 dias)'),
        ('custom',            'Lista personalizada'),
    ]
    CHANNEL_TYPES = [
        ('push',  'Push notification'),
        ('inapp', 'In-app notification'),
        ('both',  'Push + In-app'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True
    )
    title = models.CharField(max_length=100)
    body = models.TextField()
    segment = models.CharField(max_length=30, choices=SEGMENT_TYPES)
    segment_value = models.CharField(
        max_length=100, blank=True,
        help_text="Province name, category name, etc."
    )
    channel = models.CharField(max_length=10, choices=CHANNEL_TYPES, default='both')
    deep_link = models.CharField(
        max_length=200, blank=True,
        help_text="App screen to open e.g. /explore?category=Moda"
    )
    scheduled_for = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    recipient_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=[('draft','Rascunho'),('scheduled','Agendado'),('sent','Enviado'),('failed','Falhou')],
        default='draft'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'broadcast_notifications'
        ordering = ['-created_at']


# ── Broadcast Service ─────────────────────────────────────────────────────────

class BroadcastService:
    """Targets and sends broadcast notifications to user segments."""

    @classmethod
    def get_target_users(cls, segment: str, segment_value: str = '') -> list:
        from django.contrib.auth import get_user_model
        from django.utils import timezone
        from datetime import timedelta

        User = get_user_model()
        qs = User.objects.filter(is_active=True)

        if segment == 'all_buyers':
            qs = qs.filter(is_seller=False, is_staff=False)
        elif segment == 'all_sellers':
            qs = qs.filter(is_seller=True)
        elif segment == 'province':
            qs = qs.filter(province__iexact=segment_value)
        elif segment == 'category_interest':
            try:
                from apps.ai_engine.models import UserTasteProfile
                profile_ids = UserTasteProfile.objects.filter(
                    preferred_categories__contains=segment_value
                ).values_list('user_id', flat=True)
                qs = qs.filter(id__in=profile_ids)
            except Exception:
                pass
        elif segment == 'inactive_30':
            cutoff = timezone.now() - timedelta(days=30)
            qs = qs.filter(last_login__lt=cutoff)
        elif segment == 'new_users':
            cutoff = timezone.now() - timedelta(days=7)
            qs = qs.filter(date_joined__gte=cutoff)

        return list(qs.values_list('id', flat=True))

    @classmethod
    def send_broadcast(cls, broadcast_id: str):
        """Called by Celery task. Sends to all target users."""
        from .broadcast_tasks import send_broadcast_task
        send_broadcast_task.delay(broadcast_id)


# ── Broadcast Views ───────────────────────────────────────────────────────────

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser


class BroadcastListView(APIView):
    """
    GET  /api/v1/notifications/broadcasts/  — List broadcasts
    POST /api/v1/notifications/broadcasts/  — Create broadcast
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        broadcasts = BroadcastNotification.objects.all()[:50]
        data = [{
            'id': str(b.id),
            'title': b.title,
            'segment': b.segment,
            'segment_label': dict(BroadcastNotification.SEGMENT_TYPES).get(b.segment),
            'segment_value': b.segment_value,
            'channel': b.channel,
            'status': b.status,
            'recipient_count': b.recipient_count,
            'sent_at': b.sent_at,
            'scheduled_for': b.scheduled_for,
            'created_at': b.created_at,
        } for b in broadcasts]
        return Response({'broadcasts': data})

    def post(self, request):
        title = request.data.get('title', '').strip()
        body = request.data.get('body', '').strip()
        segment = request.data.get('segment', '')

        if not title or not body or not segment:
            return Response({'error': 'title, body e segment são obrigatórios.'}, status=400)
        if segment not in dict(BroadcastNotification.SEGMENT_TYPES):
            return Response({'error': 'Segmento inválido.'}, status=400)

        # Preview recipient count
        segment_value = request.data.get('segment_value', '')
        target_users = BroadcastService.get_target_users(segment, segment_value)

        broadcast = BroadcastNotification.objects.create(
            created_by=request.user,
            title=title,
            body=body,
            segment=segment,
            segment_value=segment_value,
            channel=request.data.get('channel', 'both'),
            deep_link=request.data.get('deep_link', ''),
            scheduled_for=request.data.get('scheduled_for'),
            recipient_count=len(target_users),
            status='draft',
        )

        return Response({
            'id': str(broadcast.id),
            'estimated_recipients': len(target_users),
            'message': f'Broadcast criado. Irá alcançar ~{len(target_users)} utilizadores.',
        }, status=201)


class BroadcastSendView(APIView):
    """POST /api/v1/notifications/broadcasts/<id>/send/ — Send immediately"""
    permission_classes = [IsAdminUser]

    def post(self, request, broadcast_id):
        try:
            broadcast = BroadcastNotification.objects.get(id=broadcast_id)
        except BroadcastNotification.DoesNotExist:
            return Response({'error': 'Broadcast não encontrado.'}, status=404)

        if broadcast.status == 'sent':
            return Response({'error': 'Este broadcast já foi enviado.'}, status=400)

        # Queue the send task
        from .broadcast_tasks import send_broadcast_task
        send_broadcast_task.delay(str(broadcast.id))

        broadcast.status = 'scheduled'
        broadcast.save()

        return Response({
            'status': 'sending',
            'message': f'A enviar para {broadcast.recipient_count} utilizadores...',
        })
