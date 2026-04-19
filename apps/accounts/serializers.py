from rest_framework import serializers
from .models import Block


class BlockSerializer(serializers.ModelSerializer):
    blocked_email = serializers.ReadOnlyField(source='blocked.email')
    blocked_name = serializers.ReadOnlyField(source='blocked.full_name')

    class Meta:
        model = Block
        fields = ['id', 'blocked', 'blocked_email', 'blocked_name', 'created_at']
        read_only_fields = ['id', 'created_at']

    def validate(self, attrs):
        request = self.context['request']
        if request.user == attrs.get('blocked'):
            raise serializers.ValidationError("You cannot block yourself.")
        already_blocked = Block.objects.filter(
            blocker=request.user, blocked=attrs['blocked']
        ).exists()
        if already_blocked:
            raise serializers.ValidationError("You have already blocked this user.")
        return attrs

    def create(self, validated_data):
        validated_data['blocker'] = self.context['request'].user
        return super().create(validated_data)
