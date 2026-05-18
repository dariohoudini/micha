"""
apps/gift_cards/views.py

  POST /gift-cards/issue/   admin — mint a card (returns plaintext ONCE)
  POST /gift-cards/claim/   buyer — claim by code
  GET  /gift-cards/me/      buyer — list my claimed cards
  GET  /gift-cards/<id>/    buyer — detail + recent transactions

Redeem is intentionally NOT a public endpoint — checkout calls
service.redeem() internally. Letting a user "redeem" via the API would
bypass the order linkage and produce orphan transactions.
"""
from decimal import Decimal
from datetime import timedelta
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.idempotency.decorators import idempotent
from .models import GiftCard, GiftCardTransaction
from . import service


def _serialize_card(c, *, include_balance: bool = True) -> dict:
    out = {
        'id': c.id,
        'code_prefix': c.code_prefix,
        'currency': c.currency,
        'status': c.status,
        'initial_value': str(c.initial_value),
        'expires_at': c.expires_at,
        'claimed_at': c.claimed_at,
        'created_at': c.created_at,
    }
    if include_balance:
        out['current_balance'] = str(c.current_balance)
    return out


class IssueCardView(APIView):
    """POST /gift-cards/issue/  body: {amount, currency?, expires_in_days?}
    Returns the plaintext code ONCE. Admin-only for now; later wired into
    a paid-checkout flow.

    Idempotency-Key REQUIRED: issuing a card mints real value. A retry
    that re-mints would return TWO plaintext codes for one operator
    intent — both bound to the same audit context — which is unforgivable
    in a value-issuance flow.
    """
    permission_classes = [permissions.IsAdminUser]

    @idempotent(required=True)
    def post(self, request):
        try:
            amount = Decimal(str(request.data.get('amount')))
        except Exception:
            return Response({'error': 'validation_error',
                             'detail': 'amount required'}, status=400)
        if amount <= 0 or amount > Decimal('1000000'):
            return Response({'error': 'validation_error',
                             'detail': 'amount must be 0 < x <= 1,000,000'},
                            status=400)
        currency = (request.data.get('currency') or 'AOA').upper()
        expires_in = request.data.get('expires_in_days')
        expires_at = None
        if expires_in is not None:
            try:
                d = int(expires_in)
                if d < 1 or d > 365 * 5:
                    return Response({'error': 'validation_error',
                                     'detail': 'expires_in_days 1..1825'},
                                    status=400)
                expires_at = timezone.now() + timedelta(days=d)
            except ValueError:
                return Response({'error': 'validation_error'}, status=400)

        try:
            card, plaintext = service.issue(
                amount, currency=currency, expires_at=expires_at,
                purchased_by=request.user, actor=request.user,
            )
        except service.GiftCardError as e:
            return Response({'error': 'gift_card_error', 'detail': str(e)},
                            status=400)
        body = _serialize_card(card)
        body['code'] = plaintext  # ONE-TIME REVEAL
        return Response(body, status=201)


class ClaimCardView(APIView):
    """POST /gift-cards/claim/  body: {code}

    Idempotency-Key optional — claim() is already idempotent at the
    service layer (re-claiming your own card is a no-op), but accepting
    the header lets clients dedupe at the HTTP layer too without paying
    the round trip.
    """
    permission_classes = [permissions.IsAuthenticated]

    @idempotent()
    def post(self, request):
        code = (request.data.get('code') or '').strip()
        if not code:
            return Response({'error': 'validation_error',
                             'detail': 'code required'}, status=400)
        try:
            card = service.claim(code, user=request.user)
        except service.InvalidCode:
            # Don't distinguish "wrong" from "expired" — prevents enumeration
            return Response({'error': 'invalid_code'}, status=400)
        except service.AlreadyClaimed:
            return Response({'error': 'already_claimed'}, status=409)
        except service.CardNotActive as e:
            return Response({'error': 'card_not_active', 'detail': str(e)},
                            status=400)
        except service.GiftCardError as e:
            return Response({'error': 'gift_card_error', 'detail': str(e)},
                            status=400)
        return Response(_serialize_card(card))


class MyCardsView(APIView):
    """GET /gift-cards/me/ — cards claimed by me."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        rows = (
            GiftCard.objects.filter(claimed_by=request.user)
            .order_by('-created_at')[:100]
        )
        return Response({'results': [_serialize_card(c) for c in rows]})


class CardDetailView(APIView):
    """GET /gift-cards/<id>/ — detail + recent transactions."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        card = get_object_or_404(GiftCard, pk=pk, claimed_by=request.user)
        tx_rows = list(
            GiftCardTransaction.objects.filter(card=card)
            .order_by('-created_at')[:50]
            .values('kind', 'amount', 'balance_after', 'ref_type',
                    'ref_id', 'note', 'created_at')
        )
        return Response({
            **_serialize_card(card),
            'transactions': tx_rows,
        })
