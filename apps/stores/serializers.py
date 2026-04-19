from rest_framework import serializers
from .models import Store, StoreReview


class StoreReviewSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.ReadOnlyField(source='reviewer.full_name')

    class Meta:
        model = StoreReview
        fields = ['id', 'reviewer_name', 'rating', 'comment', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        request = self.context['request']
        store = self.context['store']
        if StoreReview.objects.filter(store=store, reviewer=request.user).exists():
            raise serializers.ValidationError("You have already reviewed this store.")
        if store.owner == request.user:
            raise serializers.ValidationError("You cannot review your own store.")
        return attrs

    def create(self, validated_data):
        validated_data['reviewer'] = self.context['request'].user
        validated_data['store'] = self.context['store']
        return super().create(validated_data)


class StoreSerializer(serializers.ModelSerializer):
    owner_name = serializers.ReadOnlyField(source='owner.full_name')
    owner_email = serializers.ReadOnlyField(source='owner.email')
    # FIX: use cached_rating field instead of live Avg query every request
    average_rating = serializers.DecimalField(
        source='cached_rating', max_digits=3, decimal_places=2, read_only=True
    )
    total_reviews = serializers.IntegerField(
        source='total_reviews_count', read_only=True
    )
    total_products = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            'id', 'name', 'description', 'city', 'is_active',
            'owner_name', 'owner_email',
            'average_rating', 'total_reviews', 'total_products',
            'created_at',
        ]
        read_only_fields = ['id', 'owner_name', 'owner_email', 'created_at']

    def get_total_products(self, obj):
        return obj.products.filter(is_active=True, is_archived=False).count()


class PublicStoreSerializer(serializers.ModelSerializer):
    # FIX: use cached_rating — no DB aggregation needed on every list request
    average_rating = serializers.DecimalField(
        source='cached_rating', max_digits=3, decimal_places=2, read_only=True
    )
    total_reviews = serializers.IntegerField(
        source='total_reviews_count', read_only=True
    )

    class Meta:
        model = Store
        fields = [
            'id', 'name', 'description', 'city',
            'average_rating', 'total_reviews',
        ]
