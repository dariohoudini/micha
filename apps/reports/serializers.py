from rest_framework import serializers
from .models import Report


class ReportSerializer(serializers.ModelSerializer):
    reporter_email = serializers.ReadOnlyField(source='reporter.email')

    class Meta:
        model = Report
        fields = [
            'id', 'reporter_email',
            'target_type', 'target_id',
            'reason', 'status', 'created_at',
        ]
        read_only_fields = ['id', 'reporter_email', 'status', 'created_at']

    def validate(self, attrs):
        request = self.context['request']
        existing = Report.objects.filter(
            reporter=request.user,
            target_type=attrs['target_type'],
            target_id=attrs['target_id'],
        ).exists()
        if existing:
            raise serializers.ValidationError("You have already reported this item.")
        return attrs

    def create(self, validated_data):
        validated_data['reporter'] = self.context['request'].user
        return super().create(validated_data)
