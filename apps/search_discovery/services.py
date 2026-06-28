"""
Search & Discovery — domain services.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date as date_cls
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models as django_models
from django.db import transaction
from django.utils import timezone

from .models import (
    AttributeSchema, AutocompleteSuggestion, BadgeIntegrityCheck,
    BestsellerBadge, CoClickEdge, CrossCategoryAffinity,
    EditorialCollection, EditorialSlot, EmailDigestItem,
    EmailDigestRun, ExperimentAssignment, FlashDealDiscoverySnapshot,
    IntentSignal, NewArrivalEntry, ProductComparison, QueryParse,
    RegionalSurfacingRule, RelatedSearch, SearchClickLog,
    SearchDiscoveryEvent, SearchExperiment, SearchKpiSnapshot,
    SellerRankingSignal, SoldCountDisplayRule, TrendingScore,
    VerifiedBadge, VisualSearchLog, VoiceSearchLog, ZeroResultsLog,
)

User = get_user_model()
log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════
# CH2 — Trending velocity
# ═══════════════════════════════════════════════════════════════════

def compute_trending_score(*, product_id: str,
                              category_id: str = '',
                              country: str = '') -> TrendingScore:
    """CH2.1 — score = acceleration × log(volume) × conversion.
    Pulls purchase counts from apps.orders when present."""
    import math
    now = timezone.now()
    v1h = v24h = v7d = 0.0
    views_24h = 0
    try:
        from apps.orders.models import OrderItem
        base_qs = OrderItem.objects.filter(product__id=product_id)
        v1h = base_qs.filter(created_at__gte=now - timedelta(hours=1)).count()
        v24h = base_qs.filter(created_at__gte=now - timedelta(hours=24)).count()
        week = base_qs.filter(
            created_at__gte=now - timedelta(days=7),
            created_at__lt=now - timedelta(hours=24),
        ).count()
        v7d = week / (6 * 24) if week else 0  # hourly baseline
    except Exception:
        pass
    try:
        from apps.recommendations.models import ProductInteraction
        views_24h = ProductInteraction.objects.filter(
            product__id=product_id,
            created_at__gte=now - timedelta(hours=24),
        ).count()
    except Exception:
        pass
    acceleration = (v1h / v7d) if v7d > 0 else (v1h * 2.0)
    conversion = (v24h / views_24h) if views_24h else 0
    score = acceleration * math.log1p(v24h) * (1 + conversion)
    return TrendingScore.objects.create(
        product_id=product_id[:64], category_id=category_id[:64],
        country=country[:2],
        velocity_1h=v1h, velocity_24h=v24h, velocity_7d_baseline=v7d,
        acceleration=acceleration,
        view_to_purchase_rate=conversion,
        score=round(score, 4),
    )


def trending_feed(*, country: str = '', limit: int = 20) -> list[dict]:
    cutoff = timezone.now() - timedelta(minutes=30)
    qs = TrendingScore.objects.filter(computed_at__gte=cutoff)
    if country:
        qs = qs.filter(django_models.Q(country=country.upper()) | django_models.Q(country=''))
    # Latest snapshot per product.
    seen = set()
    out = []
    for t in qs.order_by('-score', '-computed_at'):
        if t.product_id in seen:
            continue
        seen.add(t.product_id)
        out.append({'product_id': t.product_id, 'score': t.score,
                     'acceleration': t.acceleration})
        if len(out) >= limit:
            break
    return out


# ═══════════════════════════════════════════════════════════════════
# CH3 — Weekly digest
# ═══════════════════════════════════════════════════════════════════

def generate_email_digest(*, user, week_start: date_cls = None,
                             max_items: int = 8) -> EmailDigestRun:
    """Builds the personalised weekly digest. Idempotent on
    (user, week_start)."""
    if week_start is None:
        today = timezone.now().date()
        week_start = today - timedelta(days=today.weekday())
    existing = EmailDigestRun.objects.filter(
        user=user, week_start=week_start,
    ).first()
    if existing:
        return existing

    items = []
    # 1) Wishlist price drops.
    try:
        from apps.recommendations.models import PriceAlert
        for alert in PriceAlert.objects.filter(user=user)[:2]:
            items.append((str(alert.product_id), 'price_dropped'))
    except Exception:
        pass
    # 2) Trending in affinity categories.
    for t in trending_feed(limit=3):
        items.append((t['product_id'], 'trending'))
    # 3) Recently viewed similar.
    try:
        # NOTE: RecentlyViewed lives in apps.search, NOT
        # apps.recommendations — importing from the wrong app fails
        # silently inside this try/except and the digest loses its
        # recently-viewed section. Keep this import path.
        from apps.search.models import RecentlyViewed
        for rv in RecentlyViewed.objects.filter(user=user).order_by('-viewed_at')[:3]:
            items.append((str(rv.product_id), 'viewed_similar'))
    except Exception:
        pass

    # Dedup preserving order.
    seen = set()
    unique = []
    for pid, reason in items:
        if pid in seen:
            continue
        seen.add(pid)
        unique.append((pid, reason))
    unique = unique[:max_items]

    run = EmailDigestRun.objects.create(
        user=user, week_start=week_start,
        item_count=len(unique),
        status='generated' if unique else 'skipped',
        personalisation_basis={'sources': ['price_alerts', 'trending',
                                            'recently_viewed']},
    )
    for i, (pid, reason) in enumerate(unique):
        EmailDigestItem.objects.create(
            run=run, product_id=pid, slot=i + 1, reason=reason,
        )
    return run


# ═══════════════════════════════════════════════════════════════════
# CH4 — Co-click graph
# ═══════════════════════════════════════════════════════════════════

def record_co_click(*, query_a: str, query_b: str) -> CoClickEdge:
    a, b = sorted([query_a.strip().lower()[:200], query_b.strip().lower()[:200]])
    edge, _ = CoClickEdge.objects.get_or_create(query_a=a, query_b=b)
    CoClickEdge.objects.filter(pk=edge.pk).update(
        co_click_count=django_models.F('co_click_count') + 1,
    )
    return edge


def rebuild_related_searches(*, min_strength: float = 0.1,
                                 top_n: int = 8) -> int:
    """Materialise the top-N related queries per source query from
    the co-click graph."""
    # Normalise strengths.
    edges = list(CoClickEdge.objects.all())
    if not edges:
        return 0
    max_count = max(e.co_click_count for e in edges) or 1
    by_source: dict[str, list] = {}
    for e in edges:
        strength = e.co_click_count / max_count
        e.strength = strength
        e.save(update_fields=['strength'])
        if strength < min_strength:
            continue
        by_source.setdefault(e.query_a, []).append((strength, e.query_b))
        by_source.setdefault(e.query_b, []).append((strength, e.query_a))
    n = 0
    for source, pairs in by_source.items():
        pairs.sort(reverse=True)
        RelatedSearch.objects.filter(source_query=source).delete()
        for rank, (strength, related) in enumerate(pairs[:top_n], start=1):
            RelatedSearch.objects.create(
                source_query=source, related_query=related,
                rank=rank, strength=strength,
            )
            n += 1
    return n


def related_searches(query: str, *, limit: int = 8) -> list[str]:
    return list(
        RelatedSearch.objects.filter(
            source_query=query.strip().lower(),
        ).order_by('rank').values_list('related_query', flat=True)[:limit]
    )


# ═══════════════════════════════════════════════════════════════════
# CH5 — Bestseller badges
# ═══════════════════════════════════════════════════════════════════

def recompute_bestsellers(*, category_id: str, country: str = '',
                             top_n: int = 3) -> int:
    """CH5.1 — rank products in the category by 30-day sales and
    award/refresh the top-N badges."""
    sales: dict[str, int] = {}
    try:
        from apps.orders.models import OrderItem
        cutoff = timezone.now() - timedelta(days=30)
        rows = (
            OrderItem.objects.filter(
                created_at__gte=cutoff,
                product__category__name=category_id,
            ).values('product__id')
            .annotate(c=django_models.Count('id'))
            .order_by('-c')[:top_n]
        )
        for r in rows:
            sales[str(r['product__id'])] = r['c']
    except Exception:
        pass

    # Revoke badges for products no longer in top N.
    active = BestsellerBadge.objects.filter(
        category_id=category_id, country=country.upper(), is_active=True,
    )
    for badge in active:
        if badge.product_id not in sales:
            badge.is_active = False
            badge.revoked_at = timezone.now()
            badge.save(update_fields=['is_active', 'revoked_at'])

    n = 0
    for rank, (pid, count) in enumerate(sorted(
        sales.items(), key=lambda t: t[1], reverse=True,
    ), start=1):
        BestsellerBadge.objects.update_or_create(
            category_id=category_id[:64], country=country.upper()[:2],
            rank=rank,
            defaults={'product_id': pid, 'score': count,
                       'is_active': True, 'revoked_at': None},
        )
        n += 1
    return n


# ═══════════════════════════════════════════════════════════════════
# CH7 — Verified badges + integrity
# ═══════════════════════════════════════════════════════════════════

def award_badge(*, seller, badge_type: str,
                  eligibility_snapshot: dict = None) -> VerifiedBadge:
    obj, _ = VerifiedBadge.objects.update_or_create(
        seller=seller, badge_type=badge_type,
        defaults={'eligibility_snapshot': eligibility_snapshot or {},
                  'is_active': True, 'revoked_at': None,
                  'revoke_reason': ''},
    )
    SearchDiscoveryEvent.log(kind='badge.awarded', user=seller,
                               payload={'badge_type': badge_type})
    return obj


def run_badge_integrity_checks() -> int:
    """CH7.2 — re-verify every active badge holder. Dev heuristic:
    pull seller tier from seller_onboarding when available; revoke
    if 'standard' for top_rated badges."""
    n = 0
    for badge in VerifiedBadge.objects.filter(is_active=True).select_related('seller'):
        still_eligible = True
        snapshot = {}
        try:
            from apps.seller_onboarding.models import SellerTierState
            tier = SellerTierState.objects.filter(seller=badge.seller).first()
            snapshot['tier'] = tier.current_tier if tier else 'unknown'
            if badge.badge_type == 'top_rated' and (
                not tier or tier.current_tier in ('standard', 'bronze')
            ):
                still_eligible = False
        except Exception:
            pass
        action = 'none'
        if not still_eligible:
            badge.is_active = False
            badge.revoked_at = timezone.now()
            badge.revoke_reason = 'integrity_check_failed'
            badge.save(update_fields=['is_active', 'revoked_at',
                                        'revoke_reason'])
            action = 'revoked'
        BadgeIntegrityCheck.objects.create(
            badge=badge, still_eligible=still_eligible,
            metrics_snapshot=snapshot, action_taken=action,
        )
        n += 1
    return n


# ═══════════════════════════════════════════════════════════════════
# CH8 — New arrivals quality gate
# ═══════════════════════════════════════════════════════════════════

def admit_new_arrival(*, product_id: str, category_id: str = '',
                         listed_at=None,
                         title_length: int = 0,
                         image_count: int = 0,
                         has_description: bool = False,
                         seller_health: int = 100) -> NewArrivalEntry:
    """CH8.1 — quality gate: 4 checks; failures recorded so the
    seller console can show why a listing didn't make the feed."""
    failures = []
    if title_length < 20:
        failures.append('TITLE_TOO_SHORT')
    if image_count < 3:
        failures.append('TOO_FEW_IMAGES')
    if not has_description:
        failures.append('NO_DESCRIPTION')
    if seller_health < 60:
        failures.append('SELLER_HEALTH_LOW')
    passed = not failures
    quality = max(0.0, 1.0 - len(failures) * 0.25)
    listed_at = listed_at or timezone.now()
    obj, _ = NewArrivalEntry.objects.update_or_create(
        product_id=product_id[:64],
        defaults={
            'category_id': category_id[:64],
            'quality_score': quality, 'gate_passed': passed,
            'gate_failures': failures,
            'freshness_score': 1.0,
            'listed_at': listed_at,
            'expires_at': listed_at + timedelta(days=14),
        },
    )
    return obj


