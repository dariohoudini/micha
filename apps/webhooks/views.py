"""
apps/webhooks/views.py — seller self-service for outbound webhooks.

Sellers register URLs to receive event pushes (order.placed, order.shipped,
return.created, etc.). They manage their subscriptions here:

  GET    /api/v1/webhooks/                  list my webhooks (no secrets)
  POST   /api/v1/webhooks/                  create — RETURNS SECRET ONCE
  GET    /api/v1/webhooks/<id>/             detail
  DELETE /api/v1/webhooks/<id>/             remove
  POST   /api/v1/webhooks/<id>/test/        fire a test delivery now
  POST   /api/v1/webhooks/<id>/rotate/      rotate the signing secret
  GET    /api/v1/webhooks/<id>/deliveries/  recent delivery history
"""
from __future__ import annotations

import logging

from django.shortcuts import get_object_or_404
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsNotSuspended, IsSellerOrSuperuser

from .models import (
    SellerWebhook, WebhookDelivery, DeliveryStatus, ALLOWED_TOPICS,
)
from .url_validator import validate_webhook_url


log = logging.getLogger(__name__)


def _serialize_hook(h, *, include_secret: bool = False) -> dict:
    out = {
        'id': h.id,
        'url': h.url,
        'topics': h.topics,
        'is_active': h.is_active,
        'consecutive_failures': h.consecutive_failures,
        'last_success_at': h.last_success_at,
        'last_failure_at': h.last_failure_at,
        'created_at': h.created_at,
    }
    if include_secret:
        # Plaintext shown ONCE at creation; sellers must capture it then.
        out['secret'] = h.secret
    return out


class WebhookListCreateView(APIView):
    """GET + POST /api/v1/webhooks/"""
    permission_classes = [
        permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended,
    ]

    def get(self, request):
        hooks = SellerWebhook.objects.filter(seller=request.user).order_by('-created_at')
        return Response({
            'allowed_topics': list(ALLOWED_TOPICS),
            'results': [_serialize_hook(h) for h in hooks],
        })

    def post(self, request):
        url = (request.data.get('url') or '').strip()
        topics_raw = request.data.get('topics') or []
        if not isinstance(topics_raw, list):
            return Response(
                {'error': 'validation_error', 'detail': 'topics must be a list'},
                status=400,
            )

        # SSRF defense — refuses private / loopback / link-local IPs +
        # AWS metadata. Resolves DNS at validation time and rejects if
        # any resolved IP is private. See url_validator.py for the
        # full threat model.
        decision = validate_webhook_url(url)
        if not decision.allowed:
            return Response(
                {'error': 'invalid_url', 'detail': decision.reason},
                status=400,
            )

        topics_set = sorted(set(topics_raw) & set(ALLOWED_TOPICS))
        invalid = sorted(set(topics_raw) - set(ALLOWED_TOPICS))
        if invalid:
            return Response(
                {'error': 'invalid_topics',
                 'detail': f'unknown topics: {invalid}',
                 'allowed_topics': list(ALLOWED_TOPICS)},
                status=400,
            )
        if not topics_set:
            return Response(
                {'error': 'validation_error',
                 'detail': 'at least one valid topic required'},
                status=400,
            )

        # Per-seller cap so a runaway integration can't register 1000s.
        if SellerWebhook.objects.filter(seller=request.user).count() >= 25:
            return Response(
                {'error': 'too_many',
                 'detail': 'maximum 25 webhooks per seller'},
                status=400,
            )

        hook = SellerWebhook.objects.create(
            seller=request.user,
            url=url,
            secret=SellerWebhook.gen_secret(),
            topics=topics_set,
            is_active=True,
        )
        return Response(_serialize_hook(hook, include_secret=True), status=201)


