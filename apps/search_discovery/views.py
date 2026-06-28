"""
Search & Discovery REST surface — thin views over services.py.
"""
from __future__ import annotations

from datetime import date as date_cls
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import (
    AttributeSchema, AutocompleteSuggestion, BestsellerBadge,
    EditorialCollection, EditorialSlot, EmailDigestRun,
    ExperimentAssignment, IntentSignal, NewArrivalEntry,
    ProductComparison, QueryParse, RegionalSurfacingRule,
    SearchClickLog, SearchDiscoveryEvent, SearchExperiment,
    SearchKpiSnapshot, SellerRankingSignal, TrendingScore,
    VerifiedBadge, VisualSearchLog, VoiceSearchLog, ZeroResultsLog,
)

User = get_user_model()


class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        u = getattr(request, 'user', None)
        return bool(u and u.is_authenticated and getattr(u, 'is_staff', False))


# ─── CH2 — Trending ───────────────────────────────────────────

class TrendingFeedView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({'trending': services.trending_feed(
            country=request.query_params.get('country', ''),
            limit=int(request.query_params.get('limit', 20)),
        )})


@api_view(['POST'])
@permission_classes([IsAdmin])
def trending_compute(request):
    score = services.compute_trending_score(
        product_id=request.data.get('product_id', ''),
        category_id=request.data.get('category_id', ''),
        country=request.data.get('country', ''),
    )
    return Response({'score': score.score,
                     'acceleration': score.acceleration}, status=201)


# ─── CH3 — Email digest ──────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def digest_generate(request):
    run = services.generate_email_digest(user=request.user)
    items = run.items.values('product_id', 'slot', 'reason')
    return Response({'run_id': str(run.id), 'status': run.status,
                     'items': list(items)}, status=201)


# ─── CH4 — Related searches ──────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def related_searches_view(request):
    return Response({'related': services.related_searches(
        request.query_params.get('q', ''),
        limit=int(request.query_params.get('limit', 8)),
    )})