def decay_new_arrivals() -> int:
    """CH8.2 — freshness decays linearly to 0 over 14 days."""
    now = timezone.now()
    n = 0
    for entry in NewArrivalEntry.objects.filter(gate_passed=True):
        age_days = (now - entry.listed_at).days
        fresh = max(0.0, 1.0 - age_days / 14.0)
        if abs(fresh - entry.freshness_score) > 0.01:
            entry.freshness_score = fresh
            entry.save(update_fields=['freshness_score'])
            n += 1
    return n


# ═══════════════════════════════════════════════════════════════════
# CH9 — Regional surfacing
# ═══════════════════════════════════════════════════════════════════

def regional_boost(*, country: str, is_local_warehouse: bool,
                     is_domestic_seller: bool,
                     delivery_days: int) -> float:
    rule = RegionalSurfacingRule.objects.filter(
        country=country.upper(), is_active=True,
    ).first()
    if not rule:
        return 1.0
    boost = 1.0
    if is_local_warehouse:
        boost *= rule.local_warehouse_boost
    if is_domestic_seller:
        boost *= rule.domestic_seller_boost
    if delivery_days <= rule.fast_delivery_days_threshold:
        boost *= rule.fast_delivery_boost
    return round(boost, 4)


# ═══════════════════════════════════════════════════════════════════
# CH10 — Sold count display
# ═══════════════════════════════════════════════════════════════════

