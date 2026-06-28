"""
Search & Discovery — data model
===============================

Implements AliExpress_Search_Discovery_Additional.docx CH1–CH24
where existing apps don't already own the schema. We DO NOT
duplicate:

  - apps.search.SearchEvent / SearchHistory / QueryProductBoost
  - apps.recommendations.RecentlyViewed / ProductSimilarity /
    ProductInteraction / BrowsingSession
  - apps.collections.ProductCollection / ProductOfTheDay
  - apps.buyer_engagement.HomeFeedPersonalisation
  - apps.marketing_engine.FlashSaleItem

New tables:

  CH2   TrendingScore                 — purchase velocity engine
  CH3   EmailDigestRun, EmailDigestItem
  CH4   CoClickEdge, RelatedSearch
  CH5   BestsellerBadge
  CH6   EditorialCollection, EditorialSlot
  CH7   VerifiedBadge, BadgeIntegrityCheck
  CH8   NewArrivalEntry               — quality gate + freshness decay
  CH9   RegionalSurfacingRule
  CH10  SoldCountDisplayRule
  CH11  AttributeSchema, ProductComparison
  CH12  VoiceSearchLog
  CH13  VisualSearchLog
  CH15  FlashDealDiscoverySnapshot
  CH16  AutocompleteSuggestion
  CH17  ZeroResultsLog
  CH18  SearchExperiment, ExperimentAssignment
  CH19  IntentSignal
  CH20  CrossCategoryAffinity
  CH21  QueryParse
  CH22  SellerRankingSignal
  CH23  SearchClickLog
  CH24  SearchKpiSnapshot
  Audit SearchDiscoveryEvent
"""
from __future__ import annotations

import hashlib
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

User = settings.AUTH_USER_MODEL


# ─────────────────────────────────────────────────────────────────
# CH2 — Trending
# ─────────────────────────────────────────────────────────────────

class TrendingScore(models.Model):
    """Real-time purchase-velocity score per product. Recomputed by
    the trending worker every 15 min; the feed reads the latest
    snapshot ordered by score."""

    id = models.BigAutoField(primary_key=True)
    product_id = models.CharField(max_length=64, db_index=True)
    category_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    country = models.CharField(max_length=2, blank=True, default='', db_index=True)
    velocity_1h = models.FloatField(default=0)
    velocity_24h = models.FloatField(default=0)
    velocity_7d_baseline = models.FloatField(default=0)
    acceleration = models.FloatField(
        default=0,
        help_text='velocity_1h vs 7d baseline ratio — the trending signal.',
    )
    view_to_purchase_rate = models.FloatField(default=0)
    score = models.FloatField(default=0, db_index=True)
    computed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=['country', '-score'])]


# ─────────────────────────────────────────────────────────────────
# CH3 — Weekly email digest
# ─────────────────────────────────────────────────────────────────

class EmailDigestRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_digests')
    week_start = models.DateField(db_index=True)
    item_count = models.PositiveSmallIntegerField(default=0)
    personalisation_basis = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=12, default='generated',
        choices=(('generated', 'Generated'), ('sent', 'Sent'),
                 ('skipped', 'Skipped — no items'),
                 ('failed', 'Failed')),
    )
    sent_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('user', 'week_start')]


class EmailDigestItem(models.Model):
    id = models.BigAutoField(primary_key=True)
    run = models.ForeignKey(EmailDigestRun, on_delete=models.CASCADE, related_name='items')
    product_id = models.CharField(max_length=64)
    slot = models.PositiveSmallIntegerField()
    reason = models.CharField(
        max_length=24,
        choices=(('viewed_similar', 'Viewed similar'),
                 ('price_dropped', 'Price dropped'),
                 ('trending', 'Trending'),
                 ('back_in_stock', 'Back in stock'),
                 ('category_affinity', 'Category affinity'),
                 ('wishlist', 'In wishlist')),
    )
    clicked = models.BooleanField(default=False)


# ─────────────────────────────────────────────────────────────────
# CH4 — Co-click graph + related searches
# ─────────────────────────────────────────────────────────────────

class CoClickEdge(models.Model):
    """Edge in the query co-click graph: users who searched A also
    clicked results of B."""

    id = models.BigAutoField(primary_key=True)
    query_a = models.CharField(max_length=200, db_index=True)
    query_b = models.CharField(max_length=200, db_index=True)
    co_click_count = models.PositiveIntegerField(default=0)
    strength = models.FloatField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('query_a', 'query_b')]


