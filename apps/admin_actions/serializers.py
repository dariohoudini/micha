from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import AdminAction, ProductModeration

User = get_user_model()


class AdminActionSerializer(serializers.ModelSerializer):
    admin_email = serializers.ReadOnlyField(source='admin.email')
    target_email = serializers.ReadOnlyField(source='target.email')

    class Meta:
        model = AdminAction
        fields = ['id', 'admin_email', 'target', 'target_email', 'action', 'reason', 'created_at']
        read_only_fields = ['id', 'admin_email', 'target_email', 'created_at']

    def create(self, validated_data):
        validated_data['admin'] = self.context['request'].user
        return super().create(validated_data)


class ProductModerationSerializer(serializers.ModelSerializer):
    admin_email = serializers.ReadOnlyField(source='admin.email')
    product_title = serializers.ReadOnlyField(source='product.title')

    class Meta:
        model = ProductModeration
        fields = ['id', 'admin_email', 'product', 'product_title', 'action', 'reason', 'created_at']
        read_only_fields = ['id', 'admin_email', 'product_title', 'created_at']

    def create(self, validated_data):
        validated_data['admin'] = self.context['request'].user
        return super().create(validated_data)
