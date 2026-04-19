"""
apps/rentals/serializers.py
"""
from rest_framework import serializers
from .models import (
    Listing, PropertyDetail, VehicleDetail, OtherRentalDetail,
    ListingLocation, ListingImage, ListingInquiry, RentalVerification,
    SavedListing
)


class ListingImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ListingImage
        fields = ['id', 'image_url', 'order', 'caption', 'is_cover']

    def get_image_url(self, obj):
        request = self.context.get('request')
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


class ListingLocationSerializer(serializers.ModelSerializer):
    display_location = serializers.SerializerMethodField()

    class Meta:
        model = ListingLocation
        fields = [
            'province', 'municipality', 'neighbourhood',
            'street', 'address_complement',
            'latitude', 'longitude', 'has_gps',
            'location_privacy', 'display_location',
        ]

    def get_display_location(self, obj):
        return obj.get_display_location()


class PropertyDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyDetail
        exclude = ['listing']


class VehicleDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = VehicleDetail
        exclude = ['listing']


class OtherRentalDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = OtherRentalDetail
        exclude = ['listing']


class ListingListSerializer(serializers.ModelSerializer):
    """Compact serializer for listing cards in browse view."""
    cover_image = serializers.SerializerMethodField()
    location_display = serializers.SerializerMethodField()
    formatted_price = serializers.ReadOnlyField()
    lister_name = serializers.SerializerMethodField()
    lister_role_label = serializers.SerializerMethodField()

    class Meta:
        model = Listing
        fields = [
            'id', 'title', 'category', 'purpose', 'lister_role',
            'lister_role_label', 'price', 'price_period', 'formatted_price',
            'price_negotiable', 'cover_image', 'location_display',
            'views_count', 'saves_count', 'lister_name', 'created_at',
        ]

    def get_cover_image(self, obj):
        img = obj.images.filter(is_cover=True).first() or obj.images.first()
        if img:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(img.image.url)
        return None

    def get_location_display(self, obj):
        try:
            return obj.location.get_display_location()
        except Exception:
            return ''

    def get_lister_name(self, obj):
        return getattr(obj.lister, 'username', None) or obj.lister.email.split('@')[0]

    def get_lister_role_label(self, obj):
        return dict(obj._meta.get_field('lister_role').choices).get(obj.lister_role, obj.lister_role)


class ListingDetailSerializer(serializers.ModelSerializer):
    """Full serializer for listing detail view."""
    images = ListingImageSerializer(many=True, read_only=True)
    location = ListingLocationSerializer(read_only=True)
    property_detail = PropertyDetailSerializer(read_only=True)
    vehicle_detail = VehicleDetailSerializer(read_only=True)
    other_detail = OtherRentalDetailSerializer(read_only=True)
    formatted_price = serializers.ReadOnlyField()
    lister_name = serializers.SerializerMethodField()
    lister_verified = serializers.SerializerMethodField()
    lister_role_label = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()

    class Meta:
        model = Listing
        fields = [
            'id', 'title', 'description', 'category', 'purpose',
            'lister_role', 'lister_role_label',
            'price', 'price_period', 'formatted_price', 'price_negotiable',
            'deposit_required', 'deposit_amount',
            'micheiro_commission_disclosed', 'micheiro_commission_description',
            'contact_via_chat', 'contact_phone_visible', 'contact_whatsapp',
            'views_count', 'inquiries_count', 'saves_count',
            'images', 'location',
            'property_detail', 'vehicle_detail', 'other_detail',
            'lister_name', 'lister_verified', 'is_saved',
            'status', 'created_at', 'published_at',
        ]

    def get_lister_name(self, obj):
        return getattr(obj.lister, 'username', None) or obj.lister.email.split('@')[0]

    def get_lister_verified(self, obj):
        try:
            return obj.lister.rental_verification.is_approved
        except Exception:
            return False

    def get_lister_role_label(self, obj):
        return dict(obj._meta.get_field('lister_role').choices).get(obj.lister_role, obj.lister_role)

    def get_is_saved(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return SavedListing.objects.filter(user=request.user, listing=obj).exists()
        return False


class CreateListingSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating a listing."""
    location = ListingLocationSerializer(required=True)
    property_detail = PropertyDetailSerializer(required=False)
    vehicle_detail = VehicleDetailSerializer(required=False)
    other_detail = OtherRentalDetailSerializer(required=False)

    class Meta:
        model = Listing
        fields = [
            'title', 'description', 'category', 'purpose', 'lister_role',
            'price', 'price_period', 'price_negotiable',
            'deposit_required', 'deposit_amount',
            'micheiro_commission_disclosed', 'micheiro_commission_description',
            'contact_via_chat', 'contact_phone_visible', 'contact_whatsapp',
            'location', 'property_detail', 'vehicle_detail', 'other_detail',
        ]

    def validate(self, data):
        category = data.get('category')
        lister_role = data.get('lister_role')

        # Micheiro must disclose commission
        if lister_role == 'micheiro' and not data.get('micheiro_commission_disclosed'):
            raise serializers.ValidationError(
                "Micheiros devem divulgar a sua comissão antes de publicar."
            )

        # Category-specific detail required
        if category == 'property' and not data.get('property_detail'):
            raise serializers.ValidationError(
                "Detalhes do imóvel são obrigatórios para listagens de propriedades."
            )
        if category == 'vehicle' and not data.get('vehicle_detail'):
            raise serializers.ValidationError(
                "Detalhes do veículo são obrigatórios para listagens de veículos."
            )

        return data

    def create(self, validated_data):
        location_data = validated_data.pop('location')
        property_data = validated_data.pop('property_detail', None)
        vehicle_data = validated_data.pop('vehicle_detail', None)
        other_data = validated_data.pop('other_detail', None)

        listing = Listing.objects.create(**validated_data)
        ListingLocation.objects.create(listing=listing, **location_data)

        if property_data:
            PropertyDetail.objects.create(listing=listing, **property_data)
        if vehicle_data:
            VehicleDetail.objects.create(listing=listing, **vehicle_data)
        if other_data:
            OtherRentalDetail.objects.create(listing=listing, **other_data)

        return listing

    def update(self, instance, validated_data):
        location_data = validated_data.pop('location', None)
        property_data = validated_data.pop('property_detail', None)
        vehicle_data = validated_data.pop('vehicle_detail', None)
        other_data = validated_data.pop('other_detail', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if location_data:
            ListingLocation.objects.update_or_create(
                listing=instance, defaults=location_data
            )
        if property_data:
            PropertyDetail.objects.update_or_create(
                listing=instance, defaults=property_data
            )
        if vehicle_data:
            VehicleDetail.objects.update_or_create(
                listing=instance, defaults=vehicle_data
            )
        if other_data:
            OtherRentalDetail.objects.update_or_create(
                listing=instance, defaults=other_data
            )

        return instance


class RentalVerificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = RentalVerification
        fields = [
            'id', 'id_document_type', 'id_document_number',
            'id_document_image', 'selfie_image',
            'is_micheiro', 'micheiro_description', 'commission_rate_pct',
            'status', 'rejection_reason', 'submitted_at',
        ]
        read_only_fields = ['status', 'rejection_reason', 'submitted_at']


class ListingInquirySerializer(serializers.ModelSerializer):
    class Meta:
        model = ListingInquiry
        fields = [
            'id', 'listing', 'message', 'move_in_date',
            'rental_duration', 'status', 'created_at',
        ]
        read_only_fields = ['status', 'created_at']