class RelatedSearch(models.Model):
    """Materialised top-N related queries per source query — what the
    'related searches' strip renders."""

    id = models.BigAutoField(primary_key=True)
    source_query = models.CharField(max_length=200, db_index=True)
    related_query = models.CharField(max_length=200)
    rank = models.PositiveSmallIntegerField()
    strength = models.FloatField(default=0)
    computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('source_query', 'rank')]


# ─────────────────────────────────────────────────────────────────
# CH5 — Bestseller badges
# ─────────────────────────────────────────────────────────────────

class BestsellerBadge(models.Model):
    """'#1 Bestseller in X' badge state. Recomputed daily; decays
    when the product slips below the threshold."""

    id = models.BigAutoField(primary_key=True)
    product_id = models.CharField(max_length=64, db_index=True)
    category_id = models.CharField(max_length=64, db_index=True)
    country = models.CharField(max_length=2, blank=True, default='')
    rank = models.PositiveSmallIntegerField()
    score = models.FloatField(default=0)
    is_active = models.BooleanField(default=True)
    awarded_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('category_id', 'country', 'rank')]


# ─────────────────────────────────────────────────────────────────
# CH6 — Editorial curation
# ─────────────────────────────────────────────────────────────────

class EditorialCollection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, max_length=120)
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=255, blank=True, default='')
    hero_image_key = models.CharField(max_length=255, blank=True, default='')
    product_ids = models.JSONField(default=list)
    curator = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='curated_collections',
    )
    country_scope = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=12, default='draft',
        choices=(('draft', 'Draft'), ('scheduled', 'Scheduled'),
                 ('live', 'Live'), ('archived', 'Archived')),
    )
    live_from = models.DateTimeField(null=True, blank=True)
    live_until = models.DateTimeField(null=True, blank=True)
    view_count = models.PositiveIntegerField(default=0)
    click_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)


class EditorialSlot(models.Model):
    """A surface placement (home hero, category banner, etc.) bound
    to a collection for a date range."""

    id = models.BigAutoField(primary_key=True)
    surface = models.CharField(
        max_length=24,
        choices=(('home_hero', 'Home hero'),
                 ('home_row', 'Home row'),
                 ('category_banner', 'Category banner'),
                 ('search_banner', 'Search banner'),
                 ('flash_tab', 'Flash tab')),
    )
    collection = models.ForeignKey(EditorialCollection, on_delete=models.CASCADE, related_name='slots')
    position = models.PositiveSmallIntegerField(default=1)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)


# ─────────────────────────────────────────────────────────────────
# CH7 — Verified badges
# ─────────────────────────────────────────────────────────────────

BADGE_TYPE_CHOICES = (
    ('official_brand',  'Official Brand Store'),
    ('verified_seller', 'Verified Seller'),
    ('top_rated',       'Top Rated'),
    ('fast_shipper',    'Fast Shipper'),
    ('choice',          'MICHA Choice'),
    ('local_warehouse', 'Local Warehouse'),
)


class VerifiedBadge(models.Model):
    id = models.BigAutoField(primary_key=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='discovery_badges')
    badge_type = models.CharField(max_length=20, choices=BADGE_TYPE_CHOICES)
    eligibility_snapshot = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    awarded_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoke_reason = models.CharField(max_length=120, blank=True, default='')

    class Meta:
        unique_together = [('seller', 'badge_type')]


class BadgeIntegrityCheck(models.Model):
    """CH7.2 — daily re-verification that badge holders still meet
    eligibility. Failures auto-revoke."""

    id = models.BigAutoField(primary_key=True)
    badge = models.ForeignKey(VerifiedBadge, on_delete=models.CASCADE, related_name='integrity_checks')
    still_eligible = models.BooleanField()
    metrics_snapshot = models.JSONField(default=dict, blank=True)
    action_taken = models.CharField(
        max_length=16, default='none',
        choices=(('none', 'None'), ('warned', 'Warned'),
                 ('revoked', 'Revoked')),
    )
    checked_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH8 — New arrivals
# ─────────────────────────────────────────────────────────────────

