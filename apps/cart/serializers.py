from rest_framework import serializers
from .models import Cart, CartItem
from apps.products.serializers import PublicProductSerializer


class CartItemSerializer(serializers.ModelSerializer):
    product_title = serializers.ReadOnlyField(source='product.title')
    product_price = serializers.ReadOnlyField(source='product.price')
    product_image = serializers.SerializerMethodField()
    line_total = serializers.ReadOnlyField()
    in_stock = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            'id', 'product', 'product_title', 'product_price',
            'product_image', 'quantity', 'line_total',
            'variant_info', 'in_stock', 'added_at',
        ]
        read_only_fields = ['id', 'added_at']

    def get_product_image(self, obj):
        first_image = obj.product.images.first()
        if first_image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(first_image.image.url)
        return None

    def get_in_stock(self, obj):
        return obj.product.quantity >= obj.quantity

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("Quantity must be at least 1.")
        return value


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_items = serializers.ReadOnlyField()
    subtotal = serializers.ReadOnlyField()

    class Meta:
        model = Cart
        fields = ['id', 'items', 'total_items', 'subtotal', 'updated_at']


class AddToCartSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)
    variant_info = serializers.JSONField(required=False)

    def validate_product_id(self, value):
        from apps.products.models import Product
        try:
            product = Product.objects.get(pk=value, is_active=True, is_archived=False)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found or unavailable.")
        return value

    def validate(self, attrs):
        from apps.products.models import Product
        product = Product.objects.get(pk=attrs['product_id'])
        if product.quantity < attrs['quantity']:
            raise serializers.ValidationError(
                f"Only {product.quantity} items available in stock."
            )
        return attrs
