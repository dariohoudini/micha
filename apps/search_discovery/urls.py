from django.urls import path

from .views import (
    BestsellersView, EditorialCollectionView, NewArrivalsView,
    SearchExperimentView, SearchKpiView, TrendingFeedView,
    autocomplete_rebuild, autocomplete_view, badge_award,
    badge_integrity_run, bestsellers_recompute, co_click_record,
    co_purchase_record, comparison_build, complete_the_look_view,
    digest_generate, experiment_analyse, experiment_bucket,
    intent_record, intent_score, new_arrival_admit, query_parse,
    regional_boost_compute, related_rebuild, related_searches_view,
    search_click_log, seller_ranking_snapshot,
    sold_count_display_view, trending_compute, visual_search_log,
    voice_search_log, zero_results_handle,
)


urlpatterns = [
    # CH2 — trending
    path('trending/',                  TrendingFeedView.as_view(), name='sd-trending'),
    path('trending/compute/',          trending_compute, name='sd-trending-compute'),
    # CH3 — digest
    path('digest/generate/',           digest_generate, name='sd-digest'),
    # CH4 — related searches
    path('related-searches/',          related_searches_view, name='sd-related'),
    path('co-click/record/',           co_click_record, name='sd-co-click'),
    path('related-searches/rebuild/',  related_rebuild, name='sd-related-rebuild'),
    # CH5 — bestsellers
    path('bestsellers/',               BestsellersView.as_view(), name='sd-bestsellers'),
    path('bestsellers/recompute/',     bestsellers_recompute, name='sd-bs-recompute'),
    # CH6 — editorial
    path('editorial/collections/',     EditorialCollectionView.as_view(), name='sd-editorial'),
    # CH7 — badges
    path('badges/award/',              badge_award, name='sd-badge-award'),
    path('badges/integrity-run/',      badge_integrity_run, name='sd-badge-integrity'),
    # CH8 — new arrivals
    path('new-arrivals/',              NewArrivalsView.as_view(), name='sd-new-arrivals'),
    path('new-arrivals/admit/',        new_arrival_admit, name='sd-na-admit'),
    # CH9 — regional
    path('regional-boost/',            regional_boost_compute, name='sd-regional'),
    # CH10 — sold count
    path('sold-count-display/',        sold_count_display_view, name='sd-sold-count'),
    # CH11 — comparison
    path('comparison/build/',          comparison_build, name='sd-comparison'),
    # CH12/13 — voice + visual
    path('voice-search/log/',          voice_search_log, name='sd-voice'),
    path('visual-search/log/',         visual_search_log, name='sd-visual'),
    # CH16 — autocomplete
    path('autocomplete/',              autocomplete_view, name='sd-autocomplete'),
    path('autocomplete/rebuild/',      autocomplete_rebuild, name='sd-ac-rebuild'),
    # CH17 — zero results
    path('zero-results/handle/',       zero_results_handle, name='sd-zero'),
    # CH18 — experiments
    path('experiments/',               SearchExperimentView.as_view(), name='sd-experiments'),
    path('experiments/bucket/',        experiment_bucket, name='sd-exp-bucket'),
    path('experiments/analyse/',       experiment_analyse, name='sd-exp-analyse'),
    # CH19 — intent
    path('intent/record/',             intent_record, name='sd-intent'),
    path('intent/score/',              intent_score, name='sd-intent-score'),
    # CH20 — cross-category
    path('complete-the-look/',         complete_the_look_view, name='sd-ctl'),
    path('co-purchase/record/',        co_purchase_record, name='sd-co-purchase'),
    # CH21 — query understanding
    path('query/parse/',               query_parse, name='sd-query-parse'),
    # CH22 — seller ranking
    path('seller-ranking/snapshot/',   seller_ranking_snapshot, name='sd-seller-rank'),
    # CH23 — click logging
    path('clicks/log/',                search_click_log, name='sd-clicks'),
    # CH24 — KPI
    path('admin/kpi/',                 SearchKpiView.as_view(), name='sd-kpi'),
]
