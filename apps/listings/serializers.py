from rest_framework import serializers
from .models import Listing, ListingImage


class ListingImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ListingImage
        fields = ['id', 'image', 'uploaded_at']


class ListingSerializer(serializers.ModelSerializer):
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