def sold_count_display(*, sold_count: int, country: str = '') -> str:
    rule = (
        SoldCountDisplayRule.objects.filter(
            country=country.upper(), is_active=True,
        ).first()
        or SoldCountDisplayRule.objects.filter(country='', is_active=True).first()
    )
    if not rule:
        # Default behaviour.
        if sold_count < 10:
            return ''
        if sold_count >= 10000:
            return '10K+ vendidos'
        if sold_count >= 1000:
            return f'{sold_count // 1000}K+ vendidos'
        return f'{sold_count} vendidos'
    if sold_count < rule.min_display:
        return ''
    for band in sorted(rule.bands or [], key=lambda b: b.get('min', 0), reverse=True):
        if sold_count >= band.get('min', 0):
            return f'{band.get("label", "")} vendidos'
    return f'{sold_count} vendidos'


# ═══════════════════════════════════════════════════════════════════
# CH11 — Product comparison
# ═══════════════════════════════════════════════════════════════════

def normalise_attribute(*, category_id: str, raw_key: str) -> str | None:
    """Map a seller's free-text attribute name to the canonical key
    via the synonyms table."""
    raw = raw_key.strip().lower()
    for schema in AttributeSchema.objects.filter(category_id=category_id):
        if raw == schema.attribute_key.lower():
            return schema.attribute_key
        if raw in [str(s).lower() for s in (schema.synonyms or [])]:
            return schema.attribute_key
    return None