class NewArrivalEntry(models.Model):
    """A product admitted to the New Arrivals feed after the quality
    gate. Freshness decays over 14 days."""

    id = models.BigAutoField(primary_key=True)
    product_id = models.CharField(max_length=64, unique=True, db_index=True)
    category_id = models.CharField(max_length=64, blank=True, default='', db_index=True)
    quality_score = models.FloatField(default=0)
    gate_passed = models.BooleanField(default=False)
    gate_failures = models.JSONField(default=list, blank=True)
    freshness_score = models.FloatField(default=1.0)
    listed_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    admitted_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH9 — Regional surfacing
# ─────────────────────────────────────────────────────────────────

class RegionalSurfacingRule(models.Model):
    """Per-country boost for locally-warehoused products."""

    id = models.BigAutoField(primary_key=True)
    country = models.CharField(max_length=2, unique=True)
    local_warehouse_boost = models.FloatField(default=1.5)
    domestic_seller_boost = models.FloatField(default=1.2)
    fast_delivery_days_threshold = models.PositiveSmallIntegerField(default=3)
    fast_delivery_boost = models.FloatField(default=1.3)
    is_active = models.BooleanField(default=True)


# ─────────────────────────────────────────────────────────────────
# CH10 — Sold count display
# ─────────────────────────────────────────────────────────────────

class SoldCountDisplayRule(models.Model):
    """Display thresholds: below `min_display` show nothing; above
    each band show the rounded string ('1K+ sold')."""

    id = models.BigAutoField(primary_key=True)
    country = models.CharField(max_length=2, blank=True, default='', unique=True)
    min_display = models.PositiveIntegerField(default=10)
    bands = models.JSONField(
        default=list,
        help_text='[{"min": 1000, "label": "1K+"}, ...] descending order.',
    )
    is_active = models.BooleanField(default=True)


# ─────────────────────────────────────────────────────────────────
# CH11 — Product comparison
# ─────────────────────────────────────────────────────────────────

class AttributeSchema(models.Model):
    """Normalised attribute definitions per category so different
    sellers' 'RAM: 8GB' / 'Memory 8 GB' unify into one comparable
    field."""

    id = models.BigAutoField(primary_key=True)
    category_id = models.CharField(max_length=64, db_index=True)
    attribute_key = models.CharField(max_length=64)
    display_name = models.CharField(max_length=120)
    data_type = models.CharField(
        max_length=12, default='string',
        choices=(('string', 'String'), ('number', 'Number'),
                 ('boolean', 'Boolean'), ('enum', 'Enum')),
    )
    unit = models.CharField(max_length=20, blank=True, default='')
    synonyms = models.JSONField(default=list, blank=True)
    importance_rank = models.PositiveSmallIntegerField(default=50)

    class Meta:
        unique_together = [('category_id', 'attribute_key')]


