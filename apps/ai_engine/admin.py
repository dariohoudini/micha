"""
apps/ai_engine/apps.py
"""
from django.apps import AppConfig


class AIEngineConfig(AppConfig):
    name = 'apps.ai_engine'
    verbose_name = 'MICHA AI Engine'

    def ready(self):
        from .signals import register_signals
        register_signals()


# ─────────────────────────────────────────────────────────────────────────────

"""
apps/ai_engine/admin.py
"""
from django.contrib import admin
from .models import (
    UserTasteProfile, BehavioralEvent, ProductEmbedding,
    RecommendationCache, SimilarProductsCache,
    PriceDropAlert, SearchQuery, SizeProfile, NotificationPreference
)


@admin.register(UserTasteProfile)
class TasteProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'quiz_completed', 'profile_confidence', 'preferred_categories', 'updated_at']
    list_filter = ['quiz_completed', 'province', 'shopping_for']
    search_fields = ['user__email']
    readonly_fields = ['embedding', 'embedding_updated_at', 'updated_at', 'created_at']
    fieldsets = [
        ('User', {'fields': ['user']}),
        ('Quiz Answers', {'fields': ['preferred_categories', 'budget_min', 'budget_max', 'shopping_for', 'province', 'style_tags', 'quiz_completed', 'quiz_completed_at']}),
        ('Learned Signals', {'fields': ['category_scores', 'brand_scores', 'avg_purchase_price', 'price_sensitivity']}),
        ('Profile Health', {'fields': ['profile_confidence', 'total_views', 'total_purchases', 'total_wishlist_adds']}),
        ('Embedding', {'fields': ['embedding', 'embedding_updated_at'], 'classes': ['collapse']}),
    ]


@admin.register(BehavioralEvent)
class BehavioralEventAdmin(admin.ModelAdmin):
    list_display = ['user', 'event_type', 'category', 'price', 'signal_weight', 'created_at']
    list_filter = ['event_type', 'created_at']
    search_fields = ['user__email']
    readonly_fields = ['id', 'signal_weight', 'created_at']
    date_hierarchy = 'created_at'


@admin.register(PriceDropAlert)
class PriceDropAlertAdmin(admin.ModelAdmin):
    list_display = ['user', 'product_id', 'price_when_added', 'current_price', 'alert_threshold_pct', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['user__email']


@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    list_display = ['user', 'raw_query', 'detected_category', 'detected_price_max', 'results_count', 'created_at']
    list_filter = ['detected_category', 'detected_language']
    search_fields = ['raw_query', 'user__email']
    date_hierarchy = 'created_at'


@admin.register(SizeProfile)
class SizeProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'clothing_size', 'shoe_size_eu', 'fit_preference', 'updated_at']
    search_fields = ['user__email']


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ['user', 'push_enabled', 'price_drops', 'flash_sales', 'max_daily_recommendations']
    list_filter = ['push_enabled', 'flash_sales', 'price_drops']
    search_fields = ['user__email']


@admin.register(RecommendationCache)
class RecommendationCacheAdmin(admin.ModelAdmin):
    list_display = ['user', 'feed_type', 'is_cold_start', 'algorithm_version', 'expires_at']
    list_filter = ['feed_type', 'is_cold_start', 'algorithm_version']
    search_fields = ['user__email']
