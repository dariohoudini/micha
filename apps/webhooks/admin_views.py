"""apps/webhooks/admin_views.py — admin DLQ for outbound webhook deliveries.

Mounted at /api/v1/admin/outbound-webhooks/.

  GET    /dead/?limit=                list DEAD deliveries
  GET    /stats/                      counts by status
  POST   /<id>/requeue/               retry a dead delivery
  POST   /<id>/disable-webhook/       disable the seller's webhook
                                       (admin override of auto-disable)
"""
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.users.permissions import IsAdminOrSuperuser

from .models import SellerWebhook, WebhookDelivery, DeliveryStatus


class DeadDeliveriesView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        try:
            limit = int(request.query_params.get('limit', 50))
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(limit, 500))
        rows = (
            WebhookDelivery.objects.filter(status=DeliveryStatus.DEAD)
            .select_related('webhook__seller')
            .order_by('-updated_at')[:limit]
        )
        return Response({
            'count': WebhookDelivery.objects.filter(
                status=DeliveryStatus.DEAD,
            ).count(),
            'results': [
                {
                    'id': d.id,
                    'webhook_id': d.webhook_id,
                    'seller_email': d.webhook.seller.email if d.webhook else '',
                    'topic': d.topic,
                    'attempts': d.attempts,
                    'response_status': d.response_status,
                    'last_error': (d.last_error or '')[:300],
                    'created_at': d.created_at,
                    'updated_at': d.updated_at,
                }
                for d in rows
            ],
        })


class WebhookStatsView(APIView):
    permission_classes = [IsAdminOrSuperuser]

    def get(self, request):
        from django.db.models import Count
        by_status = list(
            WebhookDelivery.objects.values('status')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        return Response({
            'by_status': by_status,
            'active_webhooks': SellerWebhook.objects.filter(is_active=True).count(),
            'inactive_webhooks': SellerWebhook.objects.filter(is_active=False).count(),
        })


class RequeueDeliveryView(APIView):
    """POST /api/v1/admin/outbound-webhooks/<id>/requeue/

    Reset a DEAD delivery to PENDING and re-enqueue. Use after the
    operator has investigated the failure and decided the seller's
    endpoint is back online OR the failure cause was transient.
    """
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, delivery_id):
        from django.utils import timezone
        d = get_object_or_404(WebhookDelivery, pk=delivery_id)
        if d.status == DeliveryStatus.DELIVERED:
            return Response(
                {'error': 'already_delivered',
                 'detail': 'This delivery already succeeded; nothing to retry.'},
                status=400,
            )
        # Reset attempts so the operator gets a fresh retry budget.
        # Re-enable the webhook if it was auto-disabled.
        d.status = DeliveryStatus.PENDING
        d.attempts = 0
        d.next_attempt_at = timezone.now()
        d.last_error = ''
        d.save(update_fields=[
            'status', 'attempts', 'next_attempt_at', 'last_error', 'updated_at',
        ])
        if d.webhook and not d.webhook.is_active:
            SellerWebhook.objects.filter(pk=d.webhook_id).update(
                is_active=True, consecutive_failures=0,
            )

        try:
            from .tasks import deliver_webhook
            deliver_webhook.delay(d.id)
        except Exception:
            pass

        return Response({
            'detail': 'Delivery requeued.',
            'delivery_id': d.id,
        })


class DisableWebhookView(APIView):
    """POST /api/v1/admin/outbound-webhooks/<id>/disable-webhook/

    Force-disable a SellerWebhook regardless of consecutive_failures.
    For cases where the operator wants to stop deliveries immediately
    (compromised seller endpoint, abuse report, security incident).
    """
    permission_classes = [IsAdminOrSuperuser]

    def post(self, request, hook_id):
        h = get_object_or_404(SellerWebhook, pk=hook_id)
        reason = (request.data.get('reason') or '').strip()[:200]
        SellerWebhook.objects.filter(pk=h.pk).update(is_active=False)
        return Response({
            'detail': 'Webhook disabled.',
            'webhook_id': h.id,
            'reason': reason,
        })
