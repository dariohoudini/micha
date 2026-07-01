"""
Products Serialisers
FIX: DynamicFieldsMixin — ?fields=id,title,price returns only those fields
     Mobile apps no longer download 30 fields when they need 4
"""
from rest_framework import serializers
from .models import Product, Category, ProductImage, ProductQA, PriceTier, ProductTag
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
        # §15 — expose attribute_schema so the product wizard can
        # render the right dynamic fields per leaf category.
        fields = ["id", "name", "slug", "icon", "image", "parent",
                  "subcategories", "ordering", "attribute_schema"]

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
    # Optional SPU/SKU annotations (only present when ?collapse=group is used)
    product_group_id = serializers.IntegerField(read_only=True, allow_null=True)
    seller_count = serializers.IntegerField(source="_seller_count", read_only=True, default=None)
    group_best_price = serializers.DecimalField(
        source="_group_best_price", max_digits=10, decimal_places=2,
        read_only=True, allow_null=True, default=None,
    )

    class Meta:
        model = Product
        fields = [
            "id", "title", "slug", "price", "compare_at_price",
            "discount_percentage", "quantity", "condition", "sale_type",
            "store_name", "category_name", "is_featured", "is_boosted",
            "views", "created_at", "thumbnail",
            "product_group_id", "seller_count", "group_best_price",
        ]
        read_only_fields = fields

    def get_thumbnail(self, obj):
        # Use the prefetched list — `.first()` would issue a fresh LIMIT 1
        # query per row, defeating the prefetch_related and triggering
        # an N+1 across the whole product list.
        cached = obj.images.all()
        img = next(iter(cached), None) if hasattr(cached, '__iter__') else None
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
    product_group_id = serializers.IntegerField(read_only=True, allow_null=True)
    other_offers_count = serializers.SerializerMethodField()
    other_offers_best_price = serializers.SerializerMethodField()

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
            "product_group_id", "other_offers_count", "other_offers_best_price",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "slug", "discount_percentage", "is_low_stock",
            "views", "add_to_cart_count", "wishlist_count",
            "store_name", "store_id", "category_name",
            "images", "variant_combos", "variant_axes", "price_tiers",
            "product_group_id", "other_offers_count", "other_offers_best_price",
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

    def _other_offers_qs(self, obj):
        if not obj.product_group_id:
            return Product.objects.none()
        return Product.active.filter(
            product_group_id=obj.product_group_id,
        ).exclude(pk=obj.pk)

    def get_other_offers_count(self, obj):
        return self._other_offers_qs(obj).count()

    def get_other_offers_best_price(self, obj):
        from django.db.models import Min
        return self._other_offers_qs(obj).aggregate(p=Min('price'))['p']


class _JSONStringField(serializers.JSONField):
    """JSONField that parses a JSON STRING from multipart/form-data.

    DRF's default JSONField behind a ModelSerializer happily accepts a
    string-shaped value off FormData and writes it to the DB literally
    as a string — so ``attributes='{"a":1}'`` stays a string rather
    than becoming the dict ``{"a": 1}``. This field decodes it.
    """
    def to_internal_value(self, data):
        if isinstance(data, str):
            try:
                import json as _json
                data = _json.loads(data)
            except Exception:
                raise serializers.ValidationError("Invalid JSON.")
        return super().to_internal_value(data)


class ProductWriteSerializer(serializers.ModelSerializer):
    """Serialiser for creating/updating products — explicit writable fields only."""
    # §15 — accept attributes as JSON string from FormData payloads.
    attributes = _JSONStringField(required=False)
    # Tags arrive from the seller as free text (a comma-separated string or a
    # list of names), NOT primary keys — so accept names and get-or-create the
    # ProductTag rows below. The default ModelSerializer M2M field expects PKs,
    # which 400s the product-create form ("Expected pk value, received str").
    tags = serializers.CharField(required=False, allow_blank=True,
                                 write_only=True)

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
            # AliExpress §12.3 promotional pricing + §14 shipping
            # template FK + §15 category-driven attributes.
            "shipping_template", "attributes",
            "promo_price", "promo_start", "promo_end", "promo_max_units",
        ]

    def validate_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Price must be greater than 0.")
        return value

    def validate_quantity(self, value):
        if value < 0:
            raise serializers.ValidationError("Quantity cannot be negative.")
        return value

    def _apply_tags(self, product, raw):
        """Turn free-text tag input ('casual, verão' or ['casual','verão'])
        into ProductTag rows and attach them."""
        if raw in (None, ''):
            return
        names = raw if isinstance(raw, (list, tuple)) else str(raw).split(',')
        cleaned = []
        for n in names:
            n = (n or '').strip()[:50]
            if n:
                cleaned.append(n)
        tags = [ProductTag.objects.get_or_create(name=n)[0] for n in cleaned]
        product.tags.set(tags)

    def create(self, validated_data):
        raw_tags = validated_data.pop('tags', None)
        product = super().create(validated_data)
        self._apply_tags(product, raw_tags)
        return product

    def update(self, instance, validated_data):
        raw_tags = validated_data.pop('tags', None)
        product = super().update(instance, validated_data)
        if raw_tags is not None:
            self._apply_tags(product, raw_tags)
        return product


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