def build_comparison(*, product_specs: list[dict],
                       category_id: str = '',
                       user=None) -> ProductComparison:
    """`product_specs` shape:
       [{product_id, attributes: {raw_key: value, ...}}, ...]
       Builds the normalised matrix + difference highlights."""
    matrix: dict[str, dict[str, str]] = {}
    for spec in product_specs:
        pid = str(spec.get('product_id', ''))
        for raw_key, value in (spec.get('attributes') or {}).items():
            canonical = normalise_attribute(
                category_id=category_id, raw_key=raw_key,
            ) or raw_key.strip().lower()
            matrix.setdefault(canonical, {})[pid] = str(value)

    # Difference highlighting — attribute differs across products.
    differences = []
    pids = [str(s.get('product_id', '')) for s in product_specs]
    for attr, values in matrix.items():
        observed = {values.get(p, '—') for p in pids}
        if len(observed) > 1:
            differences.append(attr)

    return ProductComparison.objects.create(
        user=user, product_ids=pids, category_id=category_id[:64],
        comparison_matrix=matrix,
        differences_highlighted=differences,
    )


# ═══════════════════════════════════════════════════════════════════
# CH16 — Autocomplete
# ═══════════════════════════════════════════════════════════════════

def autocomplete(*, prefix: str, language: str = 'pt-AO',
                   limit: int = 8) -> list[dict]:
    qs = AutocompleteSuggestion.objects.filter(
        prefix=prefix.strip().lower()[:60],
        language=language, is_active=True,
    ).order_by('rank')[:limit]
    return [{'suggestion': s.suggestion, 'source': s.source}
             for s in qs]


