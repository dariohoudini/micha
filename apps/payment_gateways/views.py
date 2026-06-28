"""
Payment gateway HTTP surface.

  POST /charge          — initiate a charge
  POST /webhooks/<gw>/  — inbound webhook from provider
  GET  /intents/me/     — my intent history
"""
from __future__ import annotations

from decimal import Decimal

from django.shortcuts import get_object_or_404
from rest_framework import permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import GatewayTransaction, PaymentIntent


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def charge_view(request):
    try:
        amount = Decimal(str(request.data.get('amount')))
    except Exception:
        return Response({'detail': 'amount required'}, status=400)
    currency = (request.data.get('currency') or 'AOA').upper()
    purpose = (request.data.get('purpose') or 'checkout')[:40]
    country = (request.data.get('country') or '').upper()
    result = services.charge(
        amount=amount, currency=currency, purpose=purpose,
        user=request.user, country=country,
        idempotency_key=request.data.get('idempotency_key'),
        user_metadata={'phone': getattr(request.user, 'phone', '') or '',
                       'email': request.user.email},
        gateway_metadata={
            'payment_method_id': request.data.get('payment_method_id', ''),
            'callback_url': request.data.get('callback_url', ''),
            'return_url': request.data.get('return_url', ''),
        },
    )
    return Response(result, status=201)


@api_view(['POST'])
@permission_classes([AllowAny])
def webhook_view(request, gateway):
    """Inbound webhook. Signature is verified inside services.
    Returns 200 on dedup-replay so the provider stops retrying."""
    headers = {k: v for k, v in request.META.items()
               if k.startswith('HTTP_') or k in (
                   'Stripe-Signature', 'X-EMIS-Signature',
               )}
    # Normalise common ones for the gateway adapters.
    headers['Stripe-Signature'] = request.META.get('HTTP_STRIPE_SIGNATURE', '')
    headers['X-EMIS-Signature'] = request.META.get('HTTP_X_EMIS_SIGNATURE', '')
    body = request.body
    result = services.handle_webhook(
        gateway_name=gateway, headers=headers, body=body,
        body_text=body.decode('utf-8', errors='replace'),
    )
    return Response(result, status=200 if result.get('ok') else 400)


class MyIntentsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        rows = PaymentIntent.objects.filter(user=request.user).values(
            'id', 'gateway', 'purpose', 'amount', 'currency',
            'status', 'failure_code', 'failure_message',
            'created_at', 'completed_at',
        )[:100]
        return Response(list(rows))
