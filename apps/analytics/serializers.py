from rest_framework import serializers
from .models import FunnelEvent, SellerPerformance


class FunnelEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = FunnelEvent
        fields = ["id", "event", "product", "session_id", "created_at"]
        read_only_fields = fields


class SellerPerformanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = SellerPerformance
        fields = [
            "response_rate", "avg_response_time_hours",
            "on_time_delivery_rate", "completion_rate",
            "return_rate", "overall_score", "tier", "last_calculated",
        ]
        read_only_fields = fields
