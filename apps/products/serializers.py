from rest_framework import serializers
from .models import Product, ProductImage, Category


# -----------------------------
# Public serializers
# -----------------------------
class PublicProductSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source="store.name", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "title",
            "price",
            "store_name",
            "created_at",
        ]


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ('image',)


class ProductSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, required=False)

    class Meta:
        model = Product
        fields = (
            'id',
            'title',
            'description',
            'sale_type',
            'price',
            'quantity',
            'category',
            'latitude',
            'longitude',
            'images',
        )

    def create(self, validated_data):
        images_data = validated_data.pop('images', [])
        product = Product.objects.create(**validated_data)

        for image_data in images_data:
            ProductImage.objects.create(product=product, **image_data)

        return product

    def update(self, instance, validated_data):
        images_data = validated_data.pop('images', [])
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if images_data:
            instance.images.all().delete()  # replace old images
            for image_data in images_data:
                ProductImage.objects.create(product=instance, **image_data)

        return instance


# -----------------------------
# Seller serializers (NEW)
# -----------------------------
class SellerProductCreateUpdateSerializer(ProductSerializer):
    """For seller product create & update (nested images supported)"""
    class Meta(ProductSerializer.Meta):
        fields = ProductSerializer.Meta.fields


class SellerProductListSerializer(serializers.ModelSerializer):
    """For listing seller's own products"""
    images = ProductImageSerializer(many=True, read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "title",
            "price",
            "quantity",
            "sale_type",
            "store_name",
            "category_name",
            "images",
            "created_at",
        ]
