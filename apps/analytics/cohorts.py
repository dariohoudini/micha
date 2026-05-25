"""
apps/analytics/cohorts.py
──────────────────────────

Buyer cohort retention analysis (R7).

The shape of the cohort retention curve is the entire business signal:
  • flat curve → product-market fit (users keep coming back)
  • cliff at week 4 → trust failure / payment friction
  • rapid decay → acquisition mismatch (paying for users who churn)

Without cohort visibility, "we have a churn problem" is a guess. With
it, you can compare cohort 2026-W08 vs 2026-W12 and see whether
checkout improvements stuck.

Public endpoint
───────────────
  GET /api/v1/analytics/cohorts/?weeks=12  admin-only

Returns:
  {
    'cohort_size_weeks': 12,
    'cohorts': [
      {
        'cohort_week': '2026-W08',
        'cohort_size': 47,
        'retention': {
          'w0': 47,  # signup week
          'w1': 22,
          'w2': 18,
          ...
        }
      }, ...
    ]
  }

Retention = buyers in the cohort who placed an order in week N+i.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.users.permissions import IsAdminOrSuperuser


User = get_user_model()


def _iso_week(d: date) -> str:
    """Render a date as ISO-year + week (e.g. '2026-W08')."""
    iso_year, iso_week, _ = d.isocalendar()
    return f'{iso_year}-W{iso_week:02d}'


def _week_start(d: date) -> date:
    """Monday of the ISO week containing ``d``."""
    return d - timedelta(days=d.weekday())


def build_cohort_retention(*, weeks: int = 12) -> list:
    """Compute per-cohort retention for the past N weeks.

    Returns a list of {cohort_week, cohort_size, retention} dicts.
    Cheap-ish: 2 queries (users + orders) + Python aggregation. Good
    enough for weekly admin reads; cache in Redis for higher fan-out.
    """
    from apps.orders.models import Order

    today = timezone.now().date()
    earliest = _week_start(today - timedelta(weeks=weeks))

    # All users who joined in the window. Map user_id → signup week start.
    users = (
        User.objects
        .filter(date_joined__date__gte=earliest)
        .values_list('id', 'date_joined')
    )
    user_to_cohort = {}
    cohort_members = defaultdict(set)
    for uid, joined in users:
        wk_start = _week_start(joined.date() if hasattr(joined, 'date') else joined)
        user_to_cohort[uid] = wk_start
        cohort_members[wk_start].add(uid)

    if not user_to_cohort:
        return []

    # All orders by these users since their cohort start. Filter on
    # buyer_id IN cohort users to keep the query bounded.
    cohort_user_ids = list(user_to_cohort.keys())
    orders = (
        Order.objects
        .filter(buyer_id__in=cohort_user_ids)
        .filter(created_at__date__gte=earliest)
        .values_list('buyer_id', 'created_at')
    )

    # Bucket each order into the cohort's relative week N (N=0 means
    # signup week).
    bucket = defaultdict(lambda: defaultdict(set))  # cohort → week_n → {user_ids}
    for buyer_id, created_at in orders:
        cohort_start = user_to_cohort.get(buyer_id)
        if cohort_start is None:
            continue
        order_week = _week_start(
            created_at.date() if hasattr(created_at, 'date') else created_at
        )
        delta_weeks = (order_week - cohort_start).days // 7
        if delta_weeks < 0:
            continue
        bucket[cohort_start][delta_weeks].add(buyer_id)

    # Render — newest cohort first.
    out = []
    for cohort_start in sorted(cohort_members.keys(), reverse=True):
        members = cohort_members[cohort_start]
        cohort_size = len(members)
        # Always include w0 (cohort start week, baseline).
        retention = {'w0': cohort_size}
        for week_n in range(1, weeks + 1):
            active = bucket[cohort_start].get(week_n, set())
            # Only count users who were members of the cohort.
            retention[f'w{week_n}'] = len(active & members)
        out.append({
            'cohort_week': _iso_week(cohort_start),
            'cohort_size': cohort_size,
            'retention': retention,
        })
    return out


class CohortRetentionView(APIView):
    """``GET /api/v1/analytics/cohorts/?weeks=12`` — admin-only."""
    permission_classes = [permissions.IsAuthenticated, IsAdminOrSuperuser]

    def get(self, request):
        try:
            weeks = int(request.query_params.get('weeks', '12'))
        except (TypeError, ValueError):
            weeks = 12
        weeks = max(2, min(weeks, 52))
        rows = build_cohort_retention(weeks=weeks)
        return Response({
            'cohort_size_weeks': weeks,
            'cohorts': rows,
            'count': len(rows),
        })
