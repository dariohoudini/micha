"""
apps/affiliates/views.py — public click endpoint + self-service dashboard.
"""
from decimal import Decimal
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Q
from hashlib import sha256

from .models import (
    AffiliateProgram, AffiliateAccount, AffiliateClick,
    AffiliateConversion, AffiliatePayout, ConversionStatus,
)
from . import service


def _client_ip(request) -> str:
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return (xff.split(',')[0].strip() if xff else (request.META.get('REMOTE_ADDR') or ''))[:45]


def _session_token(request) -> str:
    try:
        sid = request.session.session_key or ''
        if sid:
            return sha256(sid.encode()).hexdigest()[:64]
    except Exception:
        pass
    return ''


class ClickView(APIView):
    """POST /affiliates/click/  body: {code, product_id?}

    Anyone can hit this. We track the click; no info leaked back about
    whether the code is valid (returns 200 either way) — prevents code
    enumeration."""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        code = (request.data.get('code') or '').strip()
        product_id = (request.data.get('product_id') or '').strip()
        click = service.record_click(
            code,
            user=request.user if getattr(request.user, 'is_authenticated', False) else None,
            session_token=_session_token(request),
            product_id=product_id,
            ip=_client_ip(request),
            user_agent=request.META.get('HTTP_USER_AGENT', '')[:200],
            referrer=request.META.get('HTTP_REFERER', '')[:400],
        )
        # Always 200 — don't leak code validity
        return Response({'tracked': click is not None}, status=200)


class MyAffiliateView(APIView):
    """GET /affiliates/me/ — affiliate dashboard for this user."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        accounts = list(
            AffiliateAccount.objects.filter(user=request.user)
            .select_related('program')
        )
        if not accounts:
            return Response({
                'has_accounts': False,
                'accounts': [],
            })
        out = []
        for acc in accounts:
            stats = AffiliateConversion.objects.filter(account=acc).aggregate(
                pending=Sum('commission_amount',
                             filter=Q(status=ConversionStatus.PENDING)),
                confirmed=Sum('commission_amount',
                               filter=Q(status=ConversionStatus.CONFIRMED)),
                paid=Sum('commission_amount',
                          filter=Q(status=ConversionStatus.PAID)),
                reversed=Sum('commission_amount',
                              filter=Q(status=ConversionStatus.REVERSED)),
            )
            out.append({
                'account_id': acc.id,
                'program': acc.program.name,
                'code': acc.code,
                'is_active': acc.is_active,
                'tier_multiplier': str(acc.tier_multiplier),
                'effective_rate': str(acc.effective_rate()),
                'total_earned_aoa': str(acc.total_earned_aoa),
                'totals': {
                    'pending':   str(stats['pending']   or Decimal('0')),
                    'confirmed': str(stats['confirmed'] or Decimal('0')),
                    'paid':      str(stats['paid']      or Decimal('0')),
                    'reversed':  str(stats['reversed']  or Decimal('0')),
                },
                'min_payout_aoa': str(acc.program.min_payout_aoa),
            })
        return Response({'has_accounts': True, 'accounts': out})


class MyConversionsView(APIView):
    """GET /affiliates/me/conversions/ — recent commission events."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        accounts = list(AffiliateAccount.objects.filter(user=request.user)
                          .values_list('id', flat=True))
        rows = (
            AffiliateConversion.objects.filter(account_id__in=accounts)
            .order_by('-created_at')[:100]
        )
        return Response({'results': [{
            'id': c.id, 'order_id': c.order_id,
            'order_total': str(c.order_total),
            'commission_amount': str(c.commission_amount),
            'status': c.status,
            'created_at': c.created_at,
            'confirmed_at': c.confirmed_at,
            'paid_at': c.paid_at,
            'reversed_reason': c.reversed_reason,
        } for c in rows]})


class MyPayoutsView(APIView):
    """GET /affiliates/me/payouts/ — payout history."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        accounts = list(AffiliateAccount.objects.filter(user=request.user)
                          .values_list('id', flat=True))
        rows = (
            AffiliatePayout.objects.filter(account_id__in=accounts)
            .order_by('-created_at')[:50]
        )
        return Response({'results': [{
            'id': p.id, 'amount_aoa': str(p.amount_aoa),
            'conversion_count': p.conversion_count,
            'status': p.status,
            'paid_at': p.paid_at,
            'created_at': p.created_at,
        } for p in rows]})
