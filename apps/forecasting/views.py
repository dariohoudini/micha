"""
apps/forecasting/views.py — seller-facing endpoints for forecasts + reorder recs.
"""
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import DailyDemand, DemandForecast, ReorderRecommendation, ReorderAction
from . import service


def _serialize_rec(r):
    return {
        'id': r.id, 'product_id': str(r.product_id),
        'current_stock': r.current_stock,
        'reorder_point': r.reorder_point,
        'recommended_qty': r.recommended_qty,
        'safety_stock': r.safety_stock,
        'lead_time_days': r.lead_time_days,
        'daily_mean': float(r.forecast_daily_mean),
        'daily_stddev': float(r.forecast_daily_stddev),
        'reason': r.reason,
        'action': r.action,
        'generated_at': r.generated_at,
    }


class RecommendationListView(APIView):
    """GET — pending recommendations for my products."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = ReorderRecommendation.objects.filter(
            product__store__owner=request.user,
        )
        action_filter = request.query_params.get('action', 'pending')
        if action_filter:
            qs = qs.filter(action=action_filter)
        rows = qs.select_related('product').order_by('-generated_at')[:100]
        return Response({'results': [_serialize_rec(r) for r in rows]})


class RecommendationDetailView(APIView):
    """POST — mark as ordered or dismissed."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        rec = get_object_or_404(
            ReorderRecommendation, pk=pk,
            product__store__owner=request.user,
        )
        action = (request.data.get('action') or '').strip()
        try:
            rec = service.act_on_recommendation(rec, action=action)
        except ValueError as e:
            return Response({'error': 'validation_error', 'detail': str(e)},
                            status=400)
        return Response(_serialize_rec(rec))


class ForecastDetailView(APIView):
    """GET /forecasting/products/<id>/  — full forecast + recommendation."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, product_id):
        from apps.products.models import Product
        product = get_object_or_404(
            Product, pk=product_id, store__owner=request.user,
        )
        # Run / refresh
        result = service.generate_recommendation(product)
        # Daily history (last 30 days for chart)
        history = list(
            DailyDemand.objects.filter(product=product)
            .order_by('-day')[:30]
            .values('day', 'units', 'revenue')
        )
        return Response({
            'product_id': str(product.id),
            'product_title': product.title,
            'current_stock': product.quantity,
            'forecast': result.get('forecast'),
            'reorder_point': result['reorder_point'],
            'safety_stock': result['safety_stock'],
            'recommended_qty': result['recommended_qty'],
            'needs_reorder': result.get('needs_reorder'),
            'history_30d': history,
        })
