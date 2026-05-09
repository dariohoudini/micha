"""
Products Serialisers
FIX: DynamicFieldsMixin — ?fields=id,title,price returns only those fields
     Mobile apps no longer download 30 fields when they need 4
"""
from rest_framework import serializers
from .models import Product, Category, ProductImage, ProductQA, PriceTier
from apps.inventory.models import ProductVariantCombo


class PriceTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceTier
        fields = ['id', 'min_quantity', 'unit_price']
        read_only_fields = fields


class VariantComboSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariantCombo
        fields = ["id", "options", "price", "quantity", "sku", "image_url", "is_active"]
        read_only_fields = fields

    def get_image_url(self, obj):
        if not obj.image:
            return None
        req = self.context.get("request")
        return req.build_absolute_uri(obj.image.url) if req else obj.image.url


class DynamicFieldsMixin:
    """
    Mixin that allows API callers to request specific fields.
    GET /api/products/?fields=id,title,price,thumbnail
    Returns only those fields — reduces payload 80% for mobile clients.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request:
            fields_param = request.query_params.get("fields")
            if fields_param:
                requested = set(fields_param.split(","))
                allowed = set(self.fields.keys())
                for field_name in allowed - requested:
                    self.fields.pop(field_name, None)


class CategorySerializer(serializers.ModelSerializer):
    subcategories = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "icon", "image", "parent", "subcategories", "ordering"]

    def get_subcategories(self, obj):
        subs = obj.subcategories.all()
        return CategorySerializer(subs, many=True, context=self.context).data if subs.exists() else []


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ["id", "image", "thumbnail_url", "medium_url", "large_url", "alt_text", "ordering"]


class ProductListSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    """Lightweight serialiser for list views — supports ?fields= parameter."""
    store_name = serializers.CharField(source="store.name", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default="")
    thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id", "title", "slug", "price", "compare_at_price",
            "discount_percentage", "quantity", "condition", "sale_type",
            "store_name", "category_name", "is_featured", "is_boosted",
            "views", "created_at", "thumbnail",
        ]
        read_only_fields = fields

    def get_thumbnail(self, obj):
        img = obj.images.first()
        if img:
            if img.thumbnail_url:
                return img.thumbnail_url
            if img.image:
                req = self.context.get("request")
                return req.build_absolute_uri(img.image.url) if req else img.image.url
        return None


class ProductDetailSerializer(DynamicFieldsMixin, serializers.ModelSerializer):
    """Full serialiser for product detail — all fields."""
    images = ProductImageSerializer(many=True, read_only=True)
    store_name = serializers.CharField(source="store.name", read_only=True)
    store_id = serializers.IntegerField(source="store.id", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True, default="")
    tags = serializers.SlugRelatedField(many=True, slug_field="name", read_only=True)
    variant_combos = serializers.SerializerMethodField()
    variant_axes = serializers.SerializerMethodField()
    price_tiers = PriceTierSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id", "title", "slug", "description", "brand", "condition", "sale_type",
            "price", "compare_at_price", "cost_price", "discount_percentage",
            "quantity", "sku", "barcode", "low_stock_threshold", "is_low_stock",
            "weight_kg", "length_cm", "width_cm", "height_cm",
            "is_active", "is_featured", "is_boosted", "publish_at",
            "warranty_info", "return_policy",
            "meta_title", "meta_description",
            "views", "add_to_cart_count", "wishlist_count",
            "store_name", "store_id", "category_name",
            "tags", "images", "variant_combos", "variant_axes", "price_tiers",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "slug", "discount_percentage", "is_low_stock",
            "views", "add_to_cart_count", "wishlist_count",
            "store_name", "store_id", "category_name",
            "images", "variant_combos", "variant_axes", "price_tiers",
            "created_at", "updated_at",
        ]

    def get_variant_combos(self, obj):
        combos = obj.variant_combos.filter(is_active=True)
        return VariantComboSerializer(combos, many=True, context=self.context).data

    def get_variant_axes(self, obj):
        """Derive axes from active combos. Returns ordered list of {name, values[]}.
        e.g. [{"name": "Color", "values": ["Red", "Blue"]}, {"name": "Size", "values": ["M", "L"]}]
        """
        axes = {}  # preserve insertion order via dict
        for combo in obj.variant_combos.filter(is_active=True):
            for k, v in (combo.options or {}).items():
                axes.setdefault(k, [])
                if v not in axes[k]:
                    axes[k].append(v)
        return [{"name": k, "values": v} for k, v in axes.items()]


class ProductWriteSerializer(serializers.ModelSerializer):
    """Serialiser for creating/updating products — explicit writable fields only."""
    class Meta:
        model = Product
        # FIX: Explicit writable fields — seller cannot set is_featured or is_boosted
        fields = [
            "title", "description", "brand", "condition", "sale_type",
            "price", "compare_at_price", "cost_price", "quantity",
            "sku", "barcode", "low_stock_threshold", "category",
            "weight_kg", "length_cm", "width_cm", "height_cm",
            "warranty_info", "return_policy", "meta_title", "meta_description",
            "publish_at", "tags",
        ]

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0.")
        return value

    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Quantity cannot be negative.")
        return value


class ProductQASerializer(serializers.ModelSerializer):
    asker_name = serializers.SerializerMethodField()
    answered_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ProductQA
        fields = ["id", "question", "answer", "asker_name", "answered_by_name", "answered_at", "created_at"]
        read_only_fields = ["id", "answer", "asker_name", "answered_at", "created_at"]

    def get_asker_name(self, obj):
        try:
            return obj.asker.profile.full_name or "Anonymous"
        except Exception:
            return "Anonymous"

    def get_answered_by_name(self, obj):
        if not obj.answered_by_id:
            return None
        try:
            return obj.answered_by.profile.full_name or "Vendedor"
        except Exception:
            return "Vendedor"

# Backwards compatibility aliases — other apps import these names
PublicProductSerializer = ProductListSerializer
SlimProductSerializer = ProductListSerializer
