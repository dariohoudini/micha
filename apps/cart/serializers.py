from rest_framework import serializers
from .models import Cart, CartItem


class CartItemSerializer(serializers.ModelSerializer):
    product_title = serializers.ReadOnlyField(source='product.title')
    product_price = serializers.ReadOnlyField(source='product.price')
    product_image = serializers.SerializerMethodField()
    line_total = serializers.ReadOnlyField()
    in_stock = serializers.SerializerMethodField()
    variant_combo_id = serializers.IntegerField(source='variant_combo.id', read_only=True, default=None)
    variant_options = serializers.JSONField(source='variant_combo.options', read_only=True, default=dict)
    variant_image = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            'id', 'product', 'product_title', 'product_price',
            'product_image', 'quantity', 'line_total',
            'in_stock', 'added_at',
            'variant_combo_id', 'variant_options', 'variant_image',
        ]
        read_only_fields = ['id', 'added_at']

    def get_product_image(self, obj):
        # Use prefetched cache; .first() would N+1 across the cart.
        cached = list(obj.product.images.all())
        first_image = cached[0] if cached else None
        if first_image:
            request = self.context.get('request')
            if request and first_image.image:
                return request.build_absolute_uri(first_image.image.url)
        return None

    def get_variant_image(self, obj):
        if obj.variant_combo and obj.variant_combo.image:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.variant_combo.image.url)
        return None

    def get_in_stock(self, obj):
        if obj.variant_combo:
            return obj.variant_combo.quantity >= obj.quantity
        return obj.product.quantity >= obj.quantity

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError("Quantity must be at least 1.")
        return value


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_items = serializers.ReadOnlyField(source="item_count")
    subtotal = serializers.ReadOnlyField(source="total")

    class Meta:
        model = Cart
        fields = ['id', 'items', 'total_items', 'subtotal', 'updated_at']


class AddToCartSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1, default=1)
    variant_combo_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_product_id(self, value):
        from apps.products.models import Product
        try:
            Product.objects.get(pk=value, is_active=True, is_archived=False)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found or unavailable.")
        return value

    def validate(self, attrs):
        from apps.products.models import Product
        from apps.inventory.models import ProductVariantCombo
        product = Product.objects.get(pk=attrs['product_id'])
        combo_id = attrs.get('variant_combo_id')

        has_variants = product.variant_combos.filter(is_active=True).exists()
        if has_variants and not combo_id:
            raise serializers.ValidationError({
                'variant_combo_id': 'Este produto tem variantes — selecione uma opção.'
            })
        if combo_id and not has_variants:
            raise serializers.ValidationError({
                'variant_combo_id': 'Produto sem variantes.'
            })
        if combo_id:
            try:
                combo = ProductVariantCombo.objects.get(pk=combo_id, product=product, is_active=True)
            except ProductVariantCombo.DoesNotExist:
                raise serializers.ValidationError({'variant_combo_id': 'Variante inválida.'})
            if combo.quantity < attrs['quantity']:
                raise serializers.ValidationError(
                    f"Apenas {combo.quantity} unidades disponíveis para esta variante."
                )
        else:
            if product.quantity < attrs['quantity']:
                raise serializers.ValidationError(
                    f"Apenas {product.quantity} unidades disponíveis."
                )
        return attrs