@api_view(['POST'])
@permission_classes([IsAdmin])
def co_click_record(request):
    edge = services.record_co_click(
        query_a=request.data.get('query_a', ''),
        query_b=request.data.get('query_b', ''),
    )
    return Response({'edge_id': edge.pk}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def related_rebuild(request):
    n = services.rebuild_related_searches()
    return Response({'rows': n})


# ─── CH5 — Bestsellers ───────────────────────────────────────

class BestsellersView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = BestsellerBadge.objects.filter(is_active=True)
        cat = request.query_params.get('category_id')
        if cat:
            qs = qs.filter(category_id=cat)
        return Response(list(qs.order_by('category_id', 'rank').values(
            'product_id', 'category_id', 'country', 'rank', 'score',
        )[:100]))


@api_view(['POST'])
@permission_classes([IsAdmin])
def bestsellers_recompute(request):
    n = services.recompute_bestsellers(
        category_id=request.data.get('category_id', ''),
        country=request.data.get('country', ''),
    )
    return Response({'badges': n})


# ─── CH6 — Editorial ─────────────────────────────────────────

class EditorialCollectionView(generics.ListCreateAPIView):
    permission_classes = [AllowAny]

    def get_queryset(self):
        now = timezone.now()
        return EditorialCollection.objects.filter(
            status='live',
        )

    def list(self, request):
        return Response(list(self.get_queryset().values(
            'id', 'slug', 'title', 'subtitle', 'hero_image_key',
            'product_ids', 'view_count',
        )[:50]))

    def create(self, request):
        if not request.user.is_authenticated or not request.user.is_staff:
            return Response({'detail': 'staff only'}, status=403)
        obj = EditorialCollection.objects.create(
            slug=request.data.get('slug', '')[:120],
            title=request.data.get('title', '')[:200],
            subtitle=request.data.get('subtitle', '')[:255],
            product_ids=request.data.get('product_ids') or [],
            curator=request.user,
            status=request.data.get('status', 'draft'),
            live_from=request.data.get('live_from'),
            live_until=request.data.get('live_until'),
        )
        return Response({'collection_id': str(obj.id)}, status=201)


# ─── CH7 — Verified badges ───────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def badge_award(request):
    seller = get_object_or_404(User, pk=request.data.get('seller_id'))
    badge = services.award_badge(
        seller=seller,
        badge_type=request.data.get('badge_type', 'verified_seller'),
        eligibility_snapshot=request.data.get('eligibility_snapshot') or {},
    )
    return Response({'badge_id': badge.pk}, status=201)


@api_view(['POST'])
@permission_classes([IsAdmin])
def badge_integrity_run(request):
    return Response({'checked': services.run_badge_integrity_checks()})


# ─── CH8 — New arrivals ──────────────────────────────────────

class NewArrivalsView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        qs = NewArrivalEntry.objects.filter(
            gate_passed=True, expires_at__gt=timezone.now(),
        ).order_by('-freshness_score', '-quality_score')
        cat = request.query_params.get('category_id')
        if cat:
            qs = qs.filter(category_id=cat)
        return Response(list(qs.values(
            'product_id', 'category_id', 'quality_score',
            'freshness_score', 'listed_at',
        )[:50]))


@api_view(['POST'])
@permission_classes([IsAdmin])
def new_arrival_admit(request):
    entry = services.admit_new_arrival(
        product_id=request.data.get('product_id', ''),
        category_id=request.data.get('category_id', ''),
        title_length=int(request.data.get('title_length', 0)),
        image_count=int(request.data.get('image_count', 0)),
        has_description=bool(request.data.get('has_description', False)),
        seller_health=int(request.data.get('seller_health', 100)),
    )
    return Response({'gate_passed': entry.gate_passed,
                     'failures': entry.gate_failures,
                     'quality_score': entry.quality_score}, status=201)


# ─── CH9 — Regional boost ────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def regional_boost_compute(request):
    boost = services.regional_boost(
        country=request.data.get('country', ''),
        is_local_warehouse=bool(request.data.get('is_local_warehouse', False)),
        is_domestic_seller=bool(request.data.get('is_domestic_seller', False)),
        delivery_days=int(request.data.get('delivery_days', 30)),
    )
    return Response({'boost': boost})


# ─── CH10 — Sold count display ───────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def sold_count_display_view(request):
    return Response({'display': services.sold_count_display(
        sold_count=int(request.query_params.get('sold_count', 0)),
        country=request.query_params.get('country', ''),
    )})


# ─── CH11 — Comparison ──────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def comparison_build(request):
    user = request.user if request.user.is_authenticated else None
    cmp = services.build_comparison(
        product_specs=request.data.get('product_specs') or [],
        category_id=request.data.get('category_id', ''),
        user=user,
    )
    return Response({
        'comparison_id': str(cmp.id),
        'matrix': cmp.comparison_matrix,
        'differences': cmp.differences_highlighted,
    }, status=201)


# ─── CH12/13 — Voice + visual logs ──────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def voice_search_log(request):
    obj = VoiceSearchLog.objects.create(
        user=request.user,
        audio_duration_ms=int(request.data.get('audio_duration_ms', 0)),
        transcribed_text=request.data.get('transcribed_text', '')[:500],
        stt_confidence=float(request.data.get('stt_confidence', 0)),
        language=request.data.get('language', 'pt-AO'),
        results_count=int(request.data.get('results_count', 0)),
    )
    return Response({'log_id': obj.pk}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def visual_search_log(request):
    obj = VisualSearchLog.objects.create(
        user=request.user,
        image_key=request.data.get('image_key', '')[:255],
        detected_objects=request.data.get('detected_objects') or [],
        matched_product_ids=request.data.get('matched_product_ids') or [],
        top_match_confidence=float(request.data.get('top_match_confidence', 0)),
        results_count=int(request.data.get('results_count', 0)),
    )
    return Response({'log_id': obj.pk}, status=201)


# ─── CH16 — Autocomplete ─────────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def autocomplete_view(request):
    return Response({'suggestions': services.autocomplete(
        prefix=request.query_params.get('q', ''),
        language=request.query_params.get('language', 'pt-AO'),
        limit=int(request.query_params.get('limit', 8)),
    )})


@api_view(['POST'])
@permission_classes([IsAdmin])
def autocomplete_rebuild(request):
    return Response({'rows': services.rebuild_autocomplete(
        language=request.data.get('language', 'pt-AO'),
    )})


# ─── CH17 — Zero results ─────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def zero_results_handle(request):
    user = request.user if request.user.is_authenticated else None
    return Response(services.handle_zero_results(
        query=request.data.get('query', ''),
        user=user,
        language=request.data.get('language', 'pt-AO'),
        country=request.data.get('country', ''),
    ))


# ─── CH18 — Experiments ──────────────────────────────────────

class SearchExperimentView(generics.ListCreateAPIView):
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return SearchExperiment.objects.all()

    def list(self, request):
        return Response(list(self.get_queryset().values(
            'id', 'slug', 'name', 'status', 'traffic_pct',
            'primary_metric', 'started_at', 'result_summary',
        )))

    def create(self, request):
        obj = SearchExperiment.objects.create(
            slug=request.data.get('slug', '')[:80],
            name=request.data.get('name', '')[:160],
            hypothesis=request.data.get('hypothesis', ''),
            ranking_config_control=request.data.get('ranking_config_control') or {},
            ranking_config_variant=request.data.get('ranking_config_variant') or {},
            traffic_pct=int(request.data.get('traffic_pct', 50)),
            primary_metric=request.data.get('primary_metric', 'ctr'),
            status='running',
            started_at=timezone.now(),
        )
        return Response({'experiment_id': str(obj.id)}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def experiment_bucket(request):
    exp = get_object_or_404(SearchExperiment,
                              slug=request.data.get('slug', ''))
    bucket = services.assign_experiment_bucket(
        user=request.user, experiment=exp,
    )
    return Response({'bucket': bucket})


@api_view(['POST'])
@permission_classes([IsAdmin])
def experiment_analyse(request):
    exp = get_object_or_404(SearchExperiment,
                              pk=request.data.get('experiment_id'))
    return Response(services.analyse_experiment(exp))


# ─── CH19 — Intent signals ───────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def intent_record(request):
    obj = services.record_intent(
        user=request.user,
        session_id=request.data.get('session_id', ''),
        product_id=request.data.get('product_id', ''),
        kind=request.data.get('kind', 'dwell_long'),
        value=float(request.data.get('value', 0)),
    )
    return Response({'signal_id': obj.pk}, status=201)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def intent_score(request):
    return Response({'intent_score': services.intent_score_for(
        user=request.user,
        product_id=request.query_params.get('product_id', ''),
    )})


# ─── CH20 — Cross-category ───────────────────────────────────

@api_view(['GET'])
@permission_classes([AllowAny])
def complete_the_look_view(request):
    return Response({'suggestions': services.complete_the_look(
        category_id=request.query_params.get('category_id', ''),
        limit=int(request.query_params.get('limit', 4)),
    )})


@api_view(['POST'])
@permission_classes([IsAdmin])
def co_purchase_record(request):
    edge = services.record_co_purchase(
        source_category_id=request.data.get('source_category_id', ''),
        target_category_id=request.data.get('target_category_id', ''),
    )
    return Response({'edge_id': edge.pk}, status=201)


# ─── CH21 — Query understanding ──────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def query_parse(request):
    parse = services.parse_query(
        raw_query=request.data.get('query', ''),
        language=request.data.get('language', 'pt-AO'),
    )
    return Response({
        'normalised_query': parse.normalised_query,
        'entities': parse.detected_entities,
        'filters': parse.extracted_filters,
        'predicted_category_id': parse.predicted_category_id,
    })


# ─── CH22 — Seller ranking ───────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAdmin])
def seller_ranking_snapshot(request):
    seller = get_object_or_404(User, pk=request.data.get('seller_id'))
    obj = services.snapshot_seller_ranking(seller=seller)
    return Response({'composite_multiplier': obj.composite_multiplier},
                    status=201)


# ─── CH23 — Click logging ────────────────────────────────────

@api_view(['POST'])
@permission_classes([AllowAny])
def search_click_log(request):
    user = request.user if request.user.is_authenticated else None
    obj = services.log_search_interaction(
        query=request.data.get('query', ''),
        product_id=request.data.get('product_id', ''),
        position=int(request.data.get('position', 0)),
        action=request.data.get('action', 'click'),
        user=user,
        session_id=request.data.get('session_id', ''),
        page=int(request.data.get('page', 1)),
        experiment_bucket=request.data.get('experiment_bucket', ''),
    )
    return Response({'log_id': obj.pk}, status=201)


# ─── CH24 — KPI ──────────────────────────────────────────────

class SearchKpiView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        d_str = request.query_params.get('date')
        d = date_cls.fromisoformat(d_str) if d_str else timezone.now().date()
        snap = SearchKpiSnapshot.objects.filter(snapshot_date=d).first()
        if not snap:
            snap = services.snapshot_search_kpis(snapshot_date=d)
        return Response({
            'date': str(snap.snapshot_date),
            'total_searches': snap.total_searches,
            'zero_results_pct': snap.zero_results_pct,
            'search_ctr': snap.search_ctr,
            'search_to_cart_pct': snap.search_to_cart_pct,
            'search_to_purchase_pct': snap.search_to_purchase_pct,
            'avg_click_position': snap.avg_click_position,
            'voice_searches': snap.voice_searches,
            'visual_searches': snap.visual_searches,
            'comparison_sessions': snap.comparison_sessions,
            'digest_open_rate': snap.digest_open_rate,
            'active_experiments': snap.active_experiments,
        })
