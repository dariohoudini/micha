from rest_framework import serializers


class SlimProductSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    slug = serializers.CharField()
    price = serializers.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = serializers.DecimalField(max_digits=10, decimal_places=2, allow_null=True)
    discount_percentage = serializers.FloatField()
    quantity = serializers.IntegerField()
    views = serializers.IntegerField()
    is_featured = serializers.BooleanField()
    condition = serializers.CharField()
    created_at = serializers.DateTimeField()
    store_name = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()
    thumbnail_url = serializers.SerializerMethodField()

    def get_store_name(self, obj):
        try:
            return obj.store.name
        except Exception:
            return ""

    def get_category_name(self, obj):
        try:
            return obj.category.name
        except Exception:
            return ""

    def get_thumbnail_url(self, obj):
        try:
            img = obj.images.filter(is_primary=True).first() or obj.images.first()
            return img.thumbnail_url if img else None
        except Exception:
            return None
