"""
apps/alerts/views.py — user-facing self-serve.
"""
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404

from .models import SavedSearch, AlertDelivery
from . import service


def _serialize_saved(s: SavedSearch) -> dict:
    return {
        'id': s.id, 'name': s.name,
        'query_normalized': s.query_normalized,
        'filters': s.filters,
        'is_active': s.is_active,
        'baseline_size': len(s.baseline_product_ids or []),
        'min_notify_interval_seconds': s.min_notify_interval_seconds,
        'last_run_at': s.last_run_at,
        'last_notified_at': s.last_notified_at,
        'created_at': s.created_at,
    }


class SavedSearchListView(APIView):
    """GET — my saved searches. POST — create."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        rows = (
            SavedSearch.objects.filter(user=request.user)
            .order_by('-created_at')[:50]
        )
        return Response({'results': [_serialize_saved(s) for s in rows]})

    def post(self, request):
        try:
            sr = service.save_search(
                request.user,
                name=request.data.get('name', ''),
                query=request.data.get('query', ''),
                filters=request.data.get('filters') or {},
            )
        except service.AlertsError as e:
            return Response({'error': 'validation_error', 'detail': str(e)},
                            status=400)
        return Response(_serialize_saved(sr), status=201)


class SavedSearchDetailView(APIView):
    """GET / PATCH (pause/resume + min_notify_interval) / DELETE."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, pk):
        sr = get_object_or_404(SavedSearch, pk=pk, user=request.user)
        return Response(_serialize_saved(sr))

    def patch(self, request, pk):
        sr = get_object_or_404(SavedSearch, pk=pk, user=request.user)
        # Whitelist of mutable fields
        if 'is_active' in request.data:
            sr.is_active = bool(request.data['is_active'])
        if 'min_notify_interval_seconds' in request.data:
            try:
                v = int(request.data['min_notify_interval_seconds'])
                if v < 300 or v > 86400 * 30:
                    return Response({'error': 'validation_error',
                                     'detail': 'interval must be 300s..30d'},
                                    status=400)
                sr.min_notify_interval_seconds = v
            except (TypeError, ValueError):
                return Response({'error': 'validation_error'}, status=400)
        if 'name' in request.data:
            sr.name = str(request.data['name'])[:120]
        sr.save()
        return Response(_serialize_saved(sr))

    def delete(self, request, pk):
        sr = get_object_or_404(SavedSearch, pk=pk, user=request.user)
        sr.delete()
        return Response(status=204)


class AlertDeliveryListView(APIView):
    """GET /alerts/deliveries/ — my recent alert deliveries (notifications)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        rows = (
            AlertDelivery.objects.filter(user=request.user)
            .order_by('-delivered_at')[:100]
        )
        return Response({'results': [{
            'id': d.id, 'kind': d.kind, 'channel': d.channel,
            'saved_search_id': d.saved_search_id,
            'product_ids': d.product_ids,
            'payload': d.payload,
            'delivered_at': d.delivered_at,
        } for d in rows]})
