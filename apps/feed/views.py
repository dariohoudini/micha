"""
apps/feed/views.py — single endpoint that powers the personalized homepage.
"""
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response

from . import service


class FeedView(APIView):
    """GET /api/v1/feed/?section=home&max=60 — assembled personalized feed."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        section = (request.query_params.get('section') or 'home')[:40]
        try:
            max_tiles = int(request.query_params.get('max') or 60)
        except ValueError:
            max_tiles = 60
        max_tiles = max(1, min(max_tiles, 200))

        # Anonymous users: derive a stable token from the session so they
        # see consistent feeds across requests in the same session.
        anon_token = ''
        if not getattr(request.user, 'is_authenticated', False):
            try:
                from hashlib import sha256
                sid = request.session.session_key or ''
                if sid:
                    anon_token = sha256(sid.encode()).hexdigest()[:32]
            except Exception:
                pass

        result = service.build_feed(
            user=request.user if getattr(request.user, 'is_authenticated', False) else None,
            anon_token=anon_token,
            max_tiles=max_tiles,
            section=section,
        )
        # Only expose debug counters to admins
        if not (request.user.is_authenticated and request.user.is_staff):
            result.pop('debug', None)
        return Response(result)
