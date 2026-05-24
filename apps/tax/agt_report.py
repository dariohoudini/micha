"""
apps/tax/agt_report.py
───────────────────────

AGT (Administração Geral Tributária) IVA filing report.

What Angola tax filing actually requires
─────────────────────────────────────────
AGT receives monthly IVA declarations on Form Modelo 1 (also called
"Mapa-Resumo do IVA"). The line items: (a) total taxable sales,
(b) total IVA collected, (c) jurisdictional breakdown if multi-region,
(d) the supporting invoice list with NIF + amount per invoice.

This endpoint produces the source data for that form: every
TaxCalculation row in the requested period, aggregated and itemised.
The CSV column shape is structured for direct import into the
spreadsheet templates AGT publishes.

Why a Python view, not the FAT (Ficheiro Auditoria Tributária) format
─────────────────────────────────────────────────────────────────────
FAT is the XML format AGT mandates for full-data submissions of large
filers. It's a heavy schema (SAFT-AO) that warrants its own module
when the platform crosses the FAT threshold (~5M AOA/year revenue).
This endpoint serves the smaller monthly filing path that 99% of
MICHA's sellers will use.

Endpoint
────────
  GET /api/v1/tax/report/agt/?from=YYYY-MM-DD&to=YYYY-MM-DD
                            [&format=json|csv]
                            [&jurisdiction_id=N]
  admin-only.

Returns either JSON (summary + line items) or text/csv (filing-ready).
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import permissions
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsAdminOrSuperuser
from .models import TaxCalculation


class _PlainCSVRenderer(BaseRenderer):
    """Pass-through renderer for the CSV branch.

    Without a renderer set, DRF's APIView default-route the response
    through JSONRenderer — which mangles a plain HttpResponse (it tries
    to JSON-serialise the raw CSV bytes and the URL resolver gets
    confused, ultimately reporting 404). Declaring a renderer that
    matches the CSV content-type makes DRF's content negotiator pick
    THIS renderer for the request and pass our pre-built HttpResponse
    through unmodified.
    """
    media_type = 'text/csv'
    format = 'csv'
    render_style = 'binary'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        # APIView only calls render() when ``data`` came back from a
        # DRF Response. For the CSV path we return a Django HttpResponse
        # directly, which short-circuits the renderer chain entirely.
        return data


def _parse_date(s: str):
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except Exception:
        return None


class AGTReportView(APIView):
    """``GET /api/v1/tax/report/agt/`` — admin-only IVA filing report."""

    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperuser]
    renderer_classes = [JSONRenderer, _PlainCSVRenderer]

    def get(self, request):
        today = timezone.now().date()
        first_of_month = today.replace(day=1)
        # Default: prior month (the period being filed). E.g. on
        # May 15 → April 1–April 30.
        prev_last = first_of_month - timedelta(days=1)
        prev_first = prev_last.replace(day=1)

        date_from = (
            _parse_date(request.query_params.get('from', ''))
            or prev_first
        )
        date_to = (
            _parse_date(request.query_params.get('to', ''))
            or prev_last
        )
        if date_from > date_to:
            return Response(
                {'error': 'validation_error',
                 'detail': 'from must be <= to'},
                status=400,
            )

        # Window endpoints are inclusive — TaxCalculation.created_at
        # has microsecond precision, so we extend to <= 23:59:59.999999.
        start = datetime.combine(date_from, datetime.min.time())
        end = datetime.combine(date_to, datetime.max.time())

        qs = TaxCalculation.objects.filter(
            created_at__gte=start, created_at__lte=end,
        )
        jurisdiction_id = request.query_params.get('jurisdiction_id')
        if jurisdiction_id:
            qs = qs.filter(jurisdiction_id=jurisdiction_id)

        summary = qs.aggregate(
            total_taxable=Sum('total_taxable'),
            total_tax=Sum('total_tax'),
        )
        total_taxable = summary['total_taxable'] or Decimal('0')
        total_tax = summary['total_tax'] or Decimal('0')

        # By-jurisdiction breakdown (useful when multi-region rolls out).
        by_jur = (
            qs
            .values('jurisdiction__country_code',
                    'jurisdiction__province_code',
                    'jurisdiction__name')
            .annotate(
                taxable=Sum('total_taxable'),
                tax=Sum('total_tax'),
            )
            .order_by('-tax')
        )

        if request.query_params.get('format') == 'csv':
            return self._csv_response(qs, total_taxable, total_tax,
                                      date_from, date_to)

        return Response({
            'period_from': date_from.isoformat(),
            'period_to': date_to.isoformat(),
            'currency': 'AOA',
            'totals': {
                'taxable': str(total_taxable),
                'tax': str(total_tax),
            },
            'by_jurisdiction': [
                {
                    'country_code': r['jurisdiction__country_code'],
                    'province_code': r['jurisdiction__province_code'],
                    'name': r['jurisdiction__name'],
                    'taxable': str(r['taxable']),
                    'tax': str(r['tax']),
                }
                for r in by_jur
            ],
            'count': qs.count(),
        })

    def _csv_response(self, qs, total_taxable, total_tax,
                      date_from, date_to):
        """text/csv — column order matches AGT's reference spreadsheet."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        # Header rows.
        writer.writerow(['MAPA RESUMO IVA — MICHA Express'])
        writer.writerow(['Período', f'{date_from} → {date_to}'])
        writer.writerow(['Total tributável (AOA)', str(total_taxable)])
        writer.writerow(['Total IVA (AOA)',        str(total_tax)])
        writer.writerow([])
        # Detail header.
        writer.writerow([
            'Data', 'Referência', 'Jurisdição', 'País', 'Provincia',
            'Taxa aplicada (%)', 'Base tributável (AOA)',
            'IVA (AOA)',
        ])
        for tc in qs.select_related('jurisdiction').order_by('created_at'):
            writer.writerow([
                tc.created_at.date().isoformat(),
                f'{tc.ref_type}:{tc.ref_id}',
                tc.jurisdiction.name,
                tc.ship_to_country,
                tc.ship_to_province,
                str((tc.rate_applied * 100).quantize(Decimal('0.01'))),
                str(tc.total_taxable),
                str(tc.total_tax),
            ])
        resp = HttpResponse(buf.getvalue(), content_type='text/csv; charset=utf-8')
        resp['Content-Disposition'] = (
            f'attachment; filename="iva-agt-{date_from}-{date_to}.csv"'
        )
        return resp
