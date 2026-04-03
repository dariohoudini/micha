from rest_framework import serializers
from .models import SellerVerification
from apps.stores.models import Store
from apps.products.models import Product
from django.db.models import Avg

# -------------------------
# Seller Verification
# -------------------------
class SellerVerificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerVerification
        fields = ["id", "user", "verified", "document"]
        read_only_fields = ["user"]

# -------------------------
# Product Serializer
# -------------------------
class ProductSerializer(serializers.ModelSerializer):
    is_available = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "store",
            "category",
            "title",
            "description",
            "sale_type",
            "price",
            "quantity",
            "is_archived",
            "is_available",
            "latitude",
            "longitude",
            "views",
            "created_at",
        ]
        read_only_fields = ["id", "store", "is_archived", "views", "created_at"]

    def get_is_available(self, obj):
        return obj.quantity > 0 and not obj.is_archived

# -------------------------
# Store Serializer
# -------------------------
class StoreSerializer(serializers.ModelSerializer):
    average_rating = serializers.SerializerMethodField()
    total_products = serializers.SerializerMethodField()

    class Meta:
        model = Store
        fields = [
            "id",
            "name",
            "description",
            "city",
            "is_active",
            "average_rating",
            "total_products",
        ]
        read_only_fields = ["id", "owner"]

    def get_average_rating(self, obj):
        return round(obj.products.aggregate(avg=Avg('rating'))['avg'] or 0, 2)

    def get_total_products(self, obj):
        return obj.products.count()
