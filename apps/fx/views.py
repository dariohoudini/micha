"""
apps/fx/views.py — admin-facing endpoints for rate management + audit views.
"""
from decimal import Decimal
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta

from .models import FXRate, ConversionEvent, FXRateSource
from . import service


class FXRateListView(APIView):
    """GET — current rate per pair. POST — manually set a rate (admin only)."""
    def get_permissions(self):
        if self.request.method == 'POST':
            return [permissions.IsAdminUser()]
        return [permissions.AllowAny()]

    def get(self, request):
        rows = FXRate.objects.filter(valid_until__isnull=True).order_by(
            'source_currency', 'target_currency',
        )
        return Response({'results': [{
            'source_currency': r.source_currency,
            'target_currency': r.target_currency,
            'rate': str(r.rate),
            'source': r.source,
            'valid_from': r.valid_from,
            'recorded_by_id': r.recorded_by_id,
        } for r in rows]})

    def post(self, request):
        try:
            source_cur = (request.data.get('source_currency') or '').upper()
            target_cur = (request.data.get('target_currency') or '').upper()
            rate = Decimal(str(request.data.get('rate')))
        except Exception:
            return Response({'error': 'validation_error'}, status=400)
        if not source_cur or not target_cur or source_cur == target_cur:
            return Response({'error': 'invalid_currencies'}, status=400)
        try:
            r = service.update_rate(
                source_currency=source_cur, target_currency=target_cur,
                rate=rate, source=FXRateSource.MANUAL, user=request.user,
                note=(request.data.get('note') or '')[:200],
            )
        except service.FXError as e:
            return Response({'error': 'fx_error', 'detail': str(e)}, status=400)
        return Response({
            'id': r.id, 'rate': str(r.rate),
            'valid_from': r.valid_from,
            'detail': f'Set {source_cur}->{target_cur} = {r.rate}',
        }, status=201)


class FXRateHistoryView(APIView):
    """GET /fx/rates/<source>/<target>/history/?days=30"""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, source, target):
        try:
            days = int(request.query_params.get('days', 30))
        except ValueError:
            days = 30
        days = max(1, min(days, 365))
        cutoff = timezone.now() - timedelta(days=days)

        rows = (
            FXRate.objects
            .filter(source_currency=source.upper(), target_currency=target.upper())
            .filter(
                # current row OR closed within window
                __import__('django.db.models', fromlist=['Q']).Q(valid_until__isnull=True)
                | __import__('django.db.models', fromlist=['Q']).Q(valid_until__gte=cutoff)
            )
            .order_by('-valid_from')[:200]
        )
        return Response({'results': [{
            'id': r.id, 'rate': str(r.rate),
            'source': r.source,
            'valid_from': r.valid_from, 'valid_until': r.valid_until,
            'note': r.note,
        } for r in rows]})


class FXConvertView(APIView):
    """GET /fx/convert/?from=USD&to=AOA&amount=100 — preview a conversion.

    Does NOT log a ConversionEvent (this is a quote, not a transaction).
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        from_cur = (request.query_params.get('from') or '').upper()
        to_cur   = (request.query_params.get('to') or '').upper()
        try:
            amount = Decimal(str(request.query_params.get('amount') or '0'))
        except Exception:
            return Response({'error': 'bad_amount'}, status=400)
        if not from_cur or not to_cur:
            return Response({'error': 'missing_currency'}, status=400)
        try:
            out = service.convert(amount, from_currency=from_cur,
                                  to_currency=to_cur, log_event=False)
        except service.RateNotFound:
            return Response({'error': 'rate_not_found'}, status=404)
        rate_row = service.get_rate(from_cur, to_cur)
        return Response({
            'from': from_cur, 'to': to_cur,
            'amount_from': str(amount), 'amount_to': str(out),
            'rate': str(rate_row.rate) if rate_row else None,
            'rate_source': rate_row.source if rate_row else None,
        })


class FXConversionAuditView(APIView):
    """GET /fx/conversions/?ref_type=order&ref_id=xxx — audit lookup."""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        qs = ConversionEvent.objects.all().order_by('-created_at')
        rt = request.query_params.get('ref_type')
        rid = request.query_params.get('ref_id')
        if rt:
            qs = qs.filter(ref_type=rt)
        if rid:
            qs = qs.filter(ref_id=rid)
        rows = qs[:100]
        return Response({'results': [{
            'id': r.id,
            'from_currency': r.from_currency, 'to_currency': r.to_currency,
            'amount_from': str(r.amount_from), 'amount_to': str(r.amount_to),
            'rate_applied': str(r.rate_applied),
            'ref_type': r.ref_type, 'ref_id': r.ref_id,
            'created_at': r.created_at,
        } for r in rows]})
