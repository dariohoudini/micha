from rest_framework import serializers
from .models import Listing
from .models import Listing, ListingImage


class ListingImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListingImage
        fields = ['id', 'image', 'uploaded_at']


class ListingSerializer(serializers.ModelSerializer):
    duplicates_count = serializers.SerializerMethodField()
    similar_listings = serializers.SerializerMethodField()
    owner_username = serializers.ReadOnlyField(source='owner.username')

    def get_duplicates_count(self, obj):
        return obj.duplicates.filter(is_active=True).count()

    def get_similar_listings(self, obj):
        """Return other listings for same property (different sellers/prices)."""
        if obj.is_duplicate and obj.duplicate_of:
            siblings = Listing.objects.filter(
                duplicate_of=obj.duplicate_of,
                is_active=True,
            ).exclude(pk=obj.pk).values('id', 'price', 'owner__username')[:5]
            return list(siblings)
        return []



    images = ListingImageSerializer(many=True, read_only=True)
    owner_name = serializers.ReadOnlyField(source='owner.full_name')

    class Meta:
        model = Listing
        fields = [
            'id', 'owner', 'owner_name', 'title', 'description',
            'price', 'sale_type', 'city', 'is_active',
            'images', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'owner', 'owner_name', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)
