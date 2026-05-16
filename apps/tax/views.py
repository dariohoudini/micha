"""
apps/tax/views.py — endpoints for jurisdiction/rate management + calc preview.
"""
from decimal import Decimal
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import TaxJurisdiction, TaxRate, TaxCalculation, TaxRateSource
from . import service


class JurisdictionListView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        rows = TaxJurisdiction.objects.filter(is_active=True).order_by(
            'country_code', 'province_code',
        )
        return Response({'results': [{
            'id': j.id, 'country_code': j.country_code,
            'province_code': j.province_code, 'name': j.name,
        } for j in rows]})

    def post(self, request):
        country = (request.data.get('country_code') or '').upper()
        province = (request.data.get('province_code') or '').upper()
        name = (request.data.get('name') or '').strip()
        if not country or not name:
            return Response({'error': 'validation_error',
                             'detail': 'country_code + name required'}, status=400)
        j, created = TaxJurisdiction.objects.get_or_create(
            country_code=country, province_code=province,
            defaults={'name': name},
        )
        if not created and j.name != name:
            j.name = name
            j.save(update_fields=['name'])
        return Response({'id': j.id, 'country_code': j.country_code,
                         'province_code': j.province_code, 'name': j.name,
                         'created': created}, status=201 if created else 200)


class RateUpdateView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, jurisdiction_id):
        j = get_object_or_404(TaxJurisdiction, pk=jurisdiction_id)
        try:
            rate = Decimal(str(request.data.get('rate')))
        except Exception:
            return Response({'error': 'bad_rate'}, status=400)
        try:
            new_row = service.update_rate(
                jurisdiction=j, rate=rate, source=TaxRateSource.MANUAL,
                user=request.user, note=(request.data.get('note') or '')[:200],
                name=(request.data.get('name') or 'VAT'),
            )
        except service.TaxError as e:
            return Response({'error': 'tax_error', 'detail': str(e)}, status=400)
        return Response({
            'id': new_row.id, 'rate': str(new_row.rate),
            'valid_from': new_row.valid_from,
            'detail': f'Set {j} rate to {new_row.rate}',
        }, status=201)


class RateHistoryView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, jurisdiction_id):
        rows = (
            TaxRate.objects.filter(jurisdiction_id=jurisdiction_id)
            .order_by('-valid_from')[:200]
        )
        return Response({'results': [{
            'id': r.id, 'rate': str(r.rate),
            'name': r.name, 'source': r.source,
            'valid_from': r.valid_from, 'valid_until': r.valid_until,
            'note': r.note,
        } for r in rows]})


class CalculateView(APIView):
    """POST /tax/calculate/  body:
        {
          "ship_to_country": "AO",
          "ship_to_province": "LUA",
          "line_items": [{"id": "li-1", "amount": "100.00", "category": "STANDARD"}, ...]
        }
    Returns the breakdown — does NOT log a TaxCalculation row (preview only).
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            result = service.calculate(
                request.data.get('line_items') or [],
                ship_to_country=request.data.get('ship_to_country', ''),
                ship_to_province=request.data.get('ship_to_province', ''),
                log_calc=False,
            )
        except service.NoJurisdiction as e:
            return Response({'error': 'no_jurisdiction', 'detail': str(e)}, status=404)
        except service.NoRate as e:
            return Response({'error': 'no_rate', 'detail': str(e)}, status=404)
        return Response(result)


class CalculationAuditView(APIView):
    """GET /tax/calculations/?ref_type=order&ref_id=xxx"""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        qs = TaxCalculation.objects.all().order_by('-created_at')
        rt = request.query_params.get('ref_type')
        rid = request.query_params.get('ref_id')
        if rt: qs = qs.filter(ref_type=rt)
        if rid: qs = qs.filter(ref_id=rid)
        rows = qs[:100]
        return Response({'results': [{
            'id': r.id, 'ref_type': r.ref_type, 'ref_id': r.ref_id,
            'ship_to_country': r.ship_to_country,
            'ship_to_province': r.ship_to_province,
            'rate_applied': str(r.rate_applied),
            'total_taxable': str(r.total_taxable),
            'total_tax': str(r.total_tax),
            'created_at': r.created_at,
            'breakdown': r.breakdown,
        } for r in rows]})
