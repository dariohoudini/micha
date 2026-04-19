"""
apps/ai_engine/serializers.py
"""
from rest_framework import serializers
from .models import UserTasteProfile, SizeProfile, NotificationPreference


class OnboardingQuizSerializer(serializers.Serializer):
    categories = serializers.ListField(
        child=serializers.CharField(max_length=50),
        min_length=1, max_length=10,
    )
    budget_min = serializers.IntegerField(min_value=0, default=0)
    budget_max = serializers.IntegerField(min_value=0, default=999999)
    shopping_for = serializers.ChoiceField(
        choices=['self', 'family', 'business', 'gifts'], default='self'
    )
    province = serializers.CharField(max_length=50, default='Luanda')
    country = serializers.CharField(max_length=2, default='AO')
    style_tags = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False, default=list
    )
    language = serializers.ChoiceField(choices=['pt', 'en'], default='pt')

    def validate(self, data):
        if data['budget_min'] > data['budget_max']:
            raise serializers.ValidationError("budget_min cannot exceed budget_max")
        return data


class TasteProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserTasteProfile
        fields = [
            'preferred_categories', 'budget_min', 'budget_max',
            'shopping_for', 'province', 'country', 'style_tags',
            'preferred_language', 'category_scores',
            'profile_confidence', 'active_algorithm',
            'quiz_completed', 'quiz_completed_at',
            'total_views', 'total_purchases', 'total_wishlist_adds',
        ]
        read_only_fields = [
            'category_scores', 'profile_confidence', 'active_algorithm',
            'total_views', 'total_purchases', 'total_wishlist_adds',
        ]


class SizeProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = SizeProfile
        fields = [
            'height_cm', 'weight_kg', 'chest_cm', 'waist_cm', 'hips_cm',
            'clothing_size', 'shoe_size_eu', 'fit_preference',
            'inferred_sizes', 'updated_at',
        ]
        read_only_fields = ['inferred_sizes', 'updated_at']


class NotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreference
        fields = [
            'push_enabled', 'email_enabled',
            'price_drops', 'flash_sales', 'new_recommendations',
            'order_updates', 'chat_messages',
            'quiet_hours_start', 'quiet_hours_end',
            'max_daily_recommendations', 'max_daily_flash_sales',
        ]