class ProductComparison(models.Model):
    """A saved comparison session (2-4 products)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='product_comparisons',
    )
    product_ids = models.JSONField(default=list)
    category_id = models.CharField(max_length=64, blank=True, default='')
    comparison_matrix = models.JSONField(default=dict, blank=True)
    differences_highlighted = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# CH12 / CH13 — Voice + visual search logs
# ─────────────────────────────────────────────────────────────────

class VoiceSearchLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='voice_searches',
    )
    audio_duration_ms = models.PositiveIntegerField(default=0)
    transcribed_text = models.CharField(max_length=500)
    stt_confidence = models.FloatField(default=0)
    language = models.CharField(max_length=10, default='pt-AO')
    results_count = models.PositiveIntegerField(default=0)
    clicked_result = models.BooleanField(default=False)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)


class VisualSearchLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='visual_searches',
    )
    image_key = models.CharField(max_length=255)
    detected_objects = models.JSONField(default=list, blank=True)
    matched_product_ids = models.JSONField(default=list, blank=True)
    top_match_confidence = models.FloatField(default=0)
    results_count = models.PositiveIntegerField(default=0)
    clicked_result = models.BooleanField(default=False)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ─────────────────────────────────────────────────────────────────
# CH15 — Flash deal discovery
# ─────────────────────────────────────────────────────────────────

class FlashDealDiscoverySnapshot(models.Model):
    """Aggregated flash-deal feed snapshot (refreshed every minute
    during events) — what the countdown-browse tab reads."""

    id = models.BigAutoField(primary_key=True)
    event_slug = models.CharField(max_length=64, db_index=True)
    deals = models.JSONField(default=list, blank=True)
    total_deals = models.PositiveIntegerField(default=0)
    soonest_ending_at = models.DateTimeField(null=True, blank=True)
    computed_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ─────────────────────────────────────────────────────────────────
# CH16 — Autocomplete
# ─────────────────────────────────────────────────────────────────

class AutocompleteSuggestion(models.Model):
    """Materialised suggestion per prefix. Updated nightly from the
    query log + curated entries."""

    id = models.BigAutoField(primary_key=True)
    prefix = models.CharField(max_length=60, db_index=True)
    suggestion = models.CharField(max_length=200)
    rank = models.PositiveSmallIntegerField()
    source = models.CharField(
        max_length=12, default='organic',
        choices=(('organic', 'Organic — query log'),
                 ('curated', 'Curated'),
                 ('trending', 'Trending'),
                 ('category', 'Category')),
    )
    search_count = models.PositiveIntegerField(default=0)
    language = models.CharField(max_length=10, default='pt-AO')
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = [('prefix', 'rank', 'language')]


# ─────────────────────────────────────────────────────────────────
# CH17 — Zero results
# ─────────────────────────────────────────────────────────────────

class ZeroResultsLog(models.Model):
    id = models.BigAutoField(primary_key=True)
    query = models.CharField(max_length=200, db_index=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='zero_result_searches',
    )
    language = models.CharField(max_length=10, default='pt-AO')
    country = models.CharField(max_length=2, blank=True, default='')
    fallback_strategy = models.CharField(
        max_length=20, blank=True, default='',
        choices=(('broadened', 'Broadened terms'),
                 ('spell_corrected', 'Spell corrected'),
                 ('category_suggest', 'Category suggestion'),
                 ('synonym_expand', 'Synonym expansion'),
                 ('none', 'No fallback found')),
    )
    fallback_results_count = models.PositiveIntegerField(default=0)
    converted = models.BooleanField(default=False)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)


# ─────────────────────────────────────────────────────────────────
# CH18 — Search A/B experiments
# ─────────────────────────────────────────────────────────────────

class SearchExperiment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(unique=True, max_length=80)
    name = models.CharField(max_length=160)
    hypothesis = models.TextField(blank=True, default='')
    ranking_config_control = models.JSONField(default=dict, blank=True)
    ranking_config_variant = models.JSONField(default=dict, blank=True)
    traffic_pct = models.PositiveSmallIntegerField(default=50)
    primary_metric = models.CharField(max_length=40, default='ctr')
    status = models.CharField(
        max_length=12, default='draft',
        choices=(('draft', 'Draft'), ('running', 'Running'),
                 ('analysing', 'Analysing'),
                 ('shipped', 'Shipped — variant won'),
                 ('reverted', 'Reverted — control won')),
    )
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    result_summary = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ExperimentAssignment(models.Model):
    id = models.BigAutoField(primary_key=True)
    experiment = models.ForeignKey(SearchExperiment, on_delete=models.CASCADE, related_name='assignments')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='search_experiment_assignments')
    bucket = models.CharField(
        max_length=8,
        choices=(('control', 'Control'), ('variant', 'Variant')),
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('experiment', 'user')]


# ─────────────────────────────────────────────────────────────────
# CH19 — Intent signals
# ─────────────────────────────────────────────────────────────────

INTENT_SIGNAL_KIND_CHOICES = (
    ('dwell_long',       'Long dwell on PDP'),
    ('image_zoom',       'Zoomed images'),
    ('spec_expand',      'Expanded specifications'),
    ('review_read',      'Read reviews'),
    ('size_check',       'Checked size guide'),
    ('shipping_check',   'Checked shipping estimate'),
    ('share',            'Shared product'),
    ('re_visit',         'Re-visited PDP'),
    ('cart_hesitation',  'Added + removed from cart'),
)


class IntentSignal(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='intent_signals',
    )
    session_id = models.CharField(max_length=64, blank=True, default='')
    product_id = models.CharField(max_length=64, db_index=True)
    kind = models.CharField(max_length=20, choices=INTENT_SIGNAL_KIND_CHOICES)
    value = models.FloatField(default=0)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=['user', 'product_id'])]


# ─────────────────────────────────────────────────────────────────
# CH20 — Cross-category discovery
# ─────────────────────────────────────────────────────────────────

class CrossCategoryAffinity(models.Model):
    """'Bought X → also buys Y category' edges. Drives Complete-the-
    Look and bundle suggestions."""

    id = models.BigAutoField(primary_key=True)
    source_category_id = models.CharField(max_length=64, db_index=True)
    target_category_id = models.CharField(max_length=64, db_index=True)
    co_purchase_count = models.PositiveIntegerField(default=0)
    affinity_score = models.FloatField(default=0)
    sample_product_pairs = models.JSONField(default=list, blank=True)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('source_category_id', 'target_category_id')]


# ─────────────────────────────────────────────────────────────────
# CH21 — Query understanding
# ─────────────────────────────────────────────────────────────────

class QueryParse(models.Model):
    """Cached semantic parse per normalised query — entities,
    category prediction, attribute filters."""

    query_hash = models.CharField(max_length=64, primary_key=True)
    raw_query = models.CharField(max_length=200)
    normalised_query = models.CharField(max_length=200)
    detected_entities = models.JSONField(default=dict, blank=True)
    predicted_category_id = models.CharField(max_length=64, blank=True, default='')
    category_confidence = models.FloatField(default=0)
    extracted_filters = models.JSONField(default=dict, blank=True)
    language = models.CharField(max_length=10, default='pt-AO')
    parsed_at = models.DateTimeField(auto_now=True)


# ─────────────────────────────────────────────────────────────────
# CH22 — Seller ranking signals
# ─────────────────────────────────────────────────────────────────

class SellerRankingSignal(models.Model):
    """Daily per-seller composite that the search ranker multiplies
    into every listing's score."""

    id = models.BigAutoField(primary_key=True)
    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ranking_signals')
    snapshot_date = models.DateField(db_index=True)
    fulfilment_score = models.FloatField(default=0)
    service_score = models.FloatField(default=0)
    quality_score = models.FloatField(default=0)
    trust_score = models.FloatField(default=0)
    composite_multiplier = models.FloatField(default=1.0)

    class Meta:
        unique_together = [('seller', 'snapshot_date')]


