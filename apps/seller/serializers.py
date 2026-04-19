from rest_framework import serializers
from apps.verification.models import SellerVerification
from apps.stores.models import Store
from apps.products.models import Product
from apps.reviews.models import Review
from django.db.models import Avg


class SellerVerificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerVerification
        fields = [
            'id', 'user', 'id_number', 'id_expiry_date',
            'id_document', 'selfie', 'status',
            'last_selfie_update', 'created_at',
        ]
        read_only_fields = ['user', 'status', 'last_selfie_update', 'created_at']


class StoreSerializer(serializers.ModelSerializer):
    average_rating = serializers.SerializerMethodField()
    total_products = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            'id', 'name', 'description', 'city', 'is_active',
            'average_rating', 'total_products', 'created_at',
        ]
        read_only_fields = ['id', 'owner', 'created_at']

    def get_average_rating(self, obj):
        avg = Review.objects.filter(seller=obj.owner).aggregate(avg=Avg('rating'))['avg']
        return round(avg or 0, 2)

    def get_total_products(self, obj):
        return obj.products.filter(is_active=True, is_archived=False).count()


class ProductSerializer(serializers.ModelSerializer):
    is_available = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'store', 'category', 'title', 'description',
            'sale_type', 'price', 'quantity', 'is_archived', 'is_active',
            'is_available', 'latitude', 'longitude', 'created_at',
        ]
        read_only_fields = ['id', 'is_archived', 'created_at']

    def get_is_available(self, obj):
        return obj.quantity > 0 and not obj.is_archived
