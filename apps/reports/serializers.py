from rest_framework import serializers
from .models import Report


class ReportSerializer(serializers.ModelSerializer):
    reporter_email = serializers.ReadOnlyField(source="reporter.email")

    class Meta:
        model = Report
        fields = (
            "id",
            "reporter_email",
            "target_type",
            "target_id",
            "reason",
            "status",
            "created_at",
        )
        read_only_fields = ("id", "status", "created_at")

    def create(self, validated_data):
        validated_data["reporter"] = self.context["request"].user
        return super().create(validated_data)