def rebuild_autocomplete(*, language: str = 'pt-AO',
                            max_prefix_len: int = 12,
                            top_n: int = 8) -> int:
    """Nightly job: pull from search history + write per-prefix rows."""
    query_counts: dict[str, int] = {}
    try:
        from apps.search.models import SearchHistory
        rows = (
            SearchHistory.objects.values('query')
            .annotate(c=django_models.Count('id'))
            .order_by('-c')[:2000]
        )
        for r in rows:
            q = (r['query'] or '').strip().lower()
            if q:
                query_counts[q] = r['c']
    except Exception:
        pass
    if not query_counts:
        return 0
    by_prefix: dict[str, list] = {}
    for q, c in query_counts.items():
        for ln in range(1, min(len(q), max_prefix_len) + 1):
            by_prefix.setdefault(q[:ln], []).append((c, q))
    n = 0
    for prefix, candidates in by_prefix.items():
        candidates.sort(reverse=True)
        AutocompleteSuggestion.objects.filter(
            prefix=prefix, language=language, source='organic',
        ).delete()
        for rank, (count, q) in enumerate(candidates[:top_n], start=1):
            AutocompleteSuggestion.objects.update_or_create(
                prefix=prefix, rank=rank, language=language,
                defaults={'suggestion': q, 'source': 'organic',
                           'search_count': count, 'is_active': True},
            )
            n += 1
    return n


# ═══════════════════════════════════════════════════════════════════
# CH17 — Zero results handling
# ═══════════════════════════════════════════════════════════════════

def handle_zero_results(*, query: str, user=None,
                           language: str = 'pt-AO',
                           country: str = '') -> dict:
    """Try fallbacks in order: spell-correct → broaden → category
    suggestion. Logs the outcome either way."""
    fallback = 'none'
    fallback_count = 0
    suggestions = []

    # 1) Broaden: drop the last token.
    tokens = query.strip().split()
    if len(tokens) > 1:
        broadened = ' '.join(tokens[:-1])
        suggestions.append({'kind': 'broadened', 'query': broadened})
        fallback = 'broadened'
        fallback_count = 1
    # 2) Related searches from the co-click graph.
    related = related_searches(query, limit=3)
    if related:
        for r in related:
            suggestions.append({'kind': 'related', 'query': r})
        if fallback == 'none':
            fallback = 'synonym_expand'
        fallback_count += len(related)

    ZeroResultsLog.objects.create(
        query=query[:200], user=user, language=language[:10],
        country=country[:2], fallback_strategy=fallback,
        fallback_results_count=fallback_count,
    )
    return {'fallback_strategy': fallback, 'suggestions': suggestions}


# ═══════════════════════════════════════════════════════════════════
# CH18 — Search experiments
# ═══════════════════════════════════════════════════════════════════

def assign_experiment_bucket(*, user, experiment: SearchExperiment) -> str:
    """Deterministic per-(user, experiment) hash assignment."""
    existing = ExperimentAssignment.objects.filter(
        experiment=experiment, user=user,
    ).first()
    if existing:
        return existing.bucket
    h = hashlib.sha256(f'{user.pk}:{experiment.pk}'.encode()).hexdigest()
    bucket = 'variant' if (int(h[:8], 16) % 100) < experiment.traffic_pct else 'control'
    ExperimentAssignment.objects.create(
        experiment=experiment, user=user, bucket=bucket,
    )
    return bucket


def analyse_experiment(experiment: SearchExperiment) -> dict:
    """Compute CTR per bucket from the click log."""
    out = {}
    for bucket in ('control', 'variant'):
        impressions = SearchClickLog.objects.filter(
            experiment_bucket=bucket, action='impression',
            occurred_at__gte=experiment.started_at or experiment.created_at,
        ).count()
        clicks = SearchClickLog.objects.filter(
            experiment_bucket=bucket, action='click',
            occurred_at__gte=experiment.started_at or experiment.created_at,
        ).count()
        out[bucket] = {
            'impressions': impressions, 'clicks': clicks,
            'ctr': (clicks / impressions) if impressions else 0,
        }
    experiment.result_summary = out
    experiment.save(update_fields=['result_summary'])
    return out


# ═══════════════════════════════════════════════════════════════════
# CH19 — Intent signals
# ═══════════════════════════════════════════════════════════════════

def record_intent(*, user=None, session_id: str = '',
                    product_id: str, kind: str,
                    value: float = 0) -> IntentSignal:
    return IntentSignal.objects.create(
        user=user, session_id=session_id[:64],
        product_id=product_id[:64], kind=kind, value=value,
    )


