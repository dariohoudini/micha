from django.contrib import admin

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


@admin.register(TrendingScore)
class TrendingScoreAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'country', 'velocity_1h',
                    'acceleration', 'score', 'computed_at')


@admin.register(EmailDigestRun)
class EmailDigestRunAdmin(admin.ModelAdmin):
    list_display = ('user', 'week_start', 'item_count',
                    'status', 'sent_at', 'opened_at')
    list_filter = ('status',)


@admin.register(EmailDigestItem)
class EmailDigestItemAdmin(admin.ModelAdmin):
    list_display = ('run', 'product_id', 'slot', 'reason', 'clicked')
    list_filter = ('reason',)


@admin.register(CoClickEdge)
class CoClickEdgeAdmin(admin.ModelAdmin):
    list_display = ('query_a', 'query_b', 'co_click_count', 'strength')


@admin.register(RelatedSearch)
class RelatedSearchAdmin(admin.ModelAdmin):
    list_display = ('source_query', 'related_query', 'rank', 'strength')


@admin.register(BestsellerBadge)
class BestsellerBadgeAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'category_id', 'country',
                    'rank', 'score', 'is_active')
    list_filter = ('is_active', 'country')


@admin.register(EditorialCollection)
class EditorialCollectionAdmin(admin.ModelAdmin):
    list_display = ('slug', 'title', 'status', 'curator',
                    'view_count', 'click_count')
    list_filter = ('status',)


@admin.register(EditorialSlot)
class EditorialSlotAdmin(admin.ModelAdmin):
    list_display = ('surface', 'collection', 'position',
                    'starts_at', 'ends_at', 'is_active')
    list_filter = ('surface', 'is_active')


@admin.register(VerifiedBadge)
class VerifiedBadgeAdmin(admin.ModelAdmin):
    list_display = ('seller', 'badge_type', 'is_active',
                    'awarded_at', 'revoked_at')
    list_filter = ('badge_type', 'is_active')


@admin.register(BadgeIntegrityCheck)
class BadgeIntegrityCheckAdmin(admin.ModelAdmin):
    list_display = ('badge', 'still_eligible', 'action_taken', 'checked_at')
    list_filter = ('still_eligible', 'action_taken')


@admin.register(NewArrivalEntry)
class NewArrivalEntryAdmin(admin.ModelAdmin):
    list_display = ('product_id', 'category_id', 'gate_passed',
                    'quality_score', 'freshness_score', 'expires_at')
    list_filter = ('gate_passed',)


@admin.register(RegionalSurfacingRule)
class RegionalSurfacingRuleAdmin(admin.ModelAdmin):
    list_display = ('country', 'local_warehouse_boost',
                    'domestic_seller_boost', 'fast_delivery_boost',
                    'is_active')


@admin.register(SoldCountDisplayRule)
class SoldCountDisplayRuleAdmin(admin.ModelAdmin):
    list_display = ('country', 'min_display', 'is_active')


@admin.register(AttributeSchema)
class AttributeSchemaAdmin(admin.ModelAdmin):
    list_display = ('category_id', 'attribute_key', 'display_name',
                    'data_type', 'unit', 'importance_rank')


@admin.register(ProductComparison)
class ProductComparisonAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'category_id', 'created_at')


@admin.register(VoiceSearchLog)
class VoiceSearchLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'transcribed_text', 'stt_confidence',
                    'results_count', 'occurred_at')


@admin.register(VisualSearchLog)
class VisualSearchLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'top_match_confidence',
                    'results_count', 'occurred_at')


@admin.register(FlashDealDiscoverySnapshot)
class FlashDealDiscoverySnapshotAdmin(admin.ModelAdmin):
    list_display = ('event_slug', 'total_deals',
                    'soonest_ending_at', 'computed_at')


@admin.register(AutocompleteSuggestion)
class AutocompleteSuggestionAdmin(admin.ModelAdmin):
    list_display = ('prefix', 'suggestion', 'rank',
                    'source', 'search_count', 'is_active')
    list_filter = ('source', 'is_active')


@admin.register(ZeroResultsLog)
class ZeroResultsLogAdmin(admin.ModelAdmin):
    list_display = ('query', 'fallback_strategy',
                    'fallback_results_count', 'converted', 'occurred_at')
    list_filter = ('fallback_strategy', 'converted')


@admin.register(SearchExperiment)
class SearchExperimentAdmin(admin.ModelAdmin):
    list_display = ('slug', 'name', 'status', 'traffic_pct',
                    'primary_metric', 'started_at')
    list_filter = ('status',)


@admin.register(ExperimentAssignment)
class ExperimentAssignmentAdmin(admin.ModelAdmin):
    list_display = ('experiment', 'user', 'bucket', 'assigned_at')
    list_filter = ('bucket',)


@admin.register(IntentSignal)
class IntentSignalAdmin(admin.ModelAdmin):
    list_display = ('user', 'product_id', 'kind', 'value', 'occurred_at')
    list_filter = ('kind',)


@admin.register(CrossCategoryAffinity)
class CrossCategoryAffinityAdmin(admin.ModelAdmin):
    list_display = ('source_category_id', 'target_category_id',
                    'co_purchase_count', 'affinity_score')


@admin.register(QueryParse)
class QueryParseAdmin(admin.ModelAdmin):
    list_display = ('normalised_query', 'predicted_category_id',
                    'category_confidence', 'language', 'parsed_at')


@admin.register(SellerRankingSignal)
class SellerRankingSignalAdmin(admin.ModelAdmin):
    list_display = ('seller', 'snapshot_date', 'quality_score',
                    'trust_score', 'composite_multiplier')


@admin.register(SearchClickLog)
class SearchClickLogAdmin(admin.ModelAdmin):
    list_display = ('query', 'product_id', 'position',
                    'action', 'experiment_bucket', 'occurred_at')
    list_filter = ('action',)


@admin.register(SearchKpiSnapshot)
class SearchKpiSnapshotAdmin(admin.ModelAdmin):
    list_display = ('snapshot_date', 'total_searches',
                    'zero_results_pct', 'search_ctr',
                    'voice_searches', 'visual_searches',
                    'active_experiments')


@admin.register(SearchDiscoveryEvent)
class SearchDiscoveryEventAdmin(admin.ModelAdmin):
    list_display = ('kind', 'user', 'created_at')
    list_filter = ('kind',)
    readonly_fields = ('kind', 'user', 'payload', 'created_at')