# ─────────────────────────────────────────────────────────────────
# CH23 — Search click analytics
# ─────────────────────────────────────────────────────────────────

class SearchClickLog(models.Model):
    """Position-aware click log: query → result position → clicked.
    Drives CTR-by-position curves + ranking training data."""

    id = models.BigAutoField(primary_key=True)
    query = models.CharField(max_length=200, db_index=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='search_clicks',
    )
    session_id = models.CharField(max_length=64, blank=True, default='')
    product_id = models.CharField(max_length=64, db_index=True)
    position = models.PositiveSmallIntegerField()
    page = models.PositiveSmallIntegerField(default=1)
    experiment_bucket = models.CharField(max_length=8, blank=True, default='')
    action = models.CharField(
        max_length=12, default='click',
        choices=(('impression', 'Impression'), ('click', 'Click'),
                 ('add_to_cart', 'Add to cart'),
                 ('purchase', 'Purchase')),
    )
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [models.Index(fields=['query', 'action'])]


# ─────────────────────────────────────────────────────────────────
# CH24 — KPI snapshot
# ─────────────────────────────────────────────────────────────────

class SearchKpiSnapshot(models.Model):
    snapshot_date = models.DateField(primary_key=True)
    total_searches = models.PositiveIntegerField(default=0)
    zero_results_pct = models.FloatField(default=0)
    search_ctr = models.FloatField(default=0)
    search_to_cart_pct = models.FloatField(default=0)
    search_to_purchase_pct = models.FloatField(default=0)
    avg_click_position = models.FloatField(default=0)
    autocomplete_usage_pct = models.FloatField(default=0)
    voice_searches = models.PositiveIntegerField(default=0)
    visual_searches = models.PositiveIntegerField(default=0)
    trending_feed_ctr = models.FloatField(default=0)
    digest_open_rate = models.FloatField(default=0)
    digest_click_rate = models.FloatField(default=0)
    comparison_sessions = models.PositiveIntegerField(default=0)
    active_experiments = models.PositiveSmallIntegerField(default=0)
    by_language = models.JSONField(default=dict, blank=True)
    by_country = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


# ─────────────────────────────────────────────────────────────────
# Audit
# ─────────────────────────────────────────────────────────────────

class SearchDiscoveryEvent(models.Model):
    id = models.BigAutoField(primary_key=True)
    kind = models.CharField(max_length=64, db_index=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='sd_audit_events',
    )
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    @staticmethod
    def log(*, kind, user=None, payload=None):
        try:
            return SearchDiscoveryEvent.objects.create(
                kind=kind, user=user, payload=payload or {},
            )
        except Exception:
            return None