def intent_score_for(*, user, product_id: str) -> float:
    """Aggregate intent signals into a 0-1 purchase-intent estimate."""
    weights = {
        'dwell_long': 0.15, 'image_zoom': 0.1, 'spec_expand': 0.1,
        'review_read': 0.15, 'size_check': 0.2,
        'shipping_check': 0.2, 'share': 0.1,
        're_visit': 0.25, 'cart_hesitation': 0.3,
    }
    signals = IntentSignal.objects.filter(
        user=user, product_id=product_id,
        occurred_at__gte=timezone.now() - timedelta(days=7),
    )
    score = 0.0
    for s in signals:
        score += weights.get(s.kind, 0.05)
    return min(1.0, round(score, 3))


# ═══════════════════════════════════════════════════════════════════
# CH20 — Cross-category affinity
# ═══════════════════════════════════════════════════════════════════

def record_co_purchase(*, source_category_id: str,
                          target_category_id: str) -> CrossCategoryAffinity:
    edge, _ = CrossCategoryAffinity.objects.get_or_create(
        source_category_id=source_category_id[:64],
        target_category_id=target_category_id[:64],
    )
    CrossCategoryAffinity.objects.filter(pk=edge.pk).update(
        co_purchase_count=django_models.F('co_purchase_count') + 1,
    )
    return edge


def complete_the_look(*, category_id: str, limit: int = 4) -> list[dict]:
    qs = CrossCategoryAffinity.objects.filter(
        source_category_id=category_id,
    ).order_by('-co_purchase_count')[:limit]
    return [{'category_id': e.target_category_id,
              'co_purchase_count': e.co_purchase_count}
             for e in qs]


# ═══════════════════════════════════════════════════════════════════
# CH21 — Query understanding
# ═══════════════════════════════════════════════════════════════════

# Tiny dev-time entity lexicon. Production swaps a semantic parser.
_COLOR_WORDS = {'preto', 'branco', 'azul', 'vermelho', 'verde',
                 'rosa', 'black', 'white', 'blue', 'red', 'green'}
_SIZE_RE = re.compile(r'\b(x{0,2}[sml]|\d{2,3}(?:cm|mm|gb|tb|ml|l))\b', re.I)
_PRICE_RE = re.compile(r'(?:under|below|menos de|até)\s*(\d+)', re.I)
_BRAND_HINTS = {'samsung', 'xiaomi', 'apple', 'nike', 'adidas', 'huawei'}


def parse_query(*, raw_query: str, language: str = 'pt-AO') -> QueryParse:
    norm = re.sub(r'\s+', ' ', raw_query.strip().lower())[:200]
    qh = hashlib.sha256(f'{language}|{norm}'.encode()).hexdigest()
    existing = QueryParse.objects.filter(query_hash=qh).first()
    if existing:
        return existing
    tokens = set(norm.split())
    entities: dict = {}
    colors = tokens & _COLOR_WORDS
    if colors:
        entities['color'] = sorted(colors)
    sizes = _SIZE_RE.findall(norm)
    if sizes:
        entities['size'] = sizes
    brands = tokens & _BRAND_HINTS
    if brands:
        entities['brand'] = sorted(brands)
    m = _PRICE_RE.search(norm)
    filters = {}
    if m:
        filters['max_price'] = int(m.group(1))
    return QueryParse.objects.create(
        query_hash=qh, raw_query=raw_query[:200],
        normalised_query=norm,
        detected_entities=entities,
        extracted_filters=filters,
        language=language[:10],
    )


# ═══════════════════════════════════════════════════════════════════
# CH22 — Seller ranking signal
# ═══════════════════════════════════════════════════════════════════

def snapshot_seller_ranking(*, seller,
                                snapshot_date: date_cls = None) -> SellerRankingSignal:
    if snapshot_date is None:
        snapshot_date = timezone.now().date()
    fulfilment = service = quality = trust = 0.7
    try:
        from apps.seller_onboarding.models import SellerHealthScore
        hs = SellerHealthScore.objects.filter(
            seller=seller,
        ).order_by('-snapshot_date').first()
        if hs:
            quality = hs.score / 100.0
    except Exception:
        pass
    try:
        from apps.trust.models import SellerTrustScore
        ts = SellerTrustScore.objects.filter(seller=seller).first()
        if ts and hasattr(ts, 'score'):
            trust = float(ts.score) / 100.0
    except Exception:
        pass
    composite = round(
        0.3 * fulfilment + 0.2 * service + 0.25 * quality + 0.25 * trust,
        4,
    )
    # Multiplier band 0.5 - 1.5.
    multiplier = round(0.5 + composite, 4)
    obj, _ = SellerRankingSignal.objects.update_or_create(
        seller=seller, snapshot_date=snapshot_date,
        defaults={
            'fulfilment_score': fulfilment, 'service_score': service,
            'quality_score': quality, 'trust_score': trust,
            'composite_multiplier': multiplier,
        },
    )
    return obj


