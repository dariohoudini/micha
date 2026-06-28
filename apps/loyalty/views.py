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


# ─── AliExpress 2025 CH 5 — Coins / Daily Check-In ─────────────────

from datetime import timedelta as _td
from django.utils import timezone as _tz
from .models import DailyCheckIn, CoinTaskCompletion


class DailyCheckInView(APIView):
    """GET — today's status. POST — claim today's reward."""
    permission_classes = [permissions.IsAuthenticated]

    def _streak(self, user):
        """Compute current streak by walking back from yesterday."""
        today = _tz.localdate()
        d = today - _td(days=1)
        streak = 0
        # Cheap: scan back up to 60 days. Beyond that we treat as 0.
        for _ in range(60):
            if DailyCheckIn.objects.filter(user=user, check_date=d).exists():
                streak += 1
                d -= _td(days=1)
            else:
                break
        return streak

    def get(self, request):
        u = request.user
        today = _tz.localdate()
        already = DailyCheckIn.objects.filter(user=u, check_date=today).first()
        streak = self._streak(u) + (1 if already else 0)
        next_reward = DailyCheckIn.reward_for_streak(streak if already else streak + 1)
        return Response({
            'already_checked_in': bool(already),
            'streak_day': streak,
            'today_coins': already.coins_awarded if already else 0,
            'next_reward': next_reward,
            'balance': u.loyalty_points,
            'last_7': [
                {
                    'date': (today - _td(days=i)).isoformat(),
                    'checked': DailyCheckIn.objects.filter(user=u, check_date=today - _td(days=i)).exists(),
                }
                for i in range(6, -1, -1)
            ],
        })

    def post(self, request):
        u = request.user
        today = _tz.localdate()
        if DailyCheckIn.objects.filter(user=u, check_date=today).exists():
            return Response({'error': 'already_checked_in', 'detail': 'Already checked in today.'}, status=400)
        streak = self._streak(u) + 1
        coins = DailyCheckIn.reward_for_streak(streak)
        DailyCheckIn.objects.create(user=u, check_date=today, coins_awarded=coins, streak_day=streak)
        u.add_loyalty_points(coins)
        # User Process Flow §20.8 telemetry.
        try:
            from apps.analytics.models import UserEvent
            UserEvent.objects.create(user=u, event='coins.check_in',
                properties={'streak': streak, 'coins': coins})
        except Exception:
            pass
        return Response({'coins_awarded': coins, 'streak_day': streak, 'balance': u.loyalty_points}, status=201)


class CoinTaskCompleteView(APIView):
    """POST /loyalty/coins/tasks/ — declare a task complete.

    The FE calls this when a user performs a coin-earning action.
    Per-task daily caps are enforced here to prevent abuse.
    """
    permission_classes = [permissions.IsAuthenticated]
    # Spec §5.3 daily caps and reward amounts.
    REWARDS = {
        'browse_3m':     (3, 1),    # max 1 / day
        'add_wishlist':  (2, 5),
        'share_product': (3, 3),
        'follow_store':  (1, 5),
        'lucky_forest':  (10, 1),
        'coins_park':    (15, 3),
        'merge_boss':    (5, 5),
    }

    def post(self, request):
        u = request.user
        task = (request.data.get('task') or '').strip()
        if task not in self.REWARDS:
            return Response({'error': 'invalid_task'}, status=400)
        coins, daily_cap = self.REWARDS[task]
        since = _tz.now() - _td(hours=24)
        done_today = CoinTaskCompletion.objects.filter(user=u, task=task, completed_at__gte=since).count()
        if done_today >= daily_cap:
            return Response({'error': 'daily_cap', 'detail': 'Limite diário atingido.'}, status=400)
        CoinTaskCompletion.objects.create(user=u, task=task, coins_awarded=coins)
        u.add_loyalty_points(coins)
        try:
            from apps.analytics.models import UserEvent
            UserEvent.objects.create(user=u, event='coins.task_done',
                properties={'task': task, 'coins': coins})
        except Exception:
            pass
        return Response({'coins_awarded': coins, 'balance': u.loyalty_points, 'remaining_today': daily_cap - done_today - 1})


class TodayCoinTasksView(APIView):
    """GET /loyalty/coins/tasks/ — today's available tasks + my progress."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        u = request.user
        since = _tz.now() - _td(hours=24)
        out = []
        for task, (coins, cap) in CoinTaskCompleteView.REWARDS.items():
            done = CoinTaskCompletion.objects.filter(user=u, task=task, completed_at__gte=since).count()
            out.append({
                'task': task, 'coins_per': coins,
                'daily_cap': cap, 'done_today': done,
                'remaining': max(0, cap - done),
            })
        return Response({'tasks': out, 'balance': u.loyalty_points})
