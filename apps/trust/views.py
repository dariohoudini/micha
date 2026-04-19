"""
apps/trust/views.py
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser


class SellerTrustScoreView(APIView):
    """GET /api/trust/seller/<seller_id>/ — Public trust score for a seller."""
    permission_classes = [IsAuthenticated]

    def get(self, request, seller_id):
        from .models import SellerTrustScore
        try:
            score = SellerTrustScore.objects.get(seller__id=seller_id)
            if not score.score_is_public:
                return Response({
                    'public': False,
                    'message': 'Vendedor ainda em avaliação (poucos pedidos)',
                    'badge': {'level': 'new', 'label': 'Em avaliação', 'color': '#9E9E9E'},
                })
            return Response(score.get_score_breakdown())
        except SellerTrustScore.DoesNotExist:
            return Response({'public': False, 'badge': {'level': 'new', 'label': 'Em avaliação'}})


class MyTrustScoreView(APIView):
    """GET /api/trust/me/ — Seller's own trust score with full details."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import SellerTrustScore, TrustEvent
        try:
            score = SellerTrustScore.objects.get(seller=request.user)
            breakdown = score.get_score_breakdown()
            # Add recent events for seller to understand score changes
            recent_events = TrustEvent.objects.filter(
                seller=request.user
            ).order_by('-created_at')[:10].values(
                'event_label', 'score_change', 'score_after', 'created_at'
            )
            breakdown['recent_events'] = list(recent_events)
            return Response(breakdown)
        except SellerTrustScore.DoesNotExist:
            return Response({'overall_score': 0, 'badge': {'level': 'new'}})


class FraudAssessmentView(APIView):
    """POST /api/trust/admin/fraud-assess/ — Admin fraud assessment."""
    permission_classes = [IsAdminUser]

    def post(self, request):
        from .services import FraudDetectionService
        from django.contrib.auth import get_user_model

        user_id = request.data.get('user_id')
        assess_type = request.data.get('type', 'seller')

        User = get_user_model()
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({'error': 'User not found'}, status=404)

        if assess_type == 'seller':
            result = FraudDetectionService.assess_seller_risk(user)
        else:
            result = FraudDetectionService.assess_buyer_risk(user)

        return Response(result)


class TrustLeaderboardView(APIView):
    """GET /api/trust/leaderboard/ — Top trusted sellers."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import SellerTrustScore
        top = SellerTrustScore.objects.filter(
            score_is_public=True,
            overall_score__gte=60,
        ).order_by('-overall_score').select_related('seller')[:20]

        return Response([{
            'seller_id': str(s.seller.id),
            'seller_name': getattr(s.seller, 'store_name', s.seller.email),
            'overall_score': s.overall_score,
            'badge': {'level': s.badge_level, 'label': s.badge_label, 'color': s.badge_color},
            'total_orders': s.total_orders,
            'avg_rating': s.avg_rating,
        } for s in top])