# ═══════════════════════════════════════════════════════════════════
# CH23 — Click logging
# ═══════════════════════════════════════════════════════════════════

def log_search_interaction(*, query: str, product_id: str,
                               position: int, action: str = 'click',
                               user=None, session_id: str = '',
                               page: int = 1,
                               experiment_bucket: str = '') -> SearchClickLog:
    return SearchClickLog.objects.create(
        query=query[:200].strip().lower(), user=user,
        session_id=session_id[:64],
        product_id=product_id[:64], position=position,
        page=page, action=action,
        experiment_bucket=experiment_bucket[:8],
    )


# ═══════════════════════════════════════════════════════════════════
# CH24 — KPI snapshot
# ═══════════════════════════════════════════════════════════════════

def snapshot_search_kpis(snapshot_date=None) -> SearchKpiSnapshot:
    if snapshot_date is None:
        snapshot_date = timezone.now().date()
    start = timezone.make_aware(
        timezone.datetime.combine(snapshot_date, timezone.datetime.min.time())
    )
    end = start + timedelta(days=1)

    impressions = SearchClickLog.objects.filter(
        occurred_at__gte=start, occurred_at__lt=end, action='impression',
    ).count()
    clicks = SearchClickLog.objects.filter(
        occurred_at__gte=start, occurred_at__lt=end, action='click',
    ).count()
    carts = SearchClickLog.objects.filter(
        occurred_at__gte=start, occurred_at__lt=end, action='add_to_cart',
    ).count()
    purchases = SearchClickLog.objects.filter(
        occurred_at__gte=start, occurred_at__lt=end, action='purchase',
    ).count()
    total_searches = 0
    try:
        from apps.search.models import SearchHistory
        total_searches = SearchHistory.objects.filter(
            created_at__gte=start, created_at__lt=end,
        ).count()
    except Exception:
        total_searches = impressions

    zero = ZeroResultsLog.objects.filter(
        occurred_at__gte=start, occurred_at__lt=end,
    ).count()
    voice = VoiceSearchLog.objects.filter(
        occurred_at__gte=start, occurred_at__lt=end,
    ).count()
    visual = VisualSearchLog.objects.filter(
        occurred_at__gte=start, occurred_at__lt=end,
    ).count()
    comparisons = ProductComparison.objects.filter(
        created_at__gte=start, created_at__lt=end,
    ).count()
    digests = EmailDigestRun.objects.filter(week_start__gte=snapshot_date - timedelta(days=7))
    digest_sent = digests.filter(status='sent').count() or 1
    digest_opened = digests.filter(opened_at__isnull=False).count()
    digest_clicked = digests.filter(clicked_at__isnull=False).count()
    active_exp = SearchExperiment.objects.filter(status='running').count()

    # Avg click position.
    pos_agg = SearchClickLog.objects.filter(
        occurred_at__gte=start, occurred_at__lt=end, action='click',
    ).aggregate(a=django_models.Avg('position'))
    avg_pos = pos_agg['a'] or 0

    obj, _ = SearchKpiSnapshot.objects.update_or_create(
        snapshot_date=snapshot_date,
        defaults={
            'total_searches': total_searches,
            'zero_results_pct': (zero / total_searches * 100) if total_searches else 0,
            'search_ctr': (clicks / impressions * 100) if impressions else 0,
            'search_to_cart_pct': (carts / impressions * 100) if impressions else 0,
            'search_to_purchase_pct': (purchases / impressions * 100) if impressions else 0,
            'avg_click_position': avg_pos,
            'voice_searches': voice,
            'visual_searches': visual,
            'comparison_sessions': comparisons,
            'digest_open_rate': digest_opened / digest_sent * 100,
            'digest_click_rate': digest_clicked / digest_sent * 100,
            'active_experiments': active_exp,
        },
    )
    return obj
