"""
apps/loyalty/views.py

Two surfaces:

  user:  GET /loyalty/me/        — my tier + benefits + recent transactions
  admin: GET /loyalty/tiers/     — list tiers + benefits
         POST /loyalty/tiers/    — create tier
         POST /loyalty/admin/adjust/  — admin points adjustment
"""
from rest_framework import permissions
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Tier, TierBenefit, UserTier, PointsTransaction
from . import service


class MyLoyaltyView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        benefits = service.get_benefits(request.user)
        balance = int(request.user.loyalty_points or 0)
        recent = list(
            PointsTransaction.objects.filter(user=request.user)
            .order_by('-created_at')[:25]
            .values('delta', 'reason', 'balance_after', 'ref_type',
                    'ref_id', 'note', 'created_at')
        )
        return Response({
            'balance': balance,
            **benefits,
            'recent_transactions': recent,
        })


class TierListView(APIView):
    """Public listing of tiers + their benefits — useful for buyer-facing
    "how to reach Gold?" pages and for the admin tier configurator."""
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        tiers = list(Tier.objects.filter(is_active=True).order_by('rank'))
        out = []
        for t in tiers:
            benefits = list(t.benefits.filter(is_active=True).values('kind', 'value', 'description'))
            out.append({
                'code': t.code, 'name': t.name, 'rank': t.rank,
                'spend_threshold': str(t.spend_threshold),
                'points_multiplier': str(t.points_multiplier),
                'color': t.color, 'icon': t.icon,
                'benefits': [{'kind': b['kind'], 'value': str(b['value']),
                              'description': b['description']} for b in benefits],
            })
        return Response({'results': out})

    def post(self, request):
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({'error': 'admin_only'}, status=403)
        code = (request.data.get('code') or '').upper()
        if code not in {c for c, _ in Tier._meta.get_field('code').choices}:
            return Response({'error': 'bad_code'}, status=400)
        try:
            t = Tier.objects.create(
                code=code, rank=int(request.data['rank']),
                name=request.data.get('name', code.title()),
                spend_threshold=request.data['spend_threshold'],
                points_multiplier=request.data.get('points_multiplier', 1.0),
                color=request.data.get('color', ''),
                icon=request.data.get('icon', ''),
            )
        except Exception as e:
            return Response({'error': 'create_failed', 'detail': str(e)}, status=400)
        return Response({'id': t.id, 'code': t.code, 'rank': t.rank}, status=201)


class PointsAdjustView(APIView):
    """POST /loyalty/admin/adjust/  body: {user_id, delta, note}
    Admin manual adjustment — positive or negative. Always audited."""
    permission_classes = [permissions.IsAdminUser]

    def post(self, request):
        from django.contrib.auth import get_user_model
        try:
            uid = int(request.data['user_id'])
            delta = int(request.data['delta'])
        except (KeyError, ValueError, TypeError):
            return Response({'error': 'validation_error',
                             'detail': 'user_id + delta (int) required'}, status=400)
        if delta == 0:
            return Response({'error': 'zero_delta'}, status=400)
        u = get_user_model().objects.filter(pk=uid).first()
        if u is None:
            return Response({'error': 'user_not_found'}, status=404)
        try:
            tx = service.adjust(u, delta=delta,
                                 note=(request.data.get('note') or '')[:200],
                                 actor=request.user)
        except service.LoyaltyError as e:
            return Response({'error': 'loyalty_error', 'detail': str(e)}, status=400)
        return Response({
            'transaction_id': tx.id, 'delta': tx.delta,
            'balance_after': tx.balance_after,
        }, status=201)


class RecomputeMyTierView(APIView):
    """POST /loyalty/me/recompute/  — recompute current user's tier on demand.
    Useful after a buyer completes a big-ticket purchase and the beat task
    hasn't run yet."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        try:
            ut = service.recompute_tier(request.user)
        except Exception as e:
            return Response({'error': 'recompute_failed', 'detail': str(e)},
                            status=500)
        if ut is None:
            return Response({'tier': None})
        return Response({
            'tier': ut.tier.code, 'tier_name': ut.tier.name,
            'qualifying_spend': str(ut.qualifying_spend),
            'achieved_at': ut.achieved_at,
        })
