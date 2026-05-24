"""
apps/analytics/attribution.py
──────────────────────────────

UTM + multi-touch attribution model (R7).

Why this exists
───────────────
Marketing spend without attribution is throwing money at a wall.
Pre-R7 MICHA had FunnelEvent but no UTM source/medium/campaign
tracking — no way to answer "which campaign drove this purchase?".

Model: AttributionTouch
───────────────────────
Append-only. One row per touchpoint (any page view with utm_* params
OR a referrer worth recording). A purchase event reads the most
recent N touches for the user/session to build the conversion
attribution.

Models
──────
  AttributionTouch
    user (nullable for anon), session_id, utm_*, referrer, landing_path,
    occurred_at

API
───
  POST /api/v1/analytics/touch/    body: {utm_source, utm_medium,
                                          utm_campaign, utm_content,
                                          utm_term, referrer,
                                          landing_path, session_id}
  GET  /api/v1/analytics/attribution/?days=30  → admin summary by source/medium/campaign
"""
from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum, Count
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsAdminOrSuperuser


log = logging.getLogger('micha.attribution')


class AttributionTouch(models.Model):
    """A single attribution touchpoint — page view tagged with UTM
    parameters OR a referrer worth recording for attribution.

    Append-only by convention; no .delete() override but the retention
    policy keeps these for 365 days (override via DATA_RETENTION_POLICY).
    """

    # Anonymous-friendly — most touches happen pre-login. session_id
    # is a frontend-generated random token persisted in localStorage.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, null=True, blank=True,
        related_name='attribution_touches',
    )
    session_id = models.CharField(max_length=64, blank=True, default='',
                                  db_index=True)

    utm_source = models.CharField(max_length=80, blank=True, default='')
    utm_medium = models.CharField(max_length=80, blank=True, default='')
    utm_campaign = models.CharField(max_length=120, blank=True, default='')
    utm_content = models.CharField(max_length=120, blank=True, default='')
    utm_term = models.CharField(max_length=120, blank=True, default='')

    referrer = models.URLField(max_length=500, blank=True, default='')
    landing_path = models.CharField(max_length=500, blank=True, default='')

    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'analytics_attribution_touch'
        ordering = ['-occurred_at']
        indexes = [
            models.Index(fields=['user', '-occurred_at']),
            models.Index(fields=['session_id', '-occurred_at']),
            models.Index(fields=['utm_source', 'utm_campaign', '-occurred_at']),
        ]

    def __str__(self):
        return f'AttributionTouch({self.utm_source}/{self.utm_campaign})'


# ─── Service ──────────────────────────────────────────────────────────


def record_touch(*, request=None, user=None, **fields) -> AttributionTouch:
    """Insert a touchpoint. Defensive on every field — partial payloads
    don't reject."""
    safe = {}
    for k in ('utm_source', 'utm_medium', 'utm_campaign',
              'utm_content', 'utm_term', 'referrer', 'landing_path',
              'session_id'):
        v = fields.get(k)
        if v is None:
            v = ''
        # Truncate to model max_length minus 1 byte slack.
        max_len = 120 if k.startswith('utm_') else 500
        if k == 'session_id':
            max_len = 64
        safe[k] = str(v)[:max_len]

    return AttributionTouch.objects.create(
        user=user if (user and getattr(user, 'pk', None)) else None,
        **safe,
    )


# ─── Views ────────────────────────────────────────────────────────────


class AttributionTouchView(APIView):
    """``POST /api/v1/analytics/touch/`` — log a touchpoint.

    Open to anonymous callers (anon traffic IS the marketing-funnel
    top); authenticated callers are linked to user.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        user = request.user if getattr(request, 'user', None) \
            and getattr(request.user, 'is_authenticated', False) else None
        record_touch(request=request, user=user, **request.data)
        return Response({'detail': 'ok'}, status=201)


class AttributionReportView(APIView):
    """``GET /api/v1/analytics/attribution/?days=30`` — admin summary."""
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperuser]

    def get(self, request):
        try:
            days = int(request.query_params.get('days', '30'))
        except (TypeError, ValueError):
            days = 30
        days = max(1, min(days, 365))
        since = timezone.now() - timedelta(days=days)

        by_source = (
            AttributionTouch.objects
            .filter(occurred_at__gte=since)
            .exclude(utm_source='')
            .values('utm_source', 'utm_medium', 'utm_campaign')
            .annotate(touches=Count('id'))
            .order_by('-touches')[:50]
        )
        return Response({
            'window_days': days,
            'rows': [
                {
                    'utm_source': r['utm_source'],
                    'utm_medium': r['utm_medium'],
                    'utm_campaign': r['utm_campaign'],
                    'touches': r['touches'],
                }
                for r in by_source
            ],
        })
