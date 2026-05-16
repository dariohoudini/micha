"""
apps/flags/views.py — admin-only CRUD for flags + exposure stats.
"""
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.db.models import Count
from datetime import timedelta
from django.utils import timezone

from .models import Flag, FlagOverride, ExperimentExposure, FlagKind


def _serialize_flag(f):
    return {
        'id': f.id, 'name': f.name, 'kind': f.kind,
        'description': f.description, 'is_active': f.is_active,
        'rules': f.rules, 'default_value': f.default_value,
        'created_at': f.created_at, 'updated_at': f.updated_at,
    }


class FlagListView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        rows = Flag.objects.all().order_by('name')
        return Response({'results': [_serialize_flag(f) for f in rows]})

    def post(self, request):
        name = (request.data.get('name') or '').strip()
        kind = (request.data.get('kind') or '').strip()
        if not name or kind not in {k.value for k in FlagKind}:
            return Response({'error': 'validation_error',
                             'detail': 'name + valid kind required'}, status=400)
        if Flag.objects.filter(name=name).exists():
            return Response({'error': 'duplicate'}, status=409)

        f = Flag.objects.create(
            name=name, kind=kind,
            description=(request.data.get('description') or '')[:1000],
            rules=request.data.get('rules') or {},
            default_value=request.data.get('default_value', False),
            is_active=bool(request.data.get('is_active', True)),
        )
        return Response(_serialize_flag(f), status=201)


class FlagDetailView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, name):
        f = get_object_or_404(Flag, name=name)
        return Response(_serialize_flag(f))

    def patch(self, request, name):
        f = get_object_or_404(Flag, name=name)
        ALLOWED = {'description', 'is_active', 'rules', 'default_value'}
        for k in ALLOWED:
            if k in request.data:
                setattr(f, k, request.data[k])
        f.save()  # bumps the cache tag automatically
        return Response(_serialize_flag(f))

    def delete(self, request, name):
        f = get_object_or_404(Flag, name=name)
        f.delete()
        return Response(status=204)


class FlagExposureStatsView(APIView):
    """GET /api/v1/flags/<name>/exposures/ — variant distribution over a window."""
    permission_classes = [permissions.IsAdminUser]

    def get(self, request, name):
        try:
            hours = int(request.query_params.get('hours', 24))
        except ValueError:
            hours = 24
        hours = max(1, min(hours, 24 * 30))
        cutoff = timezone.now() - timedelta(hours=hours)

        rows = (
            ExperimentExposure.objects
            .filter(flag_name=name, created_at__gte=cutoff)
            .values('variant')
            .annotate(count=Count('id'))
            .order_by('-count')
        )
        total = sum(r['count'] for r in rows)
        return Response({
            'flag': name, 'window_hours': hours, 'total_exposures': total,
            'breakdown': [
                {'variant': r['variant'], 'count': r['count'],
                 'share': round(r['count'] / total, 4) if total else 0.0}
                for r in rows
            ],
        })


class FlagEvaluateView(APIView):
    """GET /api/v1/flags/evaluate/<name>/  — evaluate for current user.

    Public-ish: any authenticated user can ask whether THEY are in a flag.
    Used by the frontend to gate UI features without leaking ops state.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, name):
        from .evaluator import evaluate
        v = evaluate(name, user=request.user)
        return Response({'flag': name, 'value': v})


class FlagOverrideView(APIView):
    """POST a per-user override. Admin-only; used by support / QA."""
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, name):
        f = get_object_or_404(Flag, name=name)
        uid = request.data.get('user_id')
        value = request.data.get('value')
        if uid is None or value is None:
            return Response({'error': 'validation_error',
                             'detail': 'user_id and value required'}, status=400)
        o, created = FlagOverride.objects.update_or_create(
            flag=f, user_id=uid,
            defaults={'value': value, 'note': (request.data.get('note') or '')[:200]},
        )
        # Bust the per-user override cache entry
        try:
            from apps.core.cache_kit import bump_tag
            bump_tag(f'flag_override:{f.id}:{uid}')
        except Exception:
            pass
        return Response({
            'flag': name, 'user_id': uid, 'value': o.value,
            'created': created,
        }, status=201 if created else 200)