class WebhookDetailView(APIView):
    """GET + DELETE /api/v1/webhooks/<id>/"""
    permission_classes = [
        permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended,
    ]

    def get(self, request, hook_id):
        h = get_object_or_404(SellerWebhook, pk=hook_id, seller=request.user)
        return Response(_serialize_hook(h))

    def delete(self, request, hook_id):
        h = get_object_or_404(SellerWebhook, pk=hook_id, seller=request.user)
        h.delete()
        return Response({'detail': 'webhook removed.'}, status=200)


class WebhookRotateSecretView(APIView):
    """POST /api/v1/webhooks/<id>/rotate/

    Rotate the signing secret. Returns the NEW secret once; the old
    one stops working immediately. Use when the seller suspects the
    secret was compromised, or as periodic hygiene.
    """
    permission_classes = [
        permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended,
    ]

    def post(self, request, hook_id):
        h = get_object_or_404(SellerWebhook, pk=hook_id, seller=request.user)
        h.secret = SellerWebhook.gen_secret()
        h.save(update_fields=['secret', 'updated_at'])
        return Response(_serialize_hook(h, include_secret=True))


class WebhookTestView(APIView):
    """POST /api/v1/webhooks/<id>/test/

    Fire a test delivery immediately so the seller can verify their
    integration (signature verification, response handling) without
    waiting for a real event. The test payload is clearly labeled
    ``"test": true`` so the seller's handler can branch on it.
    """
    permission_classes = [
        permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended,
    ]

    def post(self, request, hook_id):
        import uuid as _uuid
        from .tasks import deliver_webhook

        h = get_object_or_404(SellerWebhook, pk=hook_id, seller=request.user)
        if not h.is_active:
            return Response(
                {'error': 'webhook_inactive',
                 'detail': 'Webhook is disabled. Re-enable from the dashboard.'},
                status=400,
            )

        # Pick the first topic the seller subscribed to for the test event.
        topic = (h.topics or ['order.placed'])[0]
        payload = {
            'test': True,
            'topic': topic,
            'message': 'This is a test delivery from MICHA.',
            'webhook_id': h.id,
            'note': 'Your handler should verify the X-Micha-Signature '
                    'header and return 2xx within 8 seconds.',
        }
        delivery = WebhookDelivery.objects.create(
            webhook=h, topic=topic, payload=payload,
            dedupe_key=f'test:{h.id}:{_uuid.uuid4().hex}',
        )
        try:
            deliver_webhook.delay(delivery.id)
        except Exception:
            # Celery unavailable (e.g. in tests) — the sweeper will pick it up
            pass
        return Response({
            'delivery_id': delivery.id,
            'topic': topic,
            'detail': 'Test delivery queued. Check the deliveries endpoint '
                      'in a few seconds for the result.',
        }, status=202)


class WebhookDeliveriesView(APIView):
    """GET /api/v1/webhooks/<id>/deliveries/?limit=50

    Recent delivery history for one webhook. Sellers use this to debug
    "did MICHA send me the order.placed for ORD-123?"
    """
    permission_classes = [
        permissions.IsAuthenticated, IsSellerOrSuperuser, IsNotSuspended,
    ]

    def get(self, request, hook_id):
        h = get_object_or_404(SellerWebhook, pk=hook_id, seller=request.user)
        try:
            limit = int(request.query_params.get('limit', 50))
        except (TypeError, ValueError):
            limit = 50
        limit = max(1, min(limit, 200))
        rows = (
            WebhookDelivery.objects.filter(webhook=h)
            .order_by('-created_at')[:limit]
        )
        return Response({
            'results': [
                {
                    'id': d.id, 'topic': d.topic, 'status': d.status,
                    'attempts': d.attempts, 'max_attempts': d.max_attempts,
                    'response_status': d.response_status,
                    'last_error': (d.last_error or '')[:200],
                    'created_at': d.created_at,
                    'delivered_at': d.delivered_at,
                    'next_attempt_at': d.next_attempt_at,
                }
                for d in rows
            ],
        })
